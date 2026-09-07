#!/usr/bin/env python3
"""Validate a literature KB paper manifest without modifying it."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED = {
    "paper_id",
    "source_path",
    "source_sha256",
    "generation_id",
    "metadata",
    "metadata_provenance",
    "metadata_confidence",
    "extraction_status",
}


def validate_records(records: Iterable[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    paper_ids: dict[str, int] = {}
    source_hashes: dict[tuple[str, str], int] = {}

    for line_number, record in enumerate(records, 1):
        prefix = f"record {line_number}"
        missing = sorted(REQUIRED - record.keys())
        if missing:
            errors.append(f"{prefix}: missing {', '.join(missing)}")
            continue

        paper_id = record["paper_id"]
        if not isinstance(paper_id, str) or not paper_id.strip():
            errors.append(f"{prefix}: paper_id must be a non-empty string")
        elif paper_id in paper_ids:
            errors.append(
                f"{prefix}: duplicate paper_id {paper_id!r} "
                f"(first at record {paper_ids[paper_id]})"
            )
        else:
            paper_ids[paper_id] = line_number

        source_path = record["source_path"]
        if not isinstance(source_path, str) or not source_path.strip():
            errors.append(f"{prefix}: source_path must be a non-empty string")

        source_hash = record["source_sha256"]
        if not isinstance(source_hash, str) or not SHA256.fullmatch(source_hash):
            errors.append(f"{prefix}: source_sha256 must be 64 lowercase hex characters")
        elif isinstance(source_path, str):
            identity = (source_path.casefold(), source_hash)
            if identity in source_hashes:
                errors.append(
                    f"{prefix}: duplicate source path/hash "
                    f"(first at record {source_hashes[identity]})"
                )
            else:
                source_hashes[identity] = line_number

        if not isinstance(record["generation_id"], str) or not record["generation_id"]:
            errors.append(f"{prefix}: generation_id must be a non-empty string")
        if not isinstance(record["metadata"], dict):
            errors.append(f"{prefix}: metadata must be an object")
        if not isinstance(record["metadata_provenance"], dict):
            errors.append(f"{prefix}: metadata_provenance must be an object")

        confidence = record["metadata_confidence"]
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            errors.append(f"{prefix}: metadata_confidence must be numeric")
        elif not 0 <= confidence <= 1:
            errors.append(f"{prefix}: metadata_confidence must be between 0 and 1")

        if not isinstance(record["extraction_status"], str) or not record["extraction_status"]:
            errors.append(f"{prefix}: extraction_status must be a non-empty string")

    return errors


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [f"cannot read {path}: {exc}"]

    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {line_number}: record must be a JSON object")
            continue
        records.append(value)
    if not records and not errors:
        errors.append("manifest contains no records")
    return records, errors


def self_test() -> int:
    good = {
        "paper_id": "paper-1",
        "source_path": "papers/example.pdf",
        "source_sha256": "a" * 64,
        "generation_id": "gen-1",
        "metadata": {"title": "Example"},
        "metadata_provenance": {"title": "pdf"},
        "metadata_confidence": 0.8,
        "extraction_status": "complete",
    }
    if validate_records([good]):
        print("self-test failed: valid record rejected", file=sys.stderr)
        return 1
    bad = dict(good, source_sha256="bad", metadata_confidence=2)
    if len(validate_records([bad])) != 2:
        print("self-test failed: invalid fields not detected", file=sys.stderr)
        return 1
    if not validate_records([good, good]):
        print("self-test failed: duplicate record not detected", file=sys.stderr)
        return 1
    print("validate_kb_manifest self-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.manifest is None:
        parser.error("manifest is required unless --self-test is used")

    records, errors = read_jsonl(args.manifest)
    errors.extend(validate_records(records))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"manifest valid: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
