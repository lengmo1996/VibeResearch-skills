#!/usr/bin/env python3
"""Validate or atomically apply a hash-bound academic-manuscript revision patch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PATCHES = 100
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
PATCH_ID = re.compile(r"^REV-\d{3,}$")
AUDIT_ID = re.compile(r"^AUD-\d{3,}$")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _contained_file(root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError("path must be a non-empty relative string")
    unresolved = root / relative
    if unresolved.is_symlink():
        raise ValueError(f"symlink paths are not accepted: {relative}")
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes root: {relative}") from exc
    if not candidate.is_file():
        raise ValueError(f"path is not a regular contained file: {relative}")
    if candidate.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"file exceeds {MAX_FILE_BYTES} bytes: {relative}")
    return candidate


def _load_utf8(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def prepare(root: Path, manifest: dict[str, Any]) -> tuple[Path, str, str, list[dict[str, str]]]:
    if manifest.get("schema_version") not in ("1.0.0", "1.1.0"):
        raise ValueError("manifest schema_version must be 1.0.0 or 1.1.0")
    target = _contained_file(root, manifest.get("target_file"))
    source = _load_utf8(target)
    target_hash = manifest.get("target_sha256")
    if not isinstance(target_hash, str) or not HEX_SHA256.fullmatch(target_hash):
        raise ValueError("target_sha256 must be 64 lowercase hexadecimal characters")
    actual_target_hash = _sha256(source)
    if actual_target_hash != target_hash:
        raise ValueError(
            f"target hash conflict: expected {target_hash}, got {actual_target_hash}"
        )

    patches = manifest.get("patches")
    if not isinstance(patches, list) or not patches:
        raise ValueError("patches must be a non-empty array")
    if len(patches) > MAX_PATCHES:
        raise ValueError(f"patches exceeds {MAX_PATCHES} entries")

    seen: set[str] = set()
    prepared: list[dict[str, str]] = []
    occupied: list[tuple[int, int, str]] = []
    for index, item in enumerate(patches, 1):
        if not isinstance(item, dict):
            raise ValueError(f"patch {index}: entry must be an object")
        patch_id = item.get("id")
        if not isinstance(patch_id, str) or not PATCH_ID.fullmatch(patch_id):
            raise ValueError(f"patch {index}: id must match REV-###")
        if patch_id in seen:
            raise ValueError(f"{patch_id}: duplicate patch id")
        seen.add(patch_id)

        audit_ids = item.get("accepted_audit_ids")
        if not isinstance(audit_ids, list) or not audit_ids:
            raise ValueError(f"{patch_id}: accepted_audit_ids must be non-empty")
        if any(not isinstance(value, str) or not AUDIT_ID.fullmatch(value) for value in audit_ids):
            raise ValueError(f"{patch_id}: accepted_audit_ids must match AUD-###")

        start_marker = item.get("start_marker")
        end_marker = item.get("end_marker")
        if not isinstance(start_marker, str) or not isinstance(end_marker, str):
            raise ValueError(f"{patch_id}: markers must be strings")
        if source.count(start_marker) != 1 or source.count(end_marker) != 1:
            raise ValueError(f"{patch_id}: each marker must occur exactly once")
        start = source.index(start_marker) + len(start_marker)
        end = source.index(end_marker)
        if start >= end:
            raise ValueError(f"{patch_id}: markers are empty, reversed, or overlapping")
        for previous_start, previous_end, previous_id in occupied:
            if start < previous_end and end > previous_start:
                raise ValueError(f"{patch_id}: overlaps {previous_id}")
        occupied.append((start, end, patch_id))

        original = source[start:end]
        original_hash = item.get("original_sha256")
        if not isinstance(original_hash, str) or not HEX_SHA256.fullmatch(original_hash):
            raise ValueError(f"{patch_id}: original_sha256 is invalid")
        actual_original_hash = _sha256(original)
        if actual_original_hash != original_hash:
            raise ValueError(
                f"{patch_id}: block hash conflict: expected {original_hash}, "
                f"got {actual_original_hash}"
            )
        replacement_path = _contained_file(root, item.get("replacement_file"))
        replacement = _load_utf8(replacement_path)
        replacement_hash = item.get("replacement_sha256")
        if not isinstance(replacement_hash, str) or not HEX_SHA256.fullmatch(replacement_hash):
            raise ValueError(f"{patch_id}: replacement_sha256 is required; bind the reviewed replacement before validation")
        actual_replacement_hash = _sha256(replacement)
        if actual_replacement_hash != replacement_hash:
            raise ValueError(f"{patch_id}: replacement hash conflict")
        prepared.append(
            {
                "id": patch_id,
                "start": str(start),
                "end": str(end),
                "original_sha256": actual_original_hash,
                "replacement_sha256": actual_replacement_hash,
                "replacement": replacement,
            }
        )

    revised = source
    for patch in sorted(prepared, key=lambda value: int(value["start"]), reverse=True):
        start = int(patch["start"])
        end = int(patch["end"])
        revised = revised[:start] + patch["replacement"] + revised[end:]
    return target, source, revised, prepared


def _atomic_write(target: Path, text: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, target.stat().st_mode)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def run_self_test() -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        target = root / "manuscript.md"
        replacement = root / "replacement.md"
        original = "\nOriginal claim with \\\\cite{key}.\n"
        source = (
            "Before\n<!-- REV:REV-001:START -->"
            + original
            + "<!-- REV:REV-001:END -->\nAfter\n"
        )
        target.write_text(source, encoding="utf-8", newline="")
        replacement.write_text(
            "\nClearer claim with \\\\cite{key}.\n", encoding="utf-8", newline=""
        )
        manifest = {
            "schema_version": "1.1.0",
            "target_file": "manuscript.md",
            "target_sha256": _sha256(source),
            "patches": [
                {
                    "id": "REV-001",
                    "accepted_audit_ids": ["AUD-001"],
                    "start_marker": "<!-- REV:REV-001:START -->",
                    "end_marker": "<!-- REV:REV-001:END -->",
                    "original_sha256": _sha256(original),
                    "replacement_file": "replacement.md",
                    "replacement_sha256": _sha256(_load_utf8(replacement)),
                }
            ],
        }
        _, before, revised, prepared = prepare(root, manifest)
        if before == revised or len(prepared) != 1:
            print("self-test failed: valid patch was not prepared", file=sys.stderr)
            return 1
        _atomic_write(target, revised)
        applied = _load_utf8(target)
        if applied != revised or not applied.startswith("Before\n") or not applied.endswith("After\n"):
            print("self-test failed: atomic apply changed undeclared text", file=sys.stderr)
            return 1
        bad_manifest = json.loads(json.dumps(manifest))
        bad_manifest["patches"][0]["original_sha256"] = "0" * 64
        try:
            prepare(root, bad_manifest)
        except ValueError:
            pass
        else:
            print("self-test failed: stale block hash was accepted", file=sys.stderr)
            return 1
    print("Self-test passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    if args.root is None or args.manifest is None:
        parser.error("provide --root and --manifest or use --self-test")

    try:
        root = args.root.resolve()
        if not root.is_dir():
            raise ValueError("root must be an existing directory")
        manifest_path = _contained_file(root, str(args.manifest))
        manifest = json.loads(_load_utf8(manifest_path))
        if not isinstance(manifest, dict):
            raise ValueError("manifest root must be an object")
        target, source, revised, patches = prepare(root, manifest)
        if args.apply:
            _atomic_write(target, revised)
        result = {
            "valid": True,
            "applied": args.apply,
            "target": target.relative_to(root).as_posix(),
            "source_sha256": _sha256(source),
            "output_sha256": _sha256(revised),
            "untouched_segments_preserved": True,
            "patches": [
                {key: value for key, value in patch.items() if key != "replacement"}
                for patch in patches
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {"valid": False, "applied": False, "errors": [str(exc)]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
