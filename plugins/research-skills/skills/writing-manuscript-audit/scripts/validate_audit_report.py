#!/usr/bin/env python3
"""Validate the structure of a saved manuscript-audit Markdown report."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_HEADINGS = (
    "## Audit scope and confidence",
    "## Executive summary",
    "## Unresolved items",
    "## Prioritized handoff",
)
REQUIRED_FINDING_FIELDS = (
    "Severity",
    "Category",
    "Location",
    "Observed content",
    "Evidence status",
    "Why it matters",
    "Suggested correction",
    "Verification",
    "Root cause",
)
FINDING_HEADING = re.compile(r"^###\s+(AUD-\d{3,})\b", re.MULTILINE)
SECTION_HEADING = re.compile(r"^##\s+", re.MULTILINE)
FIELD_LINE = re.compile(r"^-\s+([^:\n]+):\s*(.*)$", re.MULTILINE)
SEVERITY = re.compile(r"^S[0-3]\b")
ALLOWED_EVIDENCE_STATES = {
    "observed",
    "corroborated",
    "inference",
    "unresolved",
}
STRUCTURE_MODE = re.compile(
    r"^-\s+Selected modes:\s*.*\bstructure\b",
    re.MULTILINE | re.IGNORECASE,
)
REVERSE_OUTLINE_SECTION = re.compile(
    r"^## Reverse outline\s*$\n(.*?)(?=^##\s+|\Z)",
    re.MULTILINE | re.DOTALL,
)
REVERSE_OUTLINE_FIELDS = (
    "Locator",
    "Dominant function",
    "Claim or question",
    "Evidence/dependency",
    "Transition",
)
CLOSURE_REQUIRED_HEADINGS = (
    "## Closure scope",
    "## Finding transitions",
    "## Regressions and reopened findings",
    "## Closure summary",
)
CLOSURE_REQUIRED_FIELDS = (
    "Previous state",
    "Requested state",
    "Original location",
    "Revised location",
    "Claimed change",
    "Observed change",
    "Protected content",
    "Protected-content check",
    "Verification method",
    "Verification evidence",
    "Verification result",
    "New state",
    "Residual risk",
    "Linked regression IDs",
)
PROSE_REQUIRED_HEADINGS = (
    "## Audit scope and confidence",
    "## No authorship inference",
    "## Unresolved items",
    "## Prioritized handoff",
)
PROSE_REQUIRED_SCOPE_FIELDS = (
    "Materials reviewed",
    "Selected mode",
    "Usable prose sample",
    "Masked spans",
    "Diagnostic confidence",
    "Sample limitation",
)
PROSE_REQUIRED_FINDING_FIELDS = (
    "Severity",
    "Category",
    "Location",
    "Observed content",
    "Signal cluster",
    "Alternative explanation",
    "Evidence status",
    "Why it matters",
    "Suggested correction",
    "Protected scientific content",
    "Verification",
    "Root cause",
)
PROSE_CATEGORIES = {
    *(f"PS-{index:02d}" for index in range(1, 8)),
    *(f"AL-{index:02d}" for index in range(1, 6)),
}
PROSE_CONFIDENCE = {"high", "medium", "low", "insufficient-sample"}
PANEL_REQUIRED_HEADINGS = (
    "## Panel scope and independence",
    "## Independent reviewer records",
    "## Synthesis matrix",
    "## Minority and unresolved opinions",
    "## Prioritized handoff",
)
PANEL_SCOPE_FIELDS = (
    "Manuscript snapshot",
    "Shared materials",
    "Reviewer roles",
    "Execution status",
    "Isolation method",
    "Synthesis after independent records",
)
PANEL_REVIEWER_FIELDS = (
    "Focus",
    "Materials reviewed",
    "Evidence available",
    "Confidence",
    "Strengths",
    "Findings",
    "Questions",
    "Recommendation rationale",
    "Checks not performed",
)
PANEL_EXECUTION_STATES = {"independent", "simulated-separation"}
PANEL_REVIEWER_HEADING = re.compile(r"^###\s+(REV-\d{2,})\b", re.MULTILINE)
PANEL_MATRIX_HEADER = (
    "Finding ID",
    "Reviewer IDs",
    "Status",
    "Severity",
    "Evidence refs",
    "Disposition",
)
LIFECYCLE_STATES = {
    "open",
    "accepted",
    "fix-proposed",
    "fix-applied",
    "verified",
    "closed",
    "deferred",
    "rejected",
}


def _reverse_outline_errors(text: str) -> list[str]:
    if not STRUCTURE_MODE.search(text):
        return []
    match = REVERSE_OUTLINE_SECTION.search(text)
    if not match:
        return ["structure mode requires '## Reverse outline'"]

    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in match.group(1).splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    if not rows or rows[0] != list(REVERSE_OUTLINE_FIELDS):
        return [
            "reverse outline must use fields: "
            + ", ".join(REVERSE_OUTLINE_FIELDS)
        ]

    populated = [
        row
        for row in rows[2:]
        if len(row) == len(REVERSE_OUTLINE_FIELDS) and any(row)
    ]
    if not populated:
        return ["structure mode requires at least one populated reverse-outline row"]
    return []


def _finding_blocks(text: str) -> list[tuple[str, str]]:
    matches = list(FINDING_HEADING.finditer(text))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        candidate_ends = [len(text)]
        if index + 1 < len(matches):
            candidate_ends.append(matches[index + 1].start())
        next_section = SECTION_HEADING.search(text, match.end())
        if next_section:
            candidate_ends.append(next_section.start())
        end = min(candidate_ends)
        blocks.append((match.group(1), text[match.end() : end]))
    return blocks


def validate_report(text: str) -> list[str]:
    """Return validation errors without mutating the report."""
    errors: list[str] = []

    if not text.startswith("# Manuscript Audit"):
        errors.append("report must start with '# Manuscript Audit'")

    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"missing required heading: {heading}")
    errors.extend(_reverse_outline_errors(text))

    blocks = _finding_blocks(text)
    no_findings = "## No material findings" in text
    if not blocks and not no_findings:
        errors.append(
            "report must contain at least one AUD finding or "
            "'## No material findings'"
        )
    if blocks and no_findings:
        errors.append(
            "report cannot contain AUD findings and '## No material findings' together"
        )

    finding_ids = [finding_id for finding_id, _ in blocks]
    duplicates = sorted(
        finding_id for finding_id in set(finding_ids) if finding_ids.count(finding_id) > 1
    )
    for finding_id in duplicates:
        errors.append(f"duplicate finding ID: {finding_id}")

    for finding_id, block in blocks:
        fields = {name.strip(): value.strip() for name, value in FIELD_LINE.findall(block)}
        for field in REQUIRED_FINDING_FIELDS:
            if field not in fields:
                errors.append(f"{finding_id}: missing field '{field}'")
            elif not fields[field]:
                errors.append(f"{finding_id}: empty field '{field}'")

        severity = fields.get("Severity", "")
        if severity and not SEVERITY.match(severity):
            errors.append(f"{finding_id}: severity must start with S0, S1, S2, or S3")

        evidence_state = fields.get("Evidence status", "").lower()
        if evidence_state and evidence_state not in ALLOWED_EVIDENCE_STATES:
            allowed = ", ".join(sorted(ALLOWED_EVIDENCE_STATES))
            errors.append(
                f"{finding_id}: evidence status must be one of: {allowed}"
            )

    return errors


def validate_closure_ledger(text: str) -> list[str]:
    """Validate finding transitions without modifying the audit history."""

    errors: list[str] = []
    if not text.startswith("# Manuscript Audit Closure Ledger"):
        errors.append("closure ledger must start with '# Manuscript Audit Closure Ledger'")
    for heading in CLOSURE_REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"missing required closure heading: {heading}")

    blocks = _finding_blocks(text)
    if not blocks:
        errors.append("closure ledger must contain at least one AUD transition")
        return errors
    finding_ids = [finding_id for finding_id, _ in blocks]
    for finding_id in sorted(set(finding_ids)):
        if finding_ids.count(finding_id) > 1:
            errors.append(f"duplicate closure finding ID: {finding_id}")

    for finding_id, block in blocks:
        fields = {name.strip(): value.strip() for name, value in FIELD_LINE.findall(block)}
        for field in CLOSURE_REQUIRED_FIELDS:
            if field not in fields:
                errors.append(f"{finding_id}: missing closure field '{field}'")
            elif not fields[field]:
                errors.append(f"{finding_id}: empty closure field '{field}'")

        previous = fields.get("Previous state", "").lower()
        requested = fields.get("Requested state", "").lower()
        current = fields.get("New state", "").lower()
        for label, value in (
            ("Previous state", previous),
            ("Requested state", requested),
            ("New state", current),
        ):
            if value and value not in LIFECYCLE_STATES:
                errors.append(f"{finding_id}: {label} is invalid")

        verification_result = fields.get("Verification result", "").lower()
        verification_evidence = fields.get("Verification evidence", "").lower()
        protected_check = fields.get("Protected-content check", "").lower()
        if current in {"verified", "closed"}:
            if verification_result != "passed":
                errors.append(
                    f"{finding_id}: {current} requires Verification result: passed"
                )
            if verification_evidence in {"", "none", "not provided", "unclear"}:
                errors.append(f"{finding_id}: {current} requires verification evidence")
            if protected_check != "passed":
                errors.append(
                    f"{finding_id}: {current} requires Protected-content check: passed"
                )
        if verification_result == "failed" and current not in {"open", "deferred"}:
            errors.append(
                f"{finding_id}: failed verification must reopen or defer the finding"
            )
    return errors


def validate_prose_report(text: str) -> list[str]:
    """Validate a prose diagnostic without treating it as authorship evidence."""

    errors: list[str] = []
    if not text.startswith("# Prose Quality Audit"):
        errors.append("prose report must start with '# Prose Quality Audit'")
    for heading in PROSE_REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"missing required prose heading: {heading}")

    scope_end = text.find("## Findings")
    if scope_end < 0:
        scope_end = text.find("## No material findings")
    scope = text[:scope_end] if scope_end >= 0 else text
    scope_fields = {
        name.strip(): value.strip() for name, value in FIELD_LINE.findall(scope)
    }
    for field in PROSE_REQUIRED_SCOPE_FIELDS:
        if not scope_fields.get(field):
            errors.append(f"prose scope missing or empty field '{field}'")

    confidence = scope_fields.get("Diagnostic confidence", "").lower()
    if confidence and confidence not in PROSE_CONFIDENCE:
        allowed = ", ".join(sorted(PROSE_CONFIDENCE))
        errors.append(f"diagnostic confidence must be one of: {allowed}")

    safety_section = text.split("## No authorship inference", 1)
    if len(safety_section) == 2:
        safety_fields = {
            name.strip(): value.strip().lower()
            for name, value in FIELD_LINE.findall(safety_section[1])
        }
        for field in (
            "AI probability emitted",
            "Authorship verdict emitted",
            "Detector-evasion advice emitted",
        ):
            if safety_fields.get(field) != "no":
                errors.append(f"prose report requires '{field}: no'")

    blocks = _finding_blocks(text)
    no_findings = "## No material findings" in text
    if not blocks and not no_findings:
        errors.append(
            "prose report must contain at least one AUD finding or "
            "'## No material findings'"
        )
    for finding_id, block in blocks:
        fields = {name.strip(): value.strip() for name, value in FIELD_LINE.findall(block)}
        for field in PROSE_REQUIRED_FINDING_FIELDS:
            if not fields.get(field):
                errors.append(f"{finding_id}: missing or empty prose field '{field}'")
        category = fields.get("Category", "").upper()
        if category and category not in PROSE_CATEGORIES:
            errors.append(f"{finding_id}: unsupported prose category '{category}'")
        if category.startswith("PS-"):
            cluster = fields.get("Signal cluster", "").lower()
            if cluster in {"", "none", "single signal", "one signal"}:
                errors.append(f"{finding_id}: prose-style finding requires a signal cluster")
    return errors


def validate_panel_report(text: str) -> list[str]:
    """Validate reviewer separation and post-collection synthesis declarations."""

    errors: list[str] = []
    if not text.startswith("# Manuscript Review Panel"):
        errors.append("panel report must start with '# Manuscript Review Panel'")
    for heading in PANEL_REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"missing required panel heading: {heading}")

    reviewer_start = text.find("## Independent reviewer records")
    scope = text[:reviewer_start] if reviewer_start >= 0 else text
    scope_fields = {
        name.strip(): value.strip() for name, value in FIELD_LINE.findall(scope)
    }
    for field in PANEL_SCOPE_FIELDS:
        if not scope_fields.get(field):
            errors.append(f"panel scope missing or empty field '{field}'")

    execution = scope_fields.get("Execution status", "").lower()
    if execution and execution not in PANEL_EXECUTION_STATES:
        allowed = ", ".join(sorted(PANEL_EXECUTION_STATES))
        errors.append(f"panel execution status must be one of: {allowed}")
    isolation = scope_fields.get("Isolation method", "").lower()
    if execution == "independent" and (
        "same-context" in isolation or "not claimed" in isolation
    ):
        errors.append("independent status requires an actually isolated context")
    if scope_fields.get("Synthesis after independent records", "").lower() != "yes":
        errors.append("panel synthesis must occur after reviewer records")

    reviewer_matches = list(PANEL_REVIEWER_HEADING.finditer(text))
    if len(reviewer_matches) < 2:
        errors.append("panel report requires at least two reviewer records")
    reviewer_ids = [match.group(1) for match in reviewer_matches]
    for reviewer_id in sorted(set(reviewer_ids)):
        if reviewer_ids.count(reviewer_id) > 1:
            errors.append(f"duplicate reviewer ID: {reviewer_id}")
    for index, match in enumerate(reviewer_matches):
        end = reviewer_matches[index + 1].start() if index + 1 < len(reviewer_matches) else len(text)
        next_section = SECTION_HEADING.search(text, match.end())
        if next_section:
            end = min(end, next_section.start())
        fields = {
            name.strip(): value.strip()
            for name, value in FIELD_LINE.findall(text[match.end() : end])
        }
        for field in PANEL_REVIEWER_FIELDS:
            if not fields.get(field):
                errors.append(f"{match.group(1)}: missing or empty field '{field}'")

    matrix_start = text.find("## Synthesis matrix")
    matrix_end = text.find("## Minority and unresolved opinions")
    matrix = text[matrix_start:matrix_end] if matrix_start >= 0 and matrix_end > matrix_start else ""
    rows = [
        tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
        for line in matrix.splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    if not rows or rows[0] != PANEL_MATRIX_HEADER:
        errors.append(
            "panel synthesis matrix must use fields: "
            + ", ".join(PANEL_MATRIX_HEADER)
        )
    elif len(rows) < 3 or not any(cell for cell in rows[2]):
        errors.append("panel synthesis matrix requires at least one populated row")

    return errors


VALID_FIXTURE = """# Manuscript Audit

