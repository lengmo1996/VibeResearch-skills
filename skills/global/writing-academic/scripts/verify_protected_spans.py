#!/usr/bin/env python3
"""Verify literal protected spans across a rewrite without modifying either file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_SPANS = 500
MAX_SPAN_CHARS = 500


def _load_text(path: Path) -> str:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"{path.name}: file exceeds {MAX_FILE_BYTES} bytes")
    return path.read_text(encoding="utf-8")


def verify(source: str, revised: str, manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    spans = manifest.get("protected_spans")
    if manifest.get("schema_version") != "1.0.0":
        errors.append("manifest schema_version must be 1.0.0")
    if not isinstance(spans, list) or not spans:
        errors.append("manifest protected_spans must be a non-empty array")
        spans = []
    if len(spans) > MAX_SPANS:
        errors.append(f"manifest contains more than {MAX_SPANS} protected spans")

    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for index, item in enumerate(spans[:MAX_SPANS], 1):
        if not isinstance(item, dict):
            errors.append(f"span {index}: entry must be an object")
            continue
        span_id = item.get("id")
        text = item.get("text")
        expected = item.get("expected_count")
        if not isinstance(span_id, str) or not span_id.strip():
            errors.append(f"span {index}: id must be a non-empty string")
            continue
        if span_id in seen:
            errors.append(f"{span_id}: duplicate id")
            continue
        seen.add(span_id)
        if not isinstance(text, str) or not text or len(text) > MAX_SPAN_CHARS:
            errors.append(
                f"{span_id}: text must contain 1..{MAX_SPAN_CHARS} characters"
            )
            continue
        if expected is not None and (
            not isinstance(expected, int) or isinstance(expected, bool) or expected < 1
        ):
            errors.append(f"{span_id}: expected_count must be a positive integer")
            continue

        source_count = source.count(text)
        revised_count = revised.count(text)
        required_count = expected if expected is not None else source_count
        status = "pass"
        if source_count == 0:
            status = "manifest-error"
            errors.append(f"{span_id}: protected span is absent from source")
        elif source_count != required_count:
            status = "manifest-error"
            errors.append(
                f"{span_id}: source count {source_count} != expected {required_count}"
            )
        elif revised_count != required_count:
            status = "fail"
            errors.append(
                f"{span_id}: revised count {revised_count} != expected {required_count}"
            )
        results.append(
            {
                "id": span_id,
                "source_count": source_count,
                "revised_count": revised_count,
                "expected_count": required_count,
                "status": status,
            }
        )

    return {
        "valid": not errors,
        "checked_span_count": len(results),
        "results": results,
        "errors": errors,
    }


def run_self_test() -> int:
    manifest = {
        "schema_version": "1.0.0",
        "protected_spans": [
            {"id": "CIT-001", "text": "\\cite{verified-key}", "expected_count": 1},
            {"id": "NUM-001", "text": "42.7%", "expected_count": 1},
        ],
    }
    valid = verify(
        "Result 42.7% follows \\cite{verified-key}.",
        "According to \\cite{verified-key}, the result is 42.7%.",
        manifest,
    )
    invalid = verify(
        "Result 42.7% follows \\cite{verified-key}.",
        "The result improves.",
        manifest,
    )
    if not valid["valid"] or invalid["valid"]:
        print("Self-test failed.", file=sys.stderr)
        return 1
    print("Self-test passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--revised", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    if not all((args.source, args.revised, args.manifest)):
        parser.error("provide --source, --revised, and --manifest or use --self-test")
    try:
        source = _load_text(args.source)
        revised = _load_text(args.revised)
        manifest_text = _load_text(args.manifest)
        manifest = json.loads(manifest_text)
        if not isinstance(manifest, dict):
            raise ValueError("manifest root must be an object")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2
    result = verify(source, revised, manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
