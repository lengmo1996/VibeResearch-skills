#!/usr/bin/env python3
"""Validate a saved result-analysis Markdown report."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HEADINGS = (
    "## Scope and protocol gate",
    "## Normalized observations",
    "## Findings and explanations",
    "## Claim assessments",
    "## Failures, anomalies, and ablations",
    "## Next discriminating checks",
    "## Risks and unresolved items",
    "## Handoff",
)
CLAIM_STATUSES = {
    "supported",
    "partially-supported",
    "not-supported",
    "contradicted",
    "inconclusive",
}
SHARED_CLAIM_STATUSES = {"proposed", "partial", "supported", "contradicted"}
EVIDENCE_KINDS = {
    "paper",
    "result",
    "table",
    "figure",
    "equation",
    "assumption",
    "user-provided",
}
EVIDENCE_STATUSES = {"candidate", "verified", "missing", "contradictory"}
ANALYSIS_STATUSES = CLAIM_STATUSES
ANALYSIS_PROJECTION = {
    "supported": ("supported", {"verified"}),
    "partially-supported": ("partial", {"verified"}),
    "not-supported": ("proposed", {"missing"}),
    "contradicted": ("contradicted", {"contradictory"}),
    "inconclusive": ("proposed", {"candidate", "missing"}),
}
STATISTICAL_HEADINGS = (
    "## Scope and data sufficiency",
    "## Assumption checks",
    "## Effect and uncertainty",
    "## Multiplicity and selection",
    "## Reproducibility coverage",
    "## Verdicts",
    "## Risks and next checks",
)
STATISTICAL_SCOPE_FIELDS = (
    "Modes",
    "Claim/experiment IDs",
    "Protocol/metric IDs",
    "Analysis unit",
    "Planned or post-hoc",
    "Runs expected/observed/missing/failed",
    "Seed coverage",
    "Raw inputs available",
    "Original decision rule",
)
ASSUMPTION_STATES = {"pass", "fail", "unknown", "not-applicable"}
VALIDITY_VERDICTS = {
    "supported",
    "partial",
    "contradicted",
    "inconclusive",
    "not-evaluable",
}
RESULT_REF_IDS = (
    re.compile(r"\bRUN-[A-Za-z0-9._-]+\b"),
    re.compile(r"\bEXP-\d{3,}\b"),
    re.compile(r"\bPROT-[A-Za-z0-9._-]+\b"),
    re.compile(r"\bMET-\d{3,}\b"),
    re.compile(r"\bFIND-\d{3,}\b"),
)


def validate(text: str) -> list[str]:
    errors: list[str] = []
    if not text.startswith("# Result Analysis Report"):
        errors.append("report must start with '# Result Analysis Report'")
    for heading in HEADINGS:
        if heading not in text:
            errors.append(f"missing required heading: {heading}")
    if not re.search(r"\bOBS-\d{3,}\b", text):
        errors.append("missing OBS-### record")
    if not re.search(r"\bFIND-\d{3,}\b", text):
        errors.append("missing FIND-### record")
    claims = re.findall(
        r"\|\s*(?:CLM|CLAIM)-\d{3,}\s*\|"
        r"[^|\n]*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|\s*([^|\n]+?)\s*\|",
        text,
    )
    if not claims:
        claims = re.findall(
            r"\|\s*CLAIM-\d{3,}\s*\|[^|\n]*\|[^|\n]*\|\s*([^|\n]+?)\s*\|",
            text,
        )
    if not claims:
        errors.append("missing CLAIM-### assessment")
    for status in claims:
        if status.strip().lower() not in CLAIM_STATUSES:
            errors.append(f"invalid claim status: {status.strip()}")
    return errors


def validate_claim_patch(data: Any) -> list[str]:
    """Validate the shared contract subset and result identity linkage."""

    errors: list[str] = []
    if not isinstance(data, dict):
        return ["claim patch must be a JSON object"]
    if set(data) != {"schema_version", "claims"}:
        errors.append("claim patch fields must be exactly schema_version and claims")
    if data.get("schema_version") != "1.0.0":
        errors.append("claim patch schema_version must be 1.0.0")
    claims = data.get("claims")
    if not isinstance(claims, list) or not claims:
        errors.append("claim patch claims must be a non-empty list")
        return errors
    for index, claim in enumerate(claims):
        label = f"claims[{index}]"
        if not isinstance(claim, dict):
            errors.append(f"{label} must be an object")
            continue
        allowed_claim_fields = {"claim_id", "text", "status", "scope", "evidence_refs"}
        if not set(claim).issubset(allowed_claim_fields):
            errors.append(f"{label} contains unsupported fields")
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not re.fullmatch(r"CLM-\d{3,}", claim_id):
            errors.append(f"{label}.claim_id must match CLM-###")
        if not isinstance(claim.get("text"), str) or not claim["text"].strip():
            errors.append(f"{label}.text is required")
        if claim.get("status") not in SHARED_CLAIM_STATUSES:
            errors.append(f"{label}.status is invalid")
        evidence_refs = claim.get("evidence_refs")
        if not isinstance(evidence_refs, list):
            errors.append(f"{label}.evidence_refs must be a list")
            continue
        result_ref_found = False
        for evidence_index, evidence in enumerate(evidence_refs):
            evidence_label = f"{label}.evidence_refs[{evidence_index}]"
            if not isinstance(evidence, dict):
                errors.append(f"{evidence_label} must be an object")
                continue
            if evidence.get("kind") not in EVIDENCE_KINDS:
                errors.append(f"{evidence_label}.kind is invalid")
            if evidence.get("status") not in EVIDENCE_STATUSES:
                errors.append(f"{evidence_label}.status is invalid")
            ref = evidence.get("ref")
            if not isinstance(ref, str) or not ref:
                errors.append(f"{evidence_label}.ref is required")
            elif evidence.get("kind") == "result":
                result_ref_found = True
                for pattern in RESULT_REF_IDS:
                    if not pattern.search(ref):
                        errors.append(
                            f"{evidence_label}.ref is missing identity {pattern.pattern}"
                        )
            note = evidence.get("note")
            if evidence.get("kind") == "result":
                statuses = re.findall(r"\banalysis_status=([^;\s]+)", note) if isinstance(note, str) else []
                if len(statuses) != 1 or statuses[0] not in ANALYSIS_PROJECTION:
                    errors.append(
                        f"{evidence_label}.note must preserve exactly one valid analysis_status"
                    )
                else:
                    expected_claim, expected_evidence = ANALYSIS_PROJECTION[statuses[0]]
                    if claim.get("status") != expected_claim:
                        errors.append(
                            f"{label}.status conflicts with analysis_status={statuses[0]}: "
                            f"expected {expected_claim}"
                        )
                    if evidence.get("status") not in expected_evidence:
                        errors.append(
                            f"{evidence_label}.status conflicts with analysis_status={statuses[0]}: "
                            f"expected one of {sorted(expected_evidence)}"
                        )
        if not result_ref_found:
            errors.append(f"{label} must include a result evidence reference")
    return errors


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    next_heading = text.find("\n## ", start + len(heading))
    return text[start:next_heading] if next_heading >= 0 else text[start:]


def _table_rows(section: str) -> list[list[str]]:
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    return [
        row
        for row in rows[2:]
        if row and not all(set(cell) <= {"-", ":"} for cell in row)
    ]


def validate_statistical_report(text: str) -> list[str]:
    """Validate statistical/reproducibility completeness without recomputing results."""

    errors: list[str] = []
    if not text.startswith("# Statistical Validity and Reproducibility Report"):
        errors.append(
            "statistical report must start with "
            "'# Statistical Validity and Reproducibility Report'"
        )
    for heading in STATISTICAL_HEADINGS:
        if heading not in text:
            errors.append(f"missing required statistical heading: {heading}")
    scope = _section(text, "## Scope and data sufficiency")
    for field in STATISTICAL_SCOPE_FIELDS:
        if not re.search(
            rf"^-\s+{re.escape(field)}:\s*\S.+$", scope, re.MULTILINE
        ):
            errors.append(f"statistical scope missing or empty field '{field}'")

    assumption_rows = _table_rows(_section(text, "## Assumption checks"))
    if not assumption_rows:
        errors.append("statistical report requires at least one assumption check")
    for row in assumption_rows:
        if len(row) != 6:
            errors.append("assumption-check row must contain six fields")
            continue
        if row[4].lower() not in ASSUMPTION_STATES:
            errors.append(f"invalid assumption status: {row[4]}")

    reproducibility_rows = _table_rows(
        _section(text, "## Reproducibility coverage")
    )
    if not reproducibility_rows:
        errors.append("statistical report requires reproducibility coverage")
    for row in reproducibility_rows:
        if len(row) != 7:
            errors.append("reproducibility row must contain seven fields")
            continue
        if row[6].lower() not in VALIDITY_VERDICTS:
            errors.append(f"invalid reproducibility status: {row[6]}")

    verdict_rows = _table_rows(_section(text, "## Verdicts"))
    if not verdict_rows:
        errors.append("statistical report requires at least one claim verdict")
    for row in verdict_rows:
        if len(row) != 5:
            errors.append("verdict row must contain five fields")
            continue
        for label, value in (
            ("statistical", row[1]),
            ("reproducibility", row[2]),
        ):
            if value.lower() not in VALIDITY_VERDICTS:
                errors.append(f"invalid {label} verdict: {value}")
    return errors


VALID = """# Result Analysis Report
## Scope and protocol gate
Comparable.
## Normalized observations
| ID | Evidence |
|---|---|
| OBS-001 | run-1 |
## Findings and explanations
| ID | Obs |
|---|---|
| FIND-001 | OBS-001 |
## Claim assessments
| Claim ID | Claim | Finding IDs | Status | Wording |
|---|---|---|---|---|
| CLAIM-001 | bounded claim | FIND-001 | supported | evidence supports |
## Failures, anomalies, and ablations
None.
## Next discriminating checks
None.
## Risks and unresolved items
None.
## Handoff
Ready.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", nargs="?", type=Path)
    parser.add_argument("--claim-patch", type=Path)
    parser.add_argument("--statistical-report", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        patch_path = Path(__file__).resolve().parents[1] / "templates" / "claim_evidence_patch.json"
        patch = json.loads(patch_path.read_text(encoding="utf-8"))
        invalid_patch = json.loads(json.dumps(patch))
        invalid_patch["claims"][0]["evidence_refs"][0]["ref"] = "result://RUN-001"
        statistical_path = (
            Path(__file__).resolve().parents[1]
            / "templates"
            / "statistical-validity-report.md"
        )
        statistical_text = statistical_path.read_text(encoding="utf-8")
        invalid_statistical = statistical_text.replace(
            "| protocol artifact | unknown |",
            "| protocol artifact | assumed-pass |",
        )
        if (
            validate(VALID)
            or not validate("# Result Analysis Report")
            or validate_claim_patch(patch)
            or not validate_claim_patch(invalid_patch)
            or validate_statistical_report(statistical_text)
            or not validate_statistical_report(invalid_statistical)
        ):
            print("Self-test failed.", file=sys.stderr)
            return 1
        print("Self-test passed.")
        return 0
    if args.report is None and args.statistical_report is None:
        parser.error("provide a report path, --statistical-report, or use --self-test")
    errors: list[str] = []
    if args.report is not None:
        try:
            text = args.report.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"unable to read report: {exc}", file=sys.stderr)
            return 2
        errors.extend(validate(text))
    if args.claim_patch is not None:
        try:
            patch = json.loads(args.claim_patch.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"unable to read claim patch: {exc}", file=sys.stderr)
            return 2
        errors.extend(validate_claim_patch(patch))
    if args.statistical_report is not None:
        try:
            statistical_text = args.statistical_report.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"unable to read statistical report: {exc}", file=sys.stderr)
            return 2
        errors.extend(validate_statistical_report(statistical_text))
    if errors:
        print(f"Result analysis validation failed ({len(errors)} issue(s)):")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Result analysis report is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
