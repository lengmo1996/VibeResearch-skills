#!/usr/bin/env python3
"""Validate writing-knowledge candidate JSON without modifying it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ENTRY_TYPES = {
    "term",
    "phrase",
    "argument-pattern",
    "structure",
    "reviewer-response",
    "error-rule",
    "style-preference",
}
STATUSES = {"pending_review", "approved", "rejected"}
DEDUP_RESULTS = {"exact", "near", "semantic", "unknown"}
REQUIRED = {
    "schema_version",
    "entry_id",
    "entry_type",
    "content",
    "normalized_content",
    "intended_use",
    "avoid_when",
    "source",
    "confidence",
    "deduplication",
    "status",
    "created_at",
    "decision",
}


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(record: dict[str, Any], *, new_record: bool = False) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED - record.keys())
    if missing:
        return [f"missing required fields: {', '.join(missing)}"]

    for field in (
        "schema_version",
        "entry_id",
        "content",
        "normalized_content",
        "intended_use",
        "avoid_when",
        "created_at",
    ):
        if not nonempty_string(record[field]):
            errors.append(f"{field} must be a non-empty string")

    if record["entry_type"] not in ENTRY_TYPES:
        errors.append(f"entry_type must be one of {sorted(ENTRY_TYPES)}")
    if record["status"] not in STATUSES:
        errors.append(f"status must be one of {sorted(STATUSES)}")
    if new_record and record["status"] != "pending_review":
        errors.append("a new record must have status pending_review")

    confidence = record["confidence"]
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0 <= confidence <= 1
    ):
        errors.append("confidence must be numeric between 0 and 1")

    source = record["source"]
    if not isinstance(source, dict) or not nonempty_string(source.get("origin")):
        errors.append("source must be an object with non-empty origin")

    deduplication = record["deduplication"]
    if not isinstance(deduplication, dict):
        errors.append("deduplication must be an object")
    else:
        if not nonempty_string(deduplication.get("scope")):
            errors.append("deduplication.scope must be a non-empty string")
        if deduplication.get("result") not in DEDUP_RESULTS:
            errors.append(f"deduplication.result must be one of {sorted(DEDUP_RESULTS)}")
        if not isinstance(deduplication.get("matched_entry_ids"), list):
            errors.append("deduplication.matched_entry_ids must be a list")

    decision = record["decision"]
    if record["status"] == "pending_review":
        if decision is not None:
            errors.append("pending_review record must not contain a decision")
    elif not isinstance(decision, dict):
        errors.append("approved/rejected record must contain a decision object")
    else:
        expected_action = "approve" if record["status"] == "approved" else "reject"
        if decision.get("action") != expected_action:
            errors.append(f"decision.action must be {expected_action}")
        for field in ("actor", "decided_at", "evidence", "prior_status"):
            if not nonempty_string(decision.get(field)):
                errors.append(f"decision.{field} must be a non-empty string")
        if decision.get("prior_status") != "pending_review":
            errors.append("decision.prior_status must be pending_review")

    return errors


def self_test() -> int:
    good = {
        "schema_version": "1.0",
        "entry_id": "WK-1",
        "entry_type": "term",
        "content": "bounded claim",
        "normalized_content": "bounded claim",
        "intended_use": "academic writing",
        "avoid_when": "unsupported",
        "source": {"origin": "user-supplied"},
        "confidence": 0.8,
        "deduplication": {
            "scope": "supplied",
            "result": "unknown",
            "matched_entry_ids": [],
        },
        "status": "pending_review",
        "created_at": "2000-01-01T00:00:00Z",
        "decision": None,
    }
    if validate(good, new_record=True):
        print("self-test failed: valid candidate rejected", file=sys.stderr)
        return 1
    bad = dict(good, status="approved")
    if not validate(bad, new_record=True):
        print("self-test failed: invalid approval accepted", file=sys.stderr)
        return 1
    print("validate_candidate self-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", nargs="?", type=Path)
    parser.add_argument("--new-record", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.candidate is None:
        parser.error("candidate is required unless --self-test is used")
    try:
        record = json.loads(args.candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read candidate: {exc}", file=sys.stderr)
        return 1
    if not isinstance(record, dict):
        print("candidate must be a JSON object", file=sys.stderr)
        return 1
    errors = validate(record, new_record=args.new_record)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"candidate valid: {record['entry_id']} ({record['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
