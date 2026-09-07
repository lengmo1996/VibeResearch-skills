#!/usr/bin/env python3
"""Validate editable Draw.io mxfile structure without external dependencies."""

from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _finite_number(value: str | None) -> bool:
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except ValueError:
        return False


def validate_root(root: ET.Element) -> list[str]:
    errors: list[str] = []
    if root.tag != "mxfile":
        return [f"root element must be mxfile, found {root.tag!r}"]
    diagrams = root.findall("diagram")
    if not diagrams:
        return ["mxfile must contain at least one diagram"]
    for diagram_index, diagram in enumerate(diagrams):
        models = diagram.findall("mxGraphModel")
        if len(models) != 1:
            errors.append(f"diagram[{diagram_index}] must contain exactly one mxGraphModel")
            continue
        graph_root = models[0].find("root")
        if graph_root is None:
            errors.append(f"diagram[{diagram_index}] mxGraphModel is missing root")
            continue
        cells = graph_root.findall("mxCell")
        ids: set[str] = set()
        by_id: dict[str, ET.Element] = {}
        for cell_index, cell in enumerate(cells):
            cell_id = cell.get("id")
            if not cell_id:
                errors.append(f"diagram[{diagram_index}] cell[{cell_index}] is missing id")
                continue
            if cell_id in ids:
                errors.append(f"diagram[{diagram_index}] duplicate cell id: {cell_id}")
            ids.add(cell_id)
            by_id[cell_id] = cell
        for required in {"0", "1"}:
            if required not in ids:
                errors.append(f"diagram[{diagram_index}] is missing base cell {required}")
        for cell_id, cell in by_id.items():
            parent = cell.get("parent")
            if parent is not None and parent not in ids:
                errors.append(f"cell {cell_id} references missing parent {parent}")
            is_vertex = cell.get("vertex") == "1"
            is_edge = cell.get("edge") == "1"
            if is_vertex and is_edge:
                errors.append(f"cell {cell_id} cannot be both vertex and edge")
            geometry = cell.find("mxGeometry")
            if is_vertex:
                if geometry is None:
                    errors.append(f"vertex {cell_id} is missing mxGeometry")
                else:
                    for field in ("x", "y", "width", "height"):
                        if not _finite_number(geometry.get(field)):
                            errors.append(f"vertex {cell_id} has invalid {field}")
                    for field in ("width", "height"):
                        value = geometry.get(field)
                        if _finite_number(value) and float(value) <= 0:
                            errors.append(f"vertex {cell_id} has non-positive {field}")
            if is_edge:
                source = cell.get("source")
                target = cell.get("target")
                if source not in ids:
                    errors.append(f"edge {cell_id} references missing source {source!r}")
                elif by_id[source].get("vertex") != "1":
                    errors.append(f"edge {cell_id} source {source!r} is not a vertex")
                if target not in ids:
                    errors.append(f"edge {cell_id} references missing target {target!r}")
                elif by_id[target].get("vertex") != "1":
                    errors.append(f"edge {cell_id} target {target!r} is not a vertex")
                if geometry is None or geometry.get("relative") != "1":
                    errors.append(f"edge {cell_id} requires relative mxGeometry")
        for cell_id in by_id:
            chain: set[str] = set()
            cursor = cell_id
            while cursor in by_id:
                if cursor in chain:
                    errors.append(f"cell parent cycle includes {cursor}")
                    break
                chain.add(cursor)
                parent = by_id[cursor].get("parent")
                if parent is None:
                    break
                cursor = parent
    return errors


def validate_path(path: Path) -> list[str]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        return [f"cannot parse Draw.io XML: {exc}"]
    return validate_root(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Draw.io file to validate")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)
    errors = validate_path(args.input)
    result = {"valid": not errors, "path": str(args.input), "errors": errors}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif errors:
        print(f"INVALID: {args.input}", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print(f"VALID: {args.input}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
