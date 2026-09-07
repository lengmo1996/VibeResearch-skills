#!/usr/bin/env python3
"""Validate a submission manifest and optionally inspect a package root read-only."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any


ID_PATTERNS = {
    "submission": re.compile(r"^SUB-\d{3,}$"),
    "rule": re.compile(r"^RULE-\d{3,}$"),
    "artifact": re.compile(r"^ART-\d{3,}$"),
    "check": re.compile(r"^CHK-\d{3,}$"),
    "finding": re.compile(r"^FIND-\d{3,}$"),
}
MODES = {"conference", "journal", "camera-ready", "arxiv"}
RULE_CLASSES = {"hard", "soft"}
RULE_STATUSES = {"passed", "failed", "unresolved", "not-applicable"}
ARTIFACT_STATUSES = {"present", "inspected", "missing", "not-provided"}
CHECK_RESULTS = {"passed", "failed", "blocked", "not-run"}
SEVERITIES = {"Blocker", "Major", "Minor", "Polish"}
VERDICTS = {"Ready", "Conditionally ready", "Not ready", "Blocked"}
UNRESOLVED_TEXT = {"not provided", "not checked", "unclear", "unknown", "tbd", "todo"}


def _resolved_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value.strip().casefold() not in UNRESOLVED_TEXT
    )


def _index(
    errors: list[str],
    records: Any,
    label: str,
    pattern: re.Pattern[str],
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    if not isinstance(records, list):
        errors.append(f"{label} must be a list")
        return indexed
    for position, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"{label}[{position}] must be an object")
            continue
        record_id = record.get("id")
        if not isinstance(record_id, str) or not pattern.fullmatch(record_id):
            errors.append(f"{label}[{position}].id is invalid")
            continue
        if record_id in indexed:
            errors.append(f"duplicate {label} ID: {record_id}")
        indexed[record_id] = record
    return indexed


def _refs(
    errors: list[str],
    record_id: str,
    field: str,
    values: Any,
    known: set[str],
) -> None:
    if not isinstance(values, list) or not values:
        errors.append(f"{record_id}.{field} must be a non-empty list")
        return
    for value in values:
        if value not in known:
            errors.append(f"{record_id}.{field} references unknown ID: {value}")


def _contained(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def validate_manifest(data: Any, package_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest must be a JSON object"]
    expected_keys = {
        "schema_version",
        "submission",
        "rules",
        "artifacts",
        "checks",
        "findings",
        "verdict",
    }
    if set(data) != expected_keys:
        errors.append("manifest top-level fields do not match the 1.0.0 contract")
    if data.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")

    submission = data.get("submission")
    if not isinstance(submission, dict):
        errors.append("submission must be an object")
    else:
        submission_id = submission.get("id")
        if (
            not isinstance(submission_id, str)
            or not ID_PATTERNS["submission"].fullmatch(submission_id)
        ):
            errors.append("submission.id must match SUB-###")
        if submission.get("mode") not in MODES:
            errors.append("submission.mode is invalid")

    rules = _index(errors, data.get("rules"), "rules", ID_PATTERNS["rule"])
    artifacts = _index(
        errors, data.get("artifacts"), "artifacts", ID_PATTERNS["artifact"]
    )
    checks = _index(errors, data.get("checks"), "checks", ID_PATTERNS["check"])
    findings = _index(
        errors, data.get("findings"), "findings", ID_PATTERNS["finding"]
    )

    for rule_id, rule in rules.items():
        if rule.get("class") not in RULE_CLASSES:
            errors.append(f"{rule_id}.class is invalid")
        if rule.get("status") not in RULE_STATUSES:
            errors.append(f"{rule_id}.status is invalid")
        for field in ("requirement", "source", "effective_cycle", "retrieved_at"):
            if not isinstance(rule.get(field), str) or not rule[field].strip():
                errors.append(f"{rule_id}.{field} is required")
        if not isinstance(rule.get("applicable"), bool):
            errors.append(f"{rule_id}.applicable must be boolean")

    resolved_root = package_root.resolve() if package_root is not None else None
    for artifact_id, artifact in artifacts.items():
        if artifact.get("status") not in ARTIFACT_STATUSES:
            errors.append(f"{artifact_id}.status is invalid")
        if not isinstance(artifact.get("required"), bool):
            errors.append(f"{artifact_id}.required must be boolean")
        raw_path = artifact.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            errors.append(f"{artifact_id}.path is required")
            continue
        pure_path = PurePosixPath(raw_path.replace("\\", "/"))
        if pure_path.is_absolute() or ".." in pure_path.parts:
            errors.append(f"{artifact_id}.path must be relative and contained")
            continue
        digest = artifact.get("sha256", "")
        if digest and (
            not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest)
        ):
            errors.append(f"{artifact_id}.sha256 is invalid")
        if resolved_root is not None:
            candidate = (resolved_root / raw_path).resolve()
            if not _contained(resolved_root, candidate):
                errors.append(f"{artifact_id}.path resolves outside package root")
                continue
            if artifact.get("status") in {"present", "inspected"}:
                if not candidate.is_file():
                    errors.append(f"{artifact_id} is marked present but file is missing")
                elif digest:
                    observed = hashlib.sha256(candidate.read_bytes()).hexdigest()
                    if observed.lower() != digest.lower():
                        errors.append(f"{artifact_id}.sha256 does not match file content")

    for check_id, check in checks.items():
        _refs(errors, check_id, "rule_ids", check.get("rule_ids"), set(rules))
        _refs(
            errors,
            check_id,
            "artifact_ids",
            check.get("artifact_ids"),
            set(artifacts),
        )
        if check.get("result") not in CHECK_RESULTS:
            errors.append(f"{check_id}.result is invalid")
        if not isinstance(check.get("evidence"), str) or not check["evidence"].strip():
            errors.append(f"{check_id}.evidence is required")

    for finding_id, finding in findings.items():
        _refs(errors, finding_id, "rule_ids", finding.get("rule_ids"), set(rules))
        _refs(
            errors,
            finding_id,
            "artifact_ids",
            finding.get("artifact_ids"),
            set(artifacts),
        )
        _refs(errors, finding_id, "check_ids", finding.get("check_ids"), set(checks))
        if finding.get("severity") not in SEVERITIES:
            errors.append(f"{finding_id}.severity is invalid")
        for field in ("location", "evidence", "action", "recheck"):
            if not isinstance(finding.get(field), str) or not finding[field].strip():
                errors.append(f"{finding_id}.{field} is required")

    verdict = data.get("verdict")
    if not isinstance(verdict, dict):
        errors.append("verdict must be an object")
        return errors
    status = verdict.get("status")
    if status not in VERDICTS:
        errors.append("verdict.status is invalid")
    if not isinstance(verdict.get("rationale"), str) or not verdict["rationale"].strip():
        errors.append("verdict.rationale is required")
    if not isinstance(verdict.get("portal_identity_confirmed"), bool):
        errors.append("verdict.portal_identity_confirmed must be boolean")

    if status in {"Ready", "Conditionally ready"}:
        for label, records in (("rules", rules), ("artifacts", artifacts), ("checks", checks)):
            if not records:
                errors.append(f"{status} requires non-empty {label}")
        if isinstance(submission, dict):
            for field in ("venue", "cycle", "track", "phase", "portal"):
                if not _resolved_text(submission.get(field)):
                    errors.append(f"{status} requires resolved submission.{field}")
        hard_rule_ids = {
            rule_id
            for rule_id, rule in rules.items()
            if rule.get("class") == "hard" and rule.get("applicable") is True
        }
        for rule_id in hard_rule_ids:
            if rules[rule_id].get("status") != "passed":
                errors.append(f"{status} requires hard rule passed: {rule_id}")
            for field in ("requirement", "source", "effective_cycle", "retrieved_at"):
                if not _resolved_text(rules[rule_id].get(field)):
                    errors.append(f"{status} requires resolved {rule_id}.{field}")
            covered = any(
                rule_id in check.get("rule_ids", [])
                and check.get("result") == "passed"
                for check in checks.values()
            )
            if not covered:
                errors.append(f"{status} requires a passed check for hard rule: {rule_id}")
            if any(
                rule_id in check.get("rule_ids", [])
                and check.get("result") != "passed"
                for check in checks.values()
            ):
                errors.append(f"{status} cannot include failed or incomplete checks for hard rule: {rule_id}")
        for artifact_id, artifact in artifacts.items():
            if artifact.get("required") and artifact.get("status") != "inspected":
                errors.append(f"{status} requires required artifact inspected: {artifact_id}")
        if any(finding.get("severity") == "Blocker" for finding in findings.values()):
            errors.append(f"{status} cannot include Blocker findings")
    if status == "Ready":
        if any(
            finding.get("severity") in {"Blocker", "Major"}
            for finding in findings.values()
        ):
            errors.append("Ready cannot include Blocker or Major findings")
        if not verdict.get("portal_identity_confirmed"):
            errors.append("Ready requires portal_identity_confirmed: true")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    sample_path = Path(__file__).resolve().parents[1] / "templates" / "submission_manifest.json"
    if args.self_test:
        sample = json.loads(sample_path.read_text(encoding="utf-8"))
        invalid_ready = json.loads(json.dumps(sample))
        invalid_ready["verdict"]["status"] = "Ready"
        traversal = json.loads(json.dumps(sample))
        traversal["artifacts"][0]["path"] = "../paper.pdf"
        if (
            validate_manifest(sample)
            or not validate_manifest(invalid_ready)
            or not validate_manifest(traversal)
        ):
            print("Self-test failed.", file=sys.stderr)
            return 1
        print("Self-test passed.")
        return 0
    if args.manifest is None:
        parser.error("provide a manifest path or use --self-test")
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"unable to read manifest: {exc}", file=sys.stderr)
        return 2
    errors = validate_manifest(data, args.package_root)
    if errors:
        print(f"Submission manifest validation failed ({len(errors)} issue(s)):")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Submission manifest is structurally valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