## Audit scope and confidence

- Materials reviewed: manuscript.md

## Executive summary

- Overall assessment: One major inconsistency.

## Findings

### AUD-001 — Metric direction conflict

- Severity: S1 Major
- Category: table-data
- Location: Results, paragraph 2
- Observed content: Text says lower is better; Table 2 ranks the highest value first.
- Evidence status: observed
- Why it matters: The reported conclusion may reverse the actual ranking.
- Suggested correction: Reconcile the metric direction and update the affected claim.
- Verification: Compare the corrected sentence against Table 2 and the metric definition.
- Root cause: Inconsistent metric interpretation.

## Unresolved items

None.

## Prioritized handoff

AUD-001 to the manuscript owner.
"""

INVALID_FIXTURE = """# Manuscript Audit

## Audit scope and confidence

## Executive summary

## Findings

### AUD-001 — Incomplete record

- Severity: high
- Category: logic

## Unresolved items

## Prioritized handoff
"""

NO_FINDING_FIXTURE = """# Manuscript Audit

## Audit scope and confidence

- Materials reviewed: abstract.md

## Executive summary

- Overall assessment: No material language issue in the supplied abstract.

## No material findings

The language mode found no material issue in the supplied abstract only.

## Unresolved items

None.

## Prioritized handoff

