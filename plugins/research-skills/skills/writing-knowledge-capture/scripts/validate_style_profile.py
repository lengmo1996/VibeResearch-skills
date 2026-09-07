#!/usr/bin/env python3
"""Validate a privacy-bounded author-style profile without modifying it."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PROFILE_ID = re.compile(r"^WSP-[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
TRAIT_ID = re.compile(r"^TR-[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
STATUSES = {"pending_review", "approved", "rejected"}
DEDUP_RESULTS = {"exact", "near", "semantic", "unknown"}
FORBIDDEN_KEYS = {
    "raw_text",
    "sample_text",
    "full_text",
    "document_content",
    "full_prompt",
    "chat_history",
    "messages",
}


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _forbidden_key_paths(value: Any, prefix: str = "$") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}"
            if str(key).lower() in FORBIDDEN_KEYS:
                paths.append(path)
            paths.extend(_forbidden_key_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_forbidden_key_paths(child, f"{prefix}[{index}]"))
    return paths


def validate(profile: dict[str, Any], *, new_record: bool = False) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "profile_id",
        "status",
        "scope",
        "traits",
        "terminology",
        "source_refs",
        "privacy",
        "deduplication",
        "created_at",
        "decision",
    }
    missing = sorted(required - profile.keys())
    if missing:
        return [f"missing required fields: {', '.join(missing)}"]
    if profile["schema_version"] != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    if not isinstance(profile["profile_id"], str) or not PROFILE_ID.fullmatch(
        profile["profile_id"]
    ):
        errors.append("profile_id must match WSP-<stable-id>")
    if profile["status"] not in STATUSES:
        errors.append(f"status must be one of {sorted(STATUSES)}")
    if new_record and profile["status"] != "pending_review":
        errors.append("a new profile must have status pending_review")
    if not nonempty(profile["created_at"]):
        errors.append("created_at must be a non-empty string")

    scope = profile["scope"]
    if not isinstance(scope, dict):
        errors.append("scope must be an object")
    else:
        for field in ("language", "genre", "avoid_when"):
            if not nonempty(scope.get(field)):
                errors.append(f"scope.{field} must be a non-empty string")
        for field in ("domains", "applicable_sections"):
            if not isinstance(scope.get(field), list):
                errors.append(f"scope.{field} must be a list")

    traits = profile["traits"]
    seen_traits: set[str] = set()
    if not isinstance(traits, list) or not traits:
        errors.append("traits must be a non-empty list")
        traits = []
    for index, trait in enumerate(traits, 1):
        if not isinstance(trait, dict):
            errors.append(f"trait {index}: must be an object")
            continue
        trait_id = trait.get("trait_id")
        if not isinstance(trait_id, str) or not TRAIT_ID.fullmatch(trait_id):
            errors.append(f"trait {index}: trait_id must match TR-<stable-id>")
        elif trait_id in seen_traits:
            errors.append(f"{trait_id}: duplicate trait_id")
        else:
            seen_traits.add(trait_id)
        for field in ("dimension", "preference"):
            if not nonempty(trait.get(field)):
                errors.append(f"trait {index}: {field} must be a non-empty string")
        confidence = trait.get("confidence")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            errors.append(f"trait {index}: confidence must be numeric in [0, 1]")
        evidence = trait.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"trait {index}: evidence must be a non-empty list")
        else:
            for item in evidence:
                if not isinstance(item, dict) or not all(
                    nonempty(item.get(field)) for field in ("source_id", "locator")
                ):
                    errors.append(
                        f"trait {index}: evidence needs source_id and locator"
                    )
                    break

    source_refs = profile["source_refs"]
    if not isinstance(source_refs, list) or not source_refs:
        errors.append("source_refs must be a non-empty list")
    else:
        source_ids: set[str] = set()
        for index, source in enumerate(source_refs, 1):
            if not isinstance(source, dict):
                errors.append(f"source {index}: must be an object")
                continue
            source_id = source.get("source_id")
            if not nonempty(source_id) or source_id in source_ids:
                errors.append(f"source {index}: source_id must be unique and non-empty")
            else:
                source_ids.add(source_id)
            if not nonempty(source.get("origin")):
                errors.append(f"source {index}: origin must be non-empty")
            if source.get("author_owned") is not True:
                errors.append(f"source {index}: author_owned must be true")

    privacy = profile["privacy"]
    if not isinstance(privacy, dict):
        errors.append("privacy must be an object")
    else:
        for field in ("raw_sample_stored", "long_excerpt_stored", "full_prompt_stored"):
            if privacy.get(field) is not False:
                errors.append(f"privacy.{field} must be false")
        if privacy.get("retention") != "abstract-traits-and-source-refs-only":
            errors.append("privacy.retention must be abstract-traits-and-source-refs-only")

    deduplication = profile["deduplication"]
    if not isinstance(deduplication, dict):
        errors.append("deduplication must be an object")
    else:
        if not nonempty(deduplication.get("scope")):
            errors.append("deduplication.scope must be non-empty")
        if deduplication.get("result") not in DEDUP_RESULTS:
            errors.append(f"deduplication.result must be one of {sorted(DEDUP_RESULTS)}")
        if not isinstance(deduplication.get("matched_profile_ids"), list):
            errors.append("deduplication.matched_profile_ids must be a list")

    decision = profile["decision"]
    if profile["status"] == "pending_review":
        if decision is not None:
            errors.append("pending_review profile must not contain a decision")
    elif not isinstance(decision, dict):
        errors.append("approved/rejected profile must contain a decision object")
    else:
        expected = "approve" if profile["status"] == "approved" else "reject"
        if decision.get("action") != expected:
            errors.append(f"decision.action must be {expected}")
        for field in ("actor", "decided_at", "evidence", "prior_status"):
            if not nonempty(decision.get(field)):
                errors.append(f"decision.{field} must be a non-empty string")
        if decision.get("prior_status") != "pending_review":
            errors.append("decision.prior_status must be pending_review")

    for path in _forbidden_key_paths(profile):
        errors.append(f"forbidden raw-content field: {path}")
    return errors


def self_test() -> int:
    template = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "author-style-profile.example.json"
    )
    profile = json.loads(template.read_text(encoding="utf-8"))
    if validate(profile, new_record=True):
        print("self-test failed: valid profile rejected", file=sys.stderr)
        return 1
    unsafe = dict(profile)
    unsafe["sample_text"] = "raw sample"
    if not validate(unsafe, new_record=True):
        print("self-test failed: raw sample accepted", file=sys.stderr)
        return 1
    print("validate_style_profile self-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", nargs="?", type=Path)
    parser.add_argument("--new-record", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.profile is None:
        parser.error("profile is required unless --self-test is used")
    try:
        value = json.loads(args.profile.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"cannot read profile: {exc}", file=sys.stderr)
        return 2
    if not isinstance(value, dict):
        print("profile must be a JSON object", file=sys.stderr)
        return 2
    errors = validate(value, new_record=args.new_record)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"profile valid: {value['profile_id']} ({value['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
