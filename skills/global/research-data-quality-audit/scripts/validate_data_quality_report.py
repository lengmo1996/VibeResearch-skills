#!/usr/bin/env python3
"""Validate a data-quality report without reading or modifying source data."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


AUDIT_ID = re.compile(r"^DQA-[0-9]{3,8}$")
FINDING_ID = re.compile(r"^DQ-[0-9]{3,8}$")
VERDICTS = {"fit", "conditional", "not-fit", "not-evaluable"}
SEVERITIES = {"critical", "high", "medium", "low", "info"}
UNKNOWN = {"", "unknown", "unresolved", "tbd", "n/a", "not provided / unclear"}


def _resolved_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() not in UNKNOWN


def _has_evidence(value: Any) -> bool:
    return _resolved_text(value) or (
        isinstance(value, list) and bool(value) and all(_resolved_text(item) for item in value)
    )


def validate(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root must be an object"]
    if not AUDIT_ID.fullmatch(str(data.get("audit_id", ""))):
        errors.append("audit_id must match DQA-[0-9]{3,8}")
    if not isinstance(data.get("assets"), list) or not data["assets"]:
        errors.append("assets must be a non-empty list")
    coverage = data.get("coverage")
    if not isinstance(coverage, dict):
        errors.append("coverage must be an object")
        coverage = {}
    for field in ("method", "complete", "rows_or_records_scanned",
                  "total_rows_or_records", "fields_scanned", "truncated",
                  "unsupported_surfaces"):
        if field not in coverage:
            errors.append(f"coverage.{field} is required")
    scanned = coverage.get("rows_or_records_scanned")
    total = coverage.get("total_rows_or_records")
    if isinstance(scanned, bool) or not isinstance(scanned, int) or scanned < 0:
        errors.append("coverage.rows_or_records_scanned must be non-negative integer")
    if total is not None and (
        isinstance(total, bool) or not isinstance(total, int) or total < 0
    ):
        errors.append("coverage.total_rows_or_records must be null or non-negative integer")
    if coverage.get("complete") and (
        coverage.get("truncated") or total is None or scanned != total
    ):
        errors.append("complete coverage requires untruncated scanned count equal to total")
    if not isinstance(data.get("rule_registry"), list):
        errors.append("rule_registry must be a list")
    findings = data.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
        findings = []
    ids: set[str] = set()
    for index, finding in enumerate(findings):
        prefix = f"findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{prefix} must be an object")
            continue
        finding_id = str(finding.get("id", ""))
        if not FINDING_ID.fullmatch(finding_id):
            errors.append(f"{prefix}.id must match DQ-[0-9]{{3,8}}")
        elif finding_id in ids:
            errors.append(f"{prefix}.id duplicates {finding_id}")
        ids.add(finding_id)
        for field in ("rule_id", "severity", "evidence", "denominator",
                      "affected_scope", "confidence", "impact", "remediation",
                      "verification"):
            if field not in finding:
                errors.append(f"{prefix}.{field} is required")
        if finding.get("severity") not in SEVERITIES:
            errors.append(f"{prefix}.severity must be one of {sorted(SEVERITIES)}")
    fitness = data.get("fitness")
    if not isinstance(fitness, dict):
        errors.append("fitness must be an object")
        fitness = {}
    verdict = fitness.get("verdict")
    if verdict not in VERDICTS:
        errors.append(f"fitness.verdict must be one of {sorted(VERDICTS)}")
    blockers = fitness.get("blocking_finding_ids")
    if not isinstance(blockers, list):
        errors.append("fitness.blocking_finding_ids must be a list")
        blockers = []
    for blocker in blockers:
        if blocker not in ids:
            errors.append(f"fitness blocker {blocker} does not reference a finding")
    if verdict == "fit" and blockers:
        errors.append("fit verdict cannot have blocking findings")
    if verdict == "not-fit" and not blockers:
        errors.append("not-fit verdict requires at least one blocking finding")
    privacy = data.get("privacy")
    if not isinstance(privacy, dict):
        errors.append("privacy must be an object")
    elif privacy.get("raw_rows_exposed") or privacy.get("direct_identifiers_exposed"):
        errors.append("report must not expose raw rows or direct identifiers")
    for field in ("limitations", "unresolved", "handoff"):
        if not isinstance(data.get(field), list):
            errors.append(f"{field} must be a list")
    if verdict == "fit" and data.get("unresolved"):
        errors.append("fit verdict cannot contain unresolved items")
    if verdict == "fit":
        for field in ("stated_use", "authorization", "observational_unit"):
            if not _resolved_text(data.get(field)):
                errors.append(f"fit verdict requires resolved {field}")
        for index, asset in enumerate(data.get("assets", []) if isinstance(data.get("assets"), list) else []):
            if not isinstance(asset, dict):
                errors.append(f"assets[{index}] must be an object")
                continue
            for field in ("asset_id", "version", "format", "source_locator"):
                if not _resolved_text(asset.get(field)):
                    errors.append(f"fit verdict requires resolved assets[{index}].{field}")
        if not _resolved_text(coverage.get("method")):
            errors.append("fit verdict requires a resolved coverage.method")
        fields_scanned = coverage.get("fields_scanned")
        if isinstance(fields_scanned, bool) or not isinstance(fields_scanned, int) or fields_scanned < 0:
            errors.append("coverage.fields_scanned must be a non-negative integer")
        inspected = any(isinstance(value, int) and not isinstance(value, bool) and value > 0
                        for value in (scanned, fields_scanned))
        if not inspected:
            errors.append("fit verdict requires inspected records or fields")
        if not _resolved_text(fitness.get("scope_limit")):
            errors.append("fit verdict requires a resolved fitness.scope_limit")
        rules = data.get("rule_registry")
        critical_rules: set[str] = set()
        rule_ids: set[str] = set()
        for index, rule in enumerate(rules if isinstance(rules, list) else []):
            if not isinstance(rule, dict):
                errors.append(f"rule_registry[{index}] must be an object")
                continue
            rule_id = rule.get("rule_id")
            if not _resolved_text(rule_id):
                errors.append(f"rule_registry[{index}].rule_id must be resolved")
                continue
            if rule_id in rule_ids:
                errors.append(f"duplicate rule_id: {rule_id}")
            rule_ids.add(rule_id)
            if not isinstance(rule.get("critical"), bool):
                errors.append(f"rule_registry[{index}].critical must be a boolean")
            if rule.get("status") not in {"pass", "fail", "unknown", "not-applicable"}:
                errors.append(f"rule_registry[{index}].status is invalid")
            if rule.get("critical") is True:
                critical_rules.add(rule_id)
                if rule.get("status") != "pass":
                    errors.append(f"fit verdict requires critical rule {rule_id} to pass")
                if not _has_evidence(rule.get("evidence")) or not _resolved_text(rule.get("scope")):
                    errors.append(f"fit verdict requires critical rule {rule_id} evidence and scope")
        if not critical_rules:
            errors.append("fit verdict requires declared critical rules with coverage evidence")
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            rule_id = finding.get("rule_id")
            if not isinstance(rule_id, str) or rule_id not in rule_ids:
                errors.append("fit verdict requires each finding to reference a registered rule")
            if finding.get("severity") == "critical" or (isinstance(rule_id, str) and rule_id in critical_rules):
                errors.append("fit verdict cannot contain a critical finding or a finding against a critical rule")
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