None.
"""

STRUCTURE_FIXTURE = """# Manuscript Audit

## Audit scope and confidence

- Materials reviewed: introduction.md
- Selected modes: structure

## Executive summary

- Overall assessment: One repeated paragraph function.

## Reverse outline

| Locator | Dominant function | Claim or question | Evidence/dependency | Transition |
|---|---|---|---|---|
| Introduction P1 | context | Why the task matters | supplied motivation | opens the gap |

## Findings

### AUD-001 — Repeated context function

- Severity: S2 Moderate
- Category: structure
- Location: Introduction P1-P2
- Observed content: Both paragraphs perform the same context-setting function.
- Evidence status: observed
- Why it matters: The gap is delayed.
- Suggested correction: Merge the repeated context and preserve both supported facts.
- Verification: Confirm the merged passage reaches the gap without losing evidence.
- Root cause: Duplicate paragraph role.

## Unresolved items

None.

## Prioritized handoff

AUD-001 to the manuscript owner.
"""

MISSING_STRUCTURE_FIXTURE = """# Manuscript Audit

## Audit scope and confidence

- Materials reviewed: introduction.md
- Selected modes: structure

## Executive summary

- Overall assessment: Pending structure map.

## No material findings

No finding is asserted.

## Unresolved items

Reverse outline missing.

