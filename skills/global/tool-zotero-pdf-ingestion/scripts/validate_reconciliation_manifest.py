#!/usr/bin/env python3
"""Validate Zotero–PDF reconciliation JSONL without modifying it."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

SHA256 = re.compile(r"^[0-9a-f]{64}$")
STATUSES = {
    "matched",
    "loose_pdf",
    "missing_pdf",
    "conflict",
    "candidate_match",
    "duplicate_group",
    "needs_review",
}
FUZZY_METHODS = {"title-similarity", "author-year-similarity", "filename-similarity"}
APPROVAL_PLACEHOLDERS = {"unresolved", "unknown", "unclear", "not provided", "not-provided",
                         "not provided / unclear", "not checked", "not-checked", "pending", "tbd", "todo", "none", "n/a"}
REQUIRED = {
    "schema_version",
    "record_id",
    "zotero_key",
    "pdf_path",
    "pdf_sha256",
    "status",
    "relationship",
    "match_decision",
    "metadata",
    "conflicts",
    "kb_ready",
}


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def approval_supplied(value: Any) -> bool:
    return nonempty(value) and value.strip().casefold() not in APPROVAL_PLACEHOLDERS and not re.fullmatch(
        r"<[^>]+>", value.strip()
    )


def validate_records(records: Iterable[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    ids: dict[str, int] = {}
    for number, record in enumerate(records, 1):
        prefix = f"record {number}"
        if not isinstance(record, dict):
            errors.append(f"{prefix}: record must be an object")
            continue
        missing = sorted(REQUIRED - record.keys())
        if missing:
            errors.append(f"{prefix}: missing {', '.join(missing)}")
            continue

        record_id = record["record_id"]
        if not nonempty(record_id):
            errors.append(f"{prefix}: record_id must be non-empty")
        elif record_id in ids:
            errors.append(f"{prefix}: duplicate record_id {record_id!r}")
        else:
            ids[record_id] = number

        status = record["status"]
        if status not in STATUSES:
            errors.append(f"{prefix}: invalid status {status!r}")
        if not nonempty(record["relationship"]):
            errors.append(f"{prefix}: relationship must be non-empty")
        if not isinstance(record["metadata"], dict):
            errors.append(f"{prefix}: metadata must be an object")
        if not isinstance(record["conflicts"], list):
            errors.append(f"{prefix}: conflicts must be a list")
        if not isinstance(record["kb_ready"], bool):
            errors.append(f"{prefix}: kb_ready must be boolean")

        has_zotero = record["zotero_key"] is not None and nonempty(record["zotero_key"])
        has_pdf = record["pdf_path"] is not None and nonempty(record["pdf_path"])
        pdf_hash = record["pdf_sha256"]
        if has_pdf and (not isinstance(pdf_hash, str) or not SHA256.fullmatch(pdf_hash)):
            errors.append(f"{prefix}: PDF records require a lowercase SHA-256")
        if not has_pdf and pdf_hash is not None:
            errors.append(f"{prefix}: pdf_sha256 must be null when pdf_path is null")
        if status == "matched" and not (has_zotero and has_pdf):
            errors.append(f"{prefix}: matched requires Zotero key and PDF")
        if status == "loose_pdf" and not (has_pdf and not has_zotero):
            errors.append(f"{prefix}: loose_pdf requires PDF without Zotero key")
        if status == "missing_pdf" and not (has_zotero and not has_pdf):
            errors.append(f"{prefix}: missing_pdf requires Zotero key without PDF")

        decision = record["match_decision"]
        if not isinstance(decision, dict):
            errors.append(f"{prefix}: match_decision must be an object")
            continue
        method = decision.get("method")
        evidence = decision.get("evidence")
        confidence = decision.get("confidence")
        review = decision.get("review_required")
        if not nonempty(method):
            errors.append(f"{prefix}: match_decision.method must be non-empty")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{prefix}: match_decision.evidence must be a non-empty list")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            errors.append(f"{prefix}: match_decision.confidence must be 0..1")
        if not isinstance(review, bool):
            errors.append(f"{prefix}: match_decision.review_required must be boolean")
        if method in FUZZY_METHODS and review is not True:
            errors.append(f"{prefix}: fuzzy method requires review_required true")
        if record["kb_ready"] is True:
            if status not in {"matched", "loose_pdf"} or not has_pdf:
                errors.append(f"{prefix}: kb_ready requires a matched or admitted loose PDF")
            if review is not False or method in FUZZY_METHODS:
                errors.append(f"{prefix}: kb_ready cannot require review or rely on an automated fuzzy match")
            if record["conflicts"]:
                errors.append(f"{prefix}: kb_ready cannot contain unresolved conflicts")
            approval = decision.get("approval")
            if not isinstance(approval, dict) or approval.get("status") != "approved" or not all(
                approval_supplied(approval.get(field)) for field in ("actor", "approved_at", "evidence")
            ):
                errors.append(f"{prefix}: kb_ready requires traceable approval metadata")

    return errors


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [f"cannot read {path}: {exc}"]
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {number}: record must be an object")
        else:
            records.append(value)
    if not records and not errors:
        errors.append("manifest contains no records")
    return records, errors


def self_test() -> int:
    good = {
        "schema_version": "1.0",
        "record_id": "REC-1",
        "zotero_key": "KEY1",
        "pdf_path": "papers/a.pdf",
        "pdf_sha256": "a" * 64,
        "status": "matched",
        "relationship": "one-to-one",
        "match_decision": {
            "method": "attachment-link",
            "evidence": ["link"],
            "confidence": 1.0,
            "alternative_record_ids": [],
            "review_required": False,
            "approval": {
                "status": "approved", "actor": "test-user",
                "approved_at": "2026-09-06T00:00:00Z", "evidence": "synthetic self-test approval",
            },
        },
        "metadata": {},
        "conflicts": [],
        "kb_ready": True,
    }
    if validate_records([good]):
        print("self-test failed: valid record rejected", file=sys.stderr)
        return 1
    bad = dict(good, match_decision={**good["match_decision"], "method": "title-similarity"})
    if not validate_records([bad]):
        print("self-test failed: unsafe fuzzy match accepted", file=sys.stderr)
        return 1
    print("validate_reconciliation_manifest self-test passed")
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
    print(f"reconciliation manifest valid: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
