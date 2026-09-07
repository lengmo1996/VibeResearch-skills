#!/usr/bin/env python3
"""Validate the structure of a saved evaluation-protocol Markdown file."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_HEADINGS = (
    "## Scope and identities",
    "## Evaluation units",
    "## Split protocol",
    "## Preprocessing contract",
    "## Metric registry",
    "## Leakage register",
    "## Statistical plan",
    "## Comparability ledger",
    "## Reporting contract",
    "## Unresolved decisions and blocked verdicts",
    "## Handoff",
)
REQUIRED_UNITS = ("prediction", "evaluation", "grouping", "uncertainty")
VERDICTS = {"comparable", "conditional", "non-comparable"}
METRIC_ID = re.compile(r"\bMET-\d{3,}\b")
COMPARISON_ID = re.compile(r"\bCMP-\d{3,}\b")
COMMON_HEADINGS = (
    "## Scope and identities",
    "## Unresolved decisions and blocked verdicts",
    "## Handoff",
)
MODE_HEADINGS = {
    "split": COMMON_HEADINGS + ("## Evaluation units", "## Split protocol"),
    "preprocessing": COMMON_HEADINGS + ("## Preprocessing contract",),
    "metric": COMMON_HEADINGS + ("## Metric registry",),
    "statistics": COMMON_HEADINGS + ("## Evaluation units", "## Statistical plan"),
    "leakage": COMMON_HEADINGS + ("## Leakage register",),
    "comparability": COMMON_HEADINGS + ("## Comparability ledger",),
    "full": REQUIRED_HEADINGS,
}
MODE_UNITS = {
    "split": ("prediction", "evaluation", "grouping"),
    "statistics": ("evaluation", "uncertainty"),
    "full": REQUIRED_UNITS,
}
SCOPED_TABLES = {
    "split": ("## Split protocol", 5, None),
    "preprocessing": ("## Preprocessing contract", 6, r"PRE-\d{3,}"),
    "leakage": ("## Leakage register", 6, r"LEAK-\d{3,}"),
    "statistics": ("## Statistical plan", 8, r"STAT-\d{3,}"),
}


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    remainder_start = start + len(heading)
    next_heading = re.search(r"^##\s+", text[remainder_start:], re.MULTILINE)
    end = remainder_start + next_heading.start() if next_heading else len(text)
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
    declarations = re.findall(r"^-[ \t]+Mode:[ \t]*([^\r\n]*)", _section(text, "## Scope and identities"), re.MULTILINE)
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


def _validate_scoped_table(section: str, width: int, id_pattern: str | None, required: bool) -> list[str]:
    rows = _table_rows(section)
    if not rows and not required:
        return []
    label = section.splitlines()[0] if section else "required mode table"
    if len(rows) < 2:
        return [f"{label}: requires at least one table record"]
    errors: list[str] = []
    if len(rows[0]) != width:
        errors.append(f"{label}: header must contain exactly {width} columns")
    ids: set[str] = set()
    for row in rows[1:]:
        if len(row) != width or any(not cell for cell in row):
            errors.append(f"{label}: record must contain {width} non-empty fields")
            continue
        if id_pattern and not re.fullmatch(id_pattern, row[0]):
            errors.append(f"{label}: invalid record ID {row[0]!r}")
        if row[0] in ids:
            errors.append(f"{label}: duplicate record ID {row[0]!r}")
        ids.add(row[0])
    return errors


def validate_protocol(text: str, mode: str | None = None) -> list[str]:
    """Return validation errors without modifying the protocol."""
    selected, errors = _select_mode(text, mode)
    if errors:
        return errors

    if not text.startswith("# Evaluation Protocol"):
        errors.append("protocol must start with '# Evaluation Protocol'")
    for heading in MODE_HEADINGS[selected]:
        if heading not in text:
            errors.append(f"missing required heading: {heading}")

    unit_rows = _table_rows(_section(text, "## Evaluation units"))[1:]
    unit_names: set[str] = set()
    for row in unit_rows:
        if len(row) != 5:
            errors.append("evaluation unit row must contain exactly 5 columns")
            continue
        if any(not cell for cell in row):
            errors.append(f"{row[0] or 'unknown unit'}: evaluation unit row is incomplete")
            continue
        unit_names.add(row[0].lower())
    for unit in MODE_UNITS.get(selected, ()):
        if unit not in unit_names:
            errors.append(f"missing evaluation unit: {unit}")

    metric_rows = _table_rows(_section(text, "## Metric registry"))[1:]
    metric_ids: list[str] = []
    for row in metric_rows:
        if len(row) != 10:
            errors.append("metric row must contain exactly 10 columns")
            continue
        match = METRIC_ID.search(row[0])
        if not match:
            errors.append("metric row must start with a MET-### ID")
            continue
        metric_ids.append(match.group(0))
        if any(not cell for cell in row):
            errors.append(f"{match.group(0)}: metric row contains an empty field")
    if not metric_ids and (selected in {"metric", "full"} or _table_rows(_section(text, "## Metric registry"))):
        errors.append("protocol must contain at least one metric record")
    for metric_id in sorted(set(metric_ids)):
        if metric_ids.count(metric_id) > 1:
            errors.append(f"duplicate metric ID: {metric_id}")

    comparison_rows = _table_rows(_section(text, "## Comparability ledger"))[1:]
    comparison_ids: list[str] = []
    for row in comparison_rows:
        if len(row) != 7:
            errors.append("comparability row must contain exactly 7 columns")
            continue
        match = COMPARISON_ID.search(row[0])
        if not match:
            errors.append("comparability row must start with a CMP-### ID")
            continue
        comparison_ids.append(match.group(0))
        if any(not cell for cell in row):
            errors.append(f"{match.group(0)}: comparability row contains an empty field")
        verdict = row[5].lower()
        if verdict not in VERDICTS:
            allowed = ", ".join(sorted(VERDICTS))
            errors.append(f"{match.group(0)}: verdict must be one of: {allowed}")
        if not row[6]:
            errors.append(f"{match.group(0)}: allowed claim is empty")
    if not comparison_ids and (selected in {"comparability", "full"} or _table_rows(_section(text, "## Comparability ledger"))):
        errors.append("protocol must contain at least one comparability record")
    for comparison_id in sorted(set(comparison_ids)):
        if comparison_ids.count(comparison_id) > 1:
            errors.append(f"duplicate comparison ID: {comparison_id}")

    for table_mode, (heading, width, id_pattern) in SCOPED_TABLES.items():
        errors.extend(_validate_scoped_table(_section(text, heading), width, id_pattern,
                                             required=selected == table_mode))

    return errors


VALID_FIXTURE = """# Evaluation Protocol

