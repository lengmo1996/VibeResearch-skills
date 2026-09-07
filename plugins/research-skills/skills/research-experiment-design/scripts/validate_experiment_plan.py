#!/usr/bin/env python3
"""Validate the structure of a saved experiment-plan Markdown file."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_HEADINGS = (
    "## Scope and hypothesis",
    "## Variables, controls, and confounds",
    "## Baseline and fairness protocol",
    "## Experiment matrix",
    "## Outcome branches",
    "## Schedule, budget, and gates",
    "## Failure diagnosis",
    "## Artifact and logging contract",
    "## Risks and unresolved protocol",
    "## Handoff",
)
EXPERIMENT_COLUMNS = (
    "Experiment ID",
    "Claim IDs or exploratory",
    "Target hypothesis",
    "Changed variable or interaction",
    "Controls",
    "Baseline",
    "Protocol reference",
    "Decision evidence",
    "Resource estimate",
    "Dependencies",
    "Acceptance or stop criterion",
)
REQUIRED_BRANCHES = ("supportive", "null", "adverse", "inconclusive")
EXPERIMENT_ID = re.compile(r"\bEXP-\d{3,}\b")
COMMON_HEADINGS = ("## Scope and hypothesis", "## Risks and unresolved protocol", "## Handoff")
MODE_HEADINGS = {
    "baseline": COMMON_HEADINGS + ("## Baseline and fairness protocol",),
    "control": COMMON_HEADINGS + ("## Variables, controls, and confounds",),
    "ablation": COMMON_HEADINGS + ("## Experiment matrix", "## Ablation and sensitivity plan", "## Outcome branches"),
    "schedule": COMMON_HEADINGS + ("## Schedule, budget, and gates",),
    "full": REQUIRED_HEADINGS,
}
SCOPED_TABLES = {
    "baseline": ("## Baseline and fairness protocol", 7),
    "control": ("## Variables, controls, and confounds", 6),
    "ablation": ("## Ablation and sensitivity plan", 6),
    "schedule": ("## Schedule, budget, and gates", 6),
}


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    next_heading = re.search(r"^##\s+", text[start + len(heading) :], re.MULTILINE)
    if not next_heading:
        return text[start:]
    end = start + len(heading) + next_heading.start()
    return text[start:end]


def _table_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def _select_mode(text: str, explicit: str | None) -> tuple[str, list[str]]:
    declarations = re.findall(r"^-[ \t]+Mode:[ \t]*([^\r\n]*)", _section(text, "## Scope and hypothesis"), re.MULTILINE)
    declarations = [value.strip().strip("`") for value in declarations if value.strip()]
    errors: list[str] = []
    if len(declarations) > 1:
        errors.append("scope must declare Mode at most once")
    declared = declarations[0] if declarations else None
    selected = explicit if explicit is not None else declared or "full"
    if selected not in MODE_HEADINGS:
        errors.append(f"unknown mode: {selected}")
    if declared is not None and declared not in MODE_HEADINGS:
        errors.append(f"unknown document Mode: {declared}")
    if explicit is not None and declared is not None and explicit != declared:
        errors.append(f"explicit mode {explicit!r} conflicts with document Mode {declared!r}")
    return selected, errors


def _validate_scoped_table(section: str, width: int, required: bool) -> list[str]:
    rows = _table_rows(section)
    if not rows and not required:
        return []
    label = section.splitlines()[0] if section else "required mode table"
    if len(rows) < 2:
        return [f"{label}: requires at least one table record"]
    errors: list[str] = []
    if len(rows[0]) != width:
        errors.append(f"{label}: header must contain exactly {width} columns")
    for row in rows[1:]:
        if len(row) != width or any(not cell for cell in row):
            errors.append(f"{label}: record must contain {width} non-empty fields")
    return errors


def validate_plan(text: str, mode: str | None = None) -> list[str]:
    """Return validation errors without modifying the plan."""
    selected, errors = _select_mode(text, mode)
    if errors:
        return errors

    if not text.startswith("# Experiment Plan"):
        errors.append("plan must start with '# Experiment Plan'")
    for heading in MODE_HEADINGS[selected]:
        if heading not in text:
            errors.append(f"missing required heading: {heading}")

    experiment_rows = _table_rows(_section(text, "## Experiment matrix"))
    if experiment_rows:
        header = experiment_rows[0]
        missing_columns = [column for column in EXPERIMENT_COLUMNS if column not in header]
        for column in missing_columns:
            errors.append(f"experiment matrix missing column: {column}")
        data_rows = experiment_rows[1:]
    elif selected in {"full", "ablation"}:
        errors.append("experiment matrix table is missing")
        data_rows = []
    else:
        data_rows = []

    experiment_ids: list[str] = []
    for row in data_rows:
        if not row:
            continue
        if len(row) != len(EXPERIMENT_COLUMNS):
            errors.append(
                "experiment row must contain exactly "
                f"{len(EXPERIMENT_COLUMNS)} columns"
            )
            continue
        match = EXPERIMENT_ID.search(row[0])
        if not match:
            errors.append("experiment row must start with an EXP-### ID")
            continue
        experiment_ids.append(match.group(0))
        if any(not cell for cell in row[: len(EXPERIMENT_COLUMNS)]):
            errors.append(f"{match.group(0)}: experiment row contains an empty field")

    if not experiment_ids and (selected in {"full", "ablation"} or experiment_rows):
        errors.append("plan must contain at least one experiment record")
    for experiment_id in sorted(set(experiment_ids)):
        if experiment_ids.count(experiment_id) > 1:
            errors.append(f"duplicate experiment ID: {experiment_id}")

    outcome_section = _section(text, "## Outcome branches")
    if selected in {"full", "ablation"} or _table_rows(outcome_section):
        for branch in REQUIRED_BRANCHES:
            if not re.search(rf"\|\s*{re.escape(branch)}\s*\|", outcome_section.lower()):
                errors.append(f"missing outcome branch: {branch}")
        errors.extend(_validate_scoped_table(outcome_section, 5, required=True))

    for table_mode, (heading, width) in SCOPED_TABLES.items():
        section = _section(text, heading)
        errors.extend(_validate_scoped_table(section, width, required=selected == table_mode))
        for row in _table_rows(section)[1:]:
            if len(row) != width:
                continue
            if table_mode == "ablation":
                if not EXPERIMENT_ID.fullmatch(row[0]) or row[0] not in experiment_ids:
                    errors.append(f"ablation record must reference an experiment in the matrix: {row[0]!r}")
            if table_mode == "schedule" and not EXPERIMENT_ID.search(row[1]):
                errors.append("schedule record must reference at least one upstream EXP-### ID")

    return errors


VALID_FIXTURE = """# Experiment Plan