## Prioritized handoff

None.
"""

PROSE_FIXTURE = """# Prose Quality Audit

## Audit scope and confidence

- Materials reviewed: introduction.md
- Selected mode: prose-style
- Usable prose sample: 12 substantive sentences
- Masked spans: two citations and one equation
- Diagnostic confidence: medium
- Sample limitation: one manuscript section only

## Findings

### AUD-001 — Repeated paragraph scaffold

- Severity: S2 Moderate
- Category: PS-01
- Location: Introduction P2, P4, and P5
- Observed content: Three paragraphs open with the same two-clause frame.
- Signal cluster: repeated scaffold at three mapped locations plus uniform rhythm
- Alternative explanation: intentional parallel exposition
- Evidence status: observed
- Why it matters: the repeated frame obscures differences among the claims
- Suggested correction: vary the frame while preserving claim order
- Protected scientific content: claim scope, citations, and uncertainty
- Verification: confirm the three claims and citations are unchanged
- Root cause: repeated drafting scaffold

## No authorship inference

- AI probability emitted: no
- Authorship verdict emitted: no
- Detector-evasion advice emitted: no

## Unresolved items

None.

## Prioritized handoff

AUD-001 to writing-academic after author acceptance.
"""


def run_self_test() -> int:
    valid_errors = validate_report(VALID_FIXTURE)
    invalid_errors = validate_report(INVALID_FIXTURE)
    no_finding_errors = validate_report(NO_FINDING_FIXTURE)
    structure_errors = validate_report(STRUCTURE_FIXTURE)
    missing_structure_errors = validate_report(MISSING_STRUCTURE_FIXTURE)
    closure_path = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "audit-closure-ledger.md"
    )
    closure_text = closure_path.read_text(encoding="utf-8")
    closure_errors = validate_closure_ledger(closure_text)
    invalid_closure = closure_text.replace(
        "- Verification evidence: manuscript.md#section",
        "- Verification evidence: none",
    )
    invalid_closure_errors = validate_closure_ledger(invalid_closure)
    prose_errors = validate_prose_report(PROSE_FIXTURE)
    invalid_prose = PROSE_FIXTURE.replace(
        "- AI probability emitted: no",
        "- AI probability emitted: yes",
    )
    invalid_prose_errors = validate_prose_report(invalid_prose)
    panel_path = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "review-panel-report.md"
    )
    panel_text = panel_path.read_text(encoding="utf-8")
    panel_errors = validate_panel_report(panel_text)
    invalid_panel = panel_text.replace(
        "- Synthesis after independent records: yes",
        "- Synthesis after independent records: no",
    )
    invalid_panel_errors = validate_panel_report(invalid_panel)
    if valid_errors:
        print("self-test failed: valid fixture was rejected", file=sys.stderr)
        for error in valid_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if no_finding_errors:
        print("self-test failed: no-finding fixture was rejected", file=sys.stderr)
        for error in no_finding_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if not invalid_errors:
        print("self-test failed: invalid fixture was accepted", file=sys.stderr)
        return 1
    if structure_errors:
        print("self-test failed: structure fixture was rejected", file=sys.stderr)
        for error in structure_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if not any("Reverse outline" in error for error in missing_structure_errors):
        print(
            "self-test failed: missing reverse outline was accepted",
            file=sys.stderr,
        )
        return 1
    if closure_errors:
        print("self-test failed: valid closure ledger was rejected", file=sys.stderr)
        for error in closure_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if not invalid_closure_errors:
        print("self-test failed: invalid closure ledger was accepted", file=sys.stderr)
        return 1
    if prose_errors:
        print("self-test failed: valid prose report was rejected", file=sys.stderr)
        for error in prose_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if not invalid_prose_errors:
        print("self-test failed: unsafe prose report was accepted", file=sys.stderr)
        return 1
    if panel_errors:
        print("self-test failed: valid panel report was rejected", file=sys.stderr)
        for error in panel_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if not invalid_panel_errors:
        print("self-test failed: invalid panel report was accepted", file=sys.stderr)
        return 1
    print("Self-test passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a saved manuscript-audit Markdown report."
    )
    parser.add_argument("report", nargs="?", type=Path)
    parser.add_argument(
        "--closure-ledger",
        type=Path,
        help="optional finding lifecycle ledger to validate",
    )
    parser.add_argument(
        "--prose-report",
        type=Path,
        help="standalone prose-quality diagnostic to validate",
    )
    parser.add_argument(
        "--panel-report",
        type=Path,
        help="standalone reviewer-panel report to validate",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run embedded valid and invalid fixtures",
    )
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()
    if args.report is None and args.prose_report is None and args.panel_report is None:
        parser.error(
            "provide a report path, --prose-report, --panel-report, or use --self-test"
        )

    errors: list[str] = []
    if args.report is not None:
        try:
            text = args.report.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"unable to read report: {exc}", file=sys.stderr)
            return 2
        errors.extend(validate_report(text))
    if args.prose_report is not None:
        try:
            prose_text = args.prose_report.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"unable to read prose report: {exc}", file=sys.stderr)
            return 2
        errors.extend(validate_prose_report(prose_text))
    if args.panel_report is not None:
        try:
            panel_text = args.panel_report.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"unable to read panel report: {exc}", file=sys.stderr)
            return 2
        errors.extend(validate_panel_report(panel_text))
    if args.closure_ledger is not None:
        try:
            closure_text = args.closure_ledger.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"unable to read closure ledger: {exc}", file=sys.stderr)
            return 2
        errors.extend(validate_closure_ledger(closure_text))
    if errors:
        print(f"Audit report validation failed ({len(errors)} issue(s)):")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Audit report is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