## Scope and identities

- Protocol ID: P1

## Evaluation units

| Unit | Definition | Identifier/grouping key | Sampling relationship | Why this unit |
|---|---|---|---|---|
| prediction | image | image ID | nested in subject | one output |
| evaluation | image | image ID | nested in subject | metric unit |
| grouping | subject | subject ID | independent groups | split integrity |
| uncertainty | subject | subject ID | resampled groups | dependence |

## Split protocol

Defined.

## Preprocessing contract

Defined.

## Metric registry

| Metric ID | Target quantity | Direction | Unit/range | Implementation/version | Parameters | Aggregation/weighting | Threshold/missing/tie handling | Reporting precision | Validity conditions |
|---|---|---|---|---|---|---|---|---|---|
| MET-001 | accuracy | higher | proportion | package 1.0 | default | macro | report missing | 3 decimals | fixed split and unit |

## Leakage register

Defined.

## Statistical plan

Defined.

## Comparability ledger

| Comparison ID | Dataset/split difference | Preprocessing difference | Metric/aggregation difference | Sampling/statistics difference | Verdict | Allowed claim |
|---|---|---|---|---|---|---|
| CMP-001 | none | none | none | none | comparable | direct comparison |

## Reporting contract

Defined.

## Unresolved decisions and blocked verdicts

None.

## Handoff

Defined.
"""

INVALID_FIXTURE = """# Evaluation Protocol

## Scope and identities

## Metric registry

| Metric ID | Target quantity |
|---|---|
| score | accuracy |
"""


def run_self_test() -> int:
    valid_errors = validate_protocol(VALID_FIXTURE)
    invalid_errors = validate_protocol(INVALID_FIXTURE)
    if valid_errors:
        print("self-test failed: valid fixture was rejected", file=sys.stderr)
        for error in valid_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if not invalid_errors:
        print("self-test failed: invalid fixture was accepted", file=sys.stderr)
        return 1
    print("Self-test passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a saved evaluation-protocol Markdown file."
    )
    parser.add_argument("protocol", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--mode", choices=sorted(MODE_HEADINGS), help="Selected contract; otherwise use document Mode, then legacy full.")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()
    if args.protocol is None:
        parser.error("provide a protocol path or use --self-test")

    try:
        text = args.protocol.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"unable to read protocol: {exc}", file=sys.stderr)
        return 2

    errors = validate_protocol(text, args.mode)
    if errors:
        print(f"Evaluation protocol validation failed ({len(errors)} issue(s)):")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Evaluation protocol is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
