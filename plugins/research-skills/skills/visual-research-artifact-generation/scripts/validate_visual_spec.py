#!/usr/bin/env python3
"""Validate a visual artifact specification without rendering or modifying files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


HEADINGS = (
    "## Contract",
    "## Source facts and elements",
    "## Claim and figure coverage",
    "## Cross-figure relationships",
    "## Revision ledger",
    "## Validation matrix",
    "## Reproduction and uncertainty",
)
NARRATIVE_ROLES = {
    "overview",
    "problem",
    "method",
    "evidence",
    "diagnostic",
    "limitation",
    "standalone",
}


def _field(text: str, name: str) -> str:
    match = re.search(rf"^- {re.escape(name)}:[ \t]*([^\n\r]*)", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _ids(value: str, prefix: str) -> set[str]:
    return set(re.findall(rf"\b{prefix}-\d{{3,}}\b", value))


def _check_id_list(value: str, prefixes: tuple[str, ...], label: str, errors: list[str], *, optional: bool = False) -> None:
    if optional and value.strip() in {"", "none", "not-applicable"}:
        return
    tokens = [token.strip("`") for token in re.split(r"[\s,/]+", value.strip()) if token]
    pattern = rf"(?:{'|'.join(prefixes)})-\d{{3,}}"
    if not tokens or len(tokens) != len(set(tokens)) or any(not re.fullmatch(pattern, token) for token in tokens):
        errors.append(f"{label} requires a list of unique valid IDs")


def _provided(value: str) -> bool:
    return value.strip().casefold() not in {"", "none", "unknown", "unresolved", "not checked", "not run", "not-run", "not provided", "not provided / unclear", "tbd", "todo", "n/a"}


def _table(text: str, header: str, errors: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    width = 0
    active = False
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            if active:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not active:
            if cells[0] == header:
                active, width = True, len(cells)
                expected_width = {"Source ID": 6, "Element ID": 8, "Claim ID": 6, "Figure ID": 6, "Layer": 6}[header]
                if width != expected_width:
                    errors.append(f"{header} table has an invalid header width")
                    return []
            continue
        if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        if len(cells) != width:
            errors.append(f"{header} table has a malformed row")
        else:
            rows.append(cells)
    return rows


def _completed(text: str, errors: list[str]) -> None:
    figures = _ids(_field(text, "Figure ID"), "FIG")
    panels = _ids(_field(text, "Panel IDs"), "PAN")
    companions = _ids(_field(text, "Companion figure IDs"), "FIG")
    targets = _ids(_field(text, "Target claim IDs"), "CLM")
    role = _field(text, "Primary narrative role")
    for field, prefixes in (("Panel IDs", ("PAN",)), ("Companion figure IDs", ("FIG",)), ("Target claim IDs", ("CLM",))):
        _check_id_list(_field(text, field), prefixes, field, errors, optional=True)
    if len(figures) != 1 or not re.fullmatch(r"FIG-\d{3,}", _field(text, "Figure ID")):
        errors.append("completed spec requires one exact Figure ID")
    if not targets and (role != "standalone" or _field(text, "Target claim IDs") not in {"none", "not-applicable"}):
        errors.append("target claims may be absent only for explicitly standalone artifacts")
    for name in ("Mode / intended use", "Requested editable/rendered formats", "Backend and rationale", "Authorized output paths"):
        if not _field(text, name):
            errors.append(f"completed spec requires {name}")
    mode = _field(text, "Mode / intended use").split(" / ")[0]
    if mode not in {"drawio-diagram", "tikz-diagram", "pgfplots", "data-plot", "latex-table", "multi-panel"}:
        errors.append("completed spec has an invalid backend mode")

    sources = _table(text, "Source ID", errors)
    elements = _table(text, "Element ID", errors)
    coverage = _table(text, "Claim ID", errors)
    relationships = _table(text, "Figure ID", errors)
    source_ids = {row[0] for row in sources}
    element_ids = {row[0] for row in elements}
    for label, rows, pattern in (("source", sources, r"SRC-\d{3,}"), ("element", elements, r"ELEM-\d{3,}"), ("claim", coverage, r"CLM-\d{3,}")):
        if (label != "claim" or targets) and not rows:
            errors.append(f"completed spec requires {label} records")
        identities = [row[0] for row in rows]
        if len(identities) != len(set(identities)) or any(not re.fullmatch(pattern, value) for value in identities):
            errors.append(f"{label} records require unique valid IDs")
    source_status = {row[0]: row[3] for row in sources}
    for row in sources:
        _check_id_list(row[4], ("CLM",), f"{row[0]} claim IDs", errors, optional=True)
        _check_id_list(row[5], ("ELEM", "PAN"), f"{row[0]} output IDs", errors)
        if not row[1] or not row[2] or row[3] not in {"verified", "candidate", "missing", "contradictory"}:
            errors.append(f"{row[0]} requires content, provenance, and one evidence status")
        if _ids(row[4], "CLM") - targets:
            errors.append(f"{row[0]} references an undeclared claim")
        outputs = _ids(row[5], "ELEM") | _ids(row[5], "PAN")
        if not outputs or outputs - element_ids - panels:
            errors.append(f"{row[0]} references missing output elements/panels")
    for row in elements:
        _check_id_list(row[1], ("FIG", "PAN"), f"{row[0]} destinations", errors)
        _check_id_list(row[6], ("SRC",), f"{row[0]} sources", errors)
        destinations = _ids(row[1], "FIG") | _ids(row[1], "PAN")
        refs = _ids(row[6], "SRC")
        if not destinations or destinations - figures - panels:
            errors.append(f"{row[0]} references an undeclared figure/panel")
        if not refs or refs - source_ids:
            errors.append(f"{row[0]} references missing sources")
        if any(not row[index] for index in (2, 3, 4, 5)) or row[7] not in {"yes", "no"}:
            errors.append(f"{row[0]} has incomplete element metadata")
    if {row[0] for row in coverage} != targets:
        errors.append("claim coverage must match declared target claims exactly")
    for row in coverage:
        _check_id_list(row[1], ("SRC",), f"{row[0]} sources", errors)
        _check_id_list(row[2], ("FIG", "PAN"), f"{row[0]} destinations", errors)
        refs = _ids(row[1], "SRC")
        destinations = _ids(row[2], "FIG") | _ids(row[2], "PAN")
        if not refs or refs - source_ids or not destinations or destinations - figures - panels:
            errors.append(f"{row[0]} has broken source or figure/panel references")
        if row[5] not in {"verified", "blocked"} or not row[3] or not row[4]:
            errors.append(f"{row[0]} requires assertion, caption boundary, and coverage status")
        if row[5] == "verified" and any(source_status.get(ref) != "verified" for ref in refs):
            errors.append(f"{row[0]} cannot be verified with unverified source evidence")
        if row[5] == "verified":
            for destination in destinations:
                for ref in refs:
                    linked = any(
                        (destination in figures or destination in _ids(element[1], "PAN"))
                        and ref in _ids(element[6], "SRC")
                        and any(
                            source[0] == ref and (
                                element[0] in _ids(source[5], "ELEM")
                                or bool(_ids(source[5], "PAN") & _ids(element[1], "PAN"))
                            )
                            for source in sources
                        )
                        for element in elements
                    )
                    if not linked:
                        errors.append(f"{row[0]} has no source-to-element path for {ref} in {destination}")
    related_ids: set[str] = set()
    for row in relationships:
        _check_id_list(row[1], ("FIG",), "related figures", errors, optional=True)
        related_ids.update(_ids(row[1], "FIG"))
        if row[0] not in figures or (_ids(row[1], "FIG") - companions):
            errors.append("cross-figure relationship references an undeclared figure")
        if row[4] not in {"passed", "failed", "blocked", "not-run", "not-applicable"} or not row[5]:
            errors.append("cross-figure relationship needs a status and evidence/reason")
    if related_ids != companions:
        errors.append("companion relationships must cover the declared companions")

    matrix = _table(text, "Layer", errors)
    required = {"source/content", "structure/schema", "compile/build", "render/export", "visual inspection", "semantic/value cross-check", "claim-evidence trace", "cross-figure consistency"}
    if {row[0] for row in matrix} != required or len(matrix) != len(required):
        errors.append("validation matrix must contain each required layer exactly once")
    statuses = {row[0]: row[4] for row in matrix}
    for row in matrix:
        if row[4] not in {"passed", "failed", "blocked", "not-run", "not-applicable"}:
            errors.append(f"{row[0]} requires one validation status")
        elif row[4] == "passed" and any(not _provided(row[index]) for index in (1, 2, 3)):
            errors.append(f"{row[0]} passed requires command/tool, expected, and observed evidence")
        elif row[4] != "passed" and not row[5]:
            errors.append(f"{row[0]} requires a blocker or applicability reason")
        if row[4] == "not-applicable" and not ((row[0] == "claim-evidence trace" and not targets) or (row[0] == "cross-figure consistency" and not companions)):
            errors.append(f"{row[0]} cannot be marked not-applicable")
    if any(statuses.get(layer) == "passed" for layer in ("render/export", "visual inspection")) and not _provided(_field(text, "Preview identity")):
        errors.append("render/visual success requires a preview identity")
    if statuses.get("visual inspection") == "passed" and statuses.get("render/export") != "passed":
        errors.append("visual inspection success requires a rendered preview")
    if statuses.get("source/content") == "passed" and any(status in {"missing", "contradictory"} for status in source_status.values()):
        errors.append("source/content cannot pass with missing or contradictory sources")
    if statuses.get("claim-evidence trace") == "passed" and any(row[5] != "verified" for row in coverage):
        errors.append("claim-evidence trace cannot pass with blocked claim coverage")
    if statuses.get("cross-figure consistency") == "passed" and any(row[4] not in {"passed", "not-applicable"} for row in relationships):
        errors.append("cross-figure consistency cannot pass with unresolved or failed relationships")
    if statuses.get("compile/build") == "passed" and any(not _provided(_field(text, field)) for field in ("Exact command", "Runtime/version")):
        errors.append("build success requires a reproduction command and runtime identity")


def validate(text: str, *, completed: bool = False) -> list[str]:
    errors: list[str] = []
    if not text.startswith("# Visual Research Artifact Specification"):
        errors.append("spec must start with '# Visual Research Artifact Specification'")
    for heading in HEADINGS:
        if heading not in text:
            errors.append(f"missing required heading: {heading}")
    if not re.search(r"\bFIG-\d{3,}\b", text):
        errors.append("missing FIG-### identity")
    if not re.search(r"\bSRC-\d{3,}\b", text):
        errors.append("missing SRC-### source")
    if not re.search(r"\bELEM-\d{3,}\b", text):
        errors.append("missing ELEM-### element")
    if not completed and not re.search(r"\bCLM-\d{3,}\b", text):
        errors.append("missing CLM-### target claim")
    role_match = re.search(r"^- Primary narrative role:\s*(\S+)", text, re.MULTILINE)
    if not role_match or role_match.group(1) not in NARRATIVE_ROLES:
        errors.append("primary narrative role is missing or invalid")
    for layer in ("claim-evidence trace", "cross-figure consistency"):
        if not re.search(rf"\|\s*{re.escape(layer)}\s*\|", text):
            errors.append(f"validation matrix is missing layer: {layer}")
    if completed and not errors:
        _completed(text, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--completed", action="store_true", help="check completed-record states and reference closure; default checks template structure")
    args = parser.parse_args()
    if args.self_test:
        sample = Path(__file__).resolve().parents[1] / "templates" / "visual-artifact-spec.md"
        valid_errors = validate(sample.read_text(encoding="utf-8"))
        invalid_errors = validate("# Visual Research Artifact Specification")
        if valid_errors or not invalid_errors:
            print("Self-test failed.", file=sys.stderr)
            return 1
        print("Self-test passed.")
        return 0
    if args.spec is None:
        parser.error("provide a spec path or use --self-test")
    try:
        errors = validate(args.spec.read_text(encoding="utf-8"), completed=args.completed)
    except OSError as exc:
        print(f"unable to read spec: {exc}", file=sys.stderr)
        return 2
    if errors:
        print(f"Visual specification validation failed ({len(errors)} issue(s)):")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Visual specification record is consistent; rendering was not checked." if args.completed else "Visual specification template structure is valid; completion was not checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
