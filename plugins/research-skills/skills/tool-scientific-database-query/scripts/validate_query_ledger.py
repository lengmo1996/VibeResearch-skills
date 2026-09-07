#!/usr/bin/env python3
"""Validate a scientific database query ledger without issuing requests."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


QUERY_ID = re.compile(r"^QRY-[0-9]{3,8}$")
MODES = {"capability", "targeted", "exhaustive", "resume", "cross-check", "audit"}
VERDICTS = {"complete", "partial", "blocked", "not-run"}
SECRET_KEYS = {"api_key", "apikey", "token", "access_token", "authorization",
               "password", "secret", "client_secret"}
PLACEHOLDERS = {"", "unresolved", "unknown", "not provided", "not-provided", "not-checked", "not-run"}


def nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def supplied(value: Any) -> bool:
    return isinstance(value, str) and value.strip().casefold() not in PLACEHOLDERS


def _secret_paths(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key).casefold() in SECRET_KEYS:
                found.append(path)
            found.extend(_secret_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_secret_paths(child, f"{prefix}[{index}]"))
    return found


def validate(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root must be an object"]
    for path in _secret_paths(data):
        errors.append(f"secret-bearing key is forbidden: {path}")
    if not QUERY_ID.fullmatch(str(data.get("id", ""))):
        errors.append("id must match QRY-[0-9]{3,8}")
    if data.get("mode") not in MODES:
        errors.append(f"mode must be one of {sorted(MODES)}")
    scope = data.get("scope")
    if scope not in {"targeted", "exhaustive"}:
        errors.append("scope must be targeted or exhaustive")
    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        errors.append(f"verdict must be one of {sorted(VERDICTS)}")
    for field in ("contract", "source", "plan", "counts"):
        if not isinstance(data.get(field), dict):
            errors.append(f"{field} must be an object")
    pages = data.get("pages")
    if not isinstance(pages, list):
        errors.append("pages must be a list")
        pages = []
    cumulative = 0
    request_ids: set[str] = set()
    for index, page in enumerate(pages):
        prefix = f"pages[{index}]"
        if not isinstance(page, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ("request_id", "position", "requested", "returned",
                      "cumulative", "status", "next_state"):
            if field not in page:
                errors.append(f"{prefix}.{field} is required")
        returned = page.get("returned")
        requested = page.get("requested")
        request_id = page.get("request_id")
        if not supplied(request_id) or request_id in request_ids:
            errors.append(f"{prefix}.request_id must be non-empty and unique")
        else:
            request_ids.add(request_id)
        if not nonnegative_int(requested):
            errors.append(f"{prefix}.requested must be non-negative integer")
        if not nonnegative_int(returned):
            errors.append(f"{prefix}.returned must be non-negative integer")
        else:
            if nonnegative_int(requested) and returned > requested:
                errors.append(f"{prefix}.returned exceeds requested count")
            cumulative += returned
            if page.get("cumulative") != cumulative:
                errors.append(f"{prefix}.cumulative does not reconcile")
    counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
    for field in ("server_retrieved", "local_filtered", "deduplicated", "final"):
        value = counts.get(field)
        if not nonnegative_int(value):
            errors.append(f"counts.{field} must be non-negative integer")
    if counts.get("server_retrieved") != cumulative:
        errors.append("counts.server_retrieved does not equal page cumulative total")
    if all(nonnegative_int(counts.get(f)) for f in
           ("server_retrieved", "local_filtered", "deduplicated", "final")):
        if not (
            counts["server_retrieved"] >= counts["local_filtered"]
            >= counts["deduplicated"] >= counts["final"]
        ):
            errors.append("count reconciliation must be monotonically non-increasing")
    for field in ("identifier_conversions", "failures", "coverage_limits",
                  "unresolved", "handoff"):
        if not isinstance(data.get(field), list):
            errors.append(f"{field} must be a list")
    plan = data.get("plan") if isinstance(data.get("plan"), dict) else {}
    if verdict == "complete":
        if not pages:
            errors.append("complete verdict requires execution page records, including a zero-result response")
        if data.get("unresolved") or data.get("failures"):
            errors.append("complete verdict cannot contain unresolved items or failures")
        for section, fields in (
            ("contract", ("target", "deduplication_key")),
            ("source", ("database", "api_version_or_date", "documentation_locator")),
            ("plan", ("endpoint", "method", "pagination", "stable_sort")),
        ):
            record = data.get(section) if isinstance(data.get(section), dict) else {}
            for field in fields:
                if not supplied(record.get(field)):
                    errors.append(f"complete verdict requires resolved {section}.{field}")
        contract = data.get("contract") if isinstance(data.get("contract"), dict) else {}
        if not isinstance(contract.get("fields"), list) or not contract["fields"] or not all(
            supplied(field) for field in contract["fields"]
        ):
            errors.append("complete verdict requires requested output fields")
        source = data.get("source") if isinstance(data.get("source"), dict) else {}
        if source.get("authentication_mode") not in {"anonymous", "authenticated"}:
            errors.append("complete verdict requires the observed authentication mode")
        if any(page.get("status") != "success" for page in pages if isinstance(page, dict)):
            errors.append("complete query requires all pages successful")
        offset_pagination = isinstance(plan.get("pagination"), str) and bool(
            re.search(r"\boffset\b", plan["pagination"], re.I)
        )
        expected_offset = 0
        previous_page: dict[str, Any] | None = None
        for index, page in enumerate(pages):
            if not isinstance(page, dict):
                continue
            position = page.get("position")
            if previous_page is not None and previous_page.get("next_state") != position:
                errors.append(f"pages[{index}].position does not follow the preceding next_state")
            if offset_pagination:
                if not nonnegative_int(position) or position != expected_offset:
                    errors.append(f"pages[{index}].position must cover the next contiguous offset {expected_offset}")
                if nonnegative_int(page.get("returned")):
                    expected_offset += page["returned"]
                if index < len(pages) - 1 and (
                    not nonnegative_int(page.get("next_state")) or page["next_state"] != expected_offset
                ):
                    errors.append(f"pages[{index}].next_state must equal the next contiguous offset")
            previous_page = page
        if scope == "exhaustive":
            expected = counts.get("expected")
            if not nonnegative_int(expected) or expected != counts.get("server_retrieved"):
                errors.append("complete exhaustive query requires reconciled expected count")
            if data.get("next_state") not in (None, "", "done"):
                errors.append("complete exhaustive query cannot have a remaining next state")
            if pages and isinstance(pages[-1], dict) and pages[-1].get("next_state") not in (None, "", "done"):
                errors.append("complete exhaustive query requires the final page to be terminal")
    for field, used in (("request_budget", len(pages)), ("record_budget", cumulative)):
        budget = plan.get(field)
        if not nonnegative_int(budget):
            errors.append(f"plan.{field} must be a non-negative integer")
        elif used > budget:
            errors.append(f"execution exceeds plan.{field}")
    if verdict == "not-run" and pages:
        errors.append("not-run verdict cannot contain page records")
    if verdict == "blocked" and not (data.get("failures") or data.get("unresolved")):
        errors.append("blocked verdict requires failures or unresolved items")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.artifact.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2
    errors = validate(data)
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