## Scope and hypothesis

- Target hypothesis: H1

## Variables, controls, and confounds

Defined.

## Baseline and fairness protocol

Defined.

## Experiment matrix

| Experiment ID | Claim IDs or exploratory | Target hypothesis | Changed variable or interaction | Controls | Baseline | Protocol reference | Decision evidence | Resource estimate | Dependencies | Acceptance or stop criterion |
|---|---|---|---|---|---|---|---|---|---|---|
| EXP-001 | CLM-001 | H1 | feature on/off | data and seed | base | P1 | metric delta | 2 GPU-hours | none | compare against bound |

## Outcome branches

| Branch | Observable signal | Interpretation boundary | Decision | Follow-up |
|---|---|---|---|---|
| supportive | signal | bounded | continue | verify |
| null | no signal | bounded | stop claim | diagnose |
| adverse | regression | bounded | reject variant | inspect |
| inconclusive | failed protocol | bounded | rerun | repair |

## Schedule, budget, and gates

Defined.

## Failure diagnosis

Defined.

## Artifact and logging contract

Defined.

## Risks and unresolved protocol

None.

## Handoff

Defined.
"""

INVALID_FIXTURE = """# Experiment Plan

## Scope and hypothesis

## Experiment matrix

| Experiment ID | Target hypothesis |
|---|---|
| run-one | H1 |
"""


def run_self_test() -> int:
    valid_errors = validate_plan(VALID_FIXTURE)
    invalid_errors = validate_plan(INVALID_FIXTURE)
    short_row_fixture = VALID_FIXTURE.replace(
        "| EXP-001 | CLM-001 | H1 | feature on/off | data and seed | base | P1 | "
        "metric delta | 2 GPU-hours | none | compare against bound |",
        "| EXP-001 | H1 |",
    )
    short_row_errors = validate_plan(short_row_fixture)
    if valid_errors:
        print("self-test failed: valid fixture was rejected", file=sys.stderr)
        for error in valid_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if not invalid_errors:
        print("self-test failed: invalid fixture was accepted", file=sys.stderr)
        return 1
    if not any("exactly 11 columns" in error for error in short_row_errors):
        print("self-test failed: short experiment row was accepted", file=sys.stderr)
        return 1
    print("Self-test passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a saved experiment-plan Markdown file."
    )
    parser.add_argument("plan", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--mode", choices=sorted(MODE_HEADINGS), help="Selected contract; otherwise use document Mode, then legacy full.")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()
    if args.plan is None:
        parser.error("provide a plan path or use --self-test")

    try:
        text = args.plan.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"unable to read plan: {exc}", file=sys.stderr)
        return 2

    errors = validate_plan(text, args.mode)
    if errors:
        print(f"Experiment plan validation failed ({len(errors)} issue(s)):")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Experiment plan is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
