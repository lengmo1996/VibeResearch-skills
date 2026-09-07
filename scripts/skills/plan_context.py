#!/usr/bin/env python3
"""Resolve a reviewed mode's initial reading plan without executing the workflow."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any

from common import GovernanceError, ROOT, emit, json_text, load_registry, resolve_under


def section(text: str, fragment: str) -> str:
    """Select a Markdown heading and its children; missing anchors fail closed."""
    lines = text.splitlines(keepends=True)
    headings: list[tuple[int, int, str]] = []
    seen: dict[str, int] = {}
    fence = None
    for index, line in enumerate(lines):
        fenced = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if fence is not None:
            if fenced and fenced.group(1)[0] == fence[0] and len(fenced.group(1)) >= fence[1] and not fenced.group(2).strip():
                fence = None
            continue
        if fenced and not (fenced.group(1)[0] == "`" and "`" in fenced.group(2)):
            fence = (fenced.group(1)[0], len(fenced.group(1)))
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        title = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", match.group(2))
        slug = re.sub(r"[^\w\-\s]", "", title.lower()).replace(" ", "-")
        number = seen.get(slug, 0)
        seen[slug] = number + 1
        headings.append((index, len(match.group(1)), slug + (f"-{number}" if number else "")))
    for position, (start, level, slug) in enumerate(headings):
        if slug != fragment:
            continue
        end = next((item[0] for item in headings[position + 1:] if item[1] <= level), len(lines))
        return "".join(lines[start:end])
    raise GovernanceError(f"missing Markdown resource anchor: #{fragment}")


def _paths(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(path, str) or not path.strip() for path in value):
        raise GovernanceError(f"{label} must be a list of nonempty resource paths")
    if len(value) != len(set(value)):
        raise GovernanceError(f"{label} contains duplicate resource paths")
    return value


def _budget(value: Any, label: str, maximum: int | None = None) -> int:
    if type(value) is not int or value < 0 or (maximum is not None and value > maximum):
        raise GovernanceError(f"invalid {label}")
    return value


def build_plan(root: Path, entry: dict[str, Any], mode: str, stage: str | None = None) -> dict[str, Any]:
    if mode not in entry.get("modes", []):
        raise GovernanceError(f"undeclared mode: {entry.get('id')}:{mode}")
    contracts = entry.get("mode_contracts", {})
    contract = {**contracts.get("*", {}), **contracts.get(mode, {})}
    resources = contract.get("resources")
    if not isinstance(resources, dict):
        raise GovernanceError(f"no reviewed resource plan: {entry.get('id')}:{mode}")
    required = list(_paths(resources.get("required_paths"), "resources.required_paths"))
    reference_max = _budget(resources.get("references_max"), "references_max")
    profile_max = _budget(resources.get("profiles_max"), "profiles_max", 1)
    stages = resources.get("stages", {})
    if not isinstance(stages, dict):
        raise GovernanceError("resources.stages must be an object")
    ordered: list[str] = []
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            raise GovernanceError("cyclic context stage dependency")
        if name in ordered:
            return
        item = stages.get(name)
        if not isinstance(item, dict):
            raise GovernanceError(f"unknown context stage: {name}")
        visiting.add(name)
        for dependency in _paths(item.get("depends_on", []), f"{name}.depends_on"):
            visit(dependency)
        visiting.remove(name)
        ordered.append(name)

    if stage is not None:
        visit(stage)
    for name in ordered:
        item = stages[name]
        required.extend(_paths(item.get("required_paths"), f"{name}.required_paths"))
        if "references_max" in item:
            reference_max = max(reference_max, _budget(item["references_max"], f"{name}.references_max"))

    skill_file = resolve_under(root, entry["path"])
    skill_root = skill_file.parent
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    reference_files: set[Path] = set()
    profile_files: set[Path] = set()
    for raw in ["SKILL.md", *required]:
        path_part, _, fragment = raw.partition("#")
        relative = PurePosixPath(path_part)
        if (not path_part or "\\" in path_part or ":" in path_part or relative.is_absolute()
                or any(part in {"..", "legacy-assets", "__pycache__"} for part in relative.parts)):
            raise GovernanceError(f"resource must be a current skill-relative path: {raw}")
        path = (skill_root / path_part).resolve()
        if not path.is_relative_to(skill_root.resolve()) or not path.is_file():
            raise GovernanceError(f"missing or escaping resource: {raw}")
        if "references" in relative.parts:
            reference_files.add(path)
        if "profiles" in relative.parts:
            profile_files.add(path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise GovernanceError(f"cannot read resource: {raw}") from exc
        if fragment:
            if path.suffix.lower() != ".md":
                raise GovernanceError(f"section anchors require Markdown: {raw}")
            text = section(text, fragment)
        key = (path.relative_to(root.resolve()).as_posix(), fragment)
        selected[key] = {"path": key[0], "fragment": fragment or None, "char_count": len(text),
                         "selected_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    # If the whole file is required, its sections do not add another reading cost.
    selected = {key: value for key, value in selected.items() if not key[1] or (key[0], "") not in selected}
    if len(reference_files) > reference_max or len(profile_files) > profile_max:
        raise GovernanceError("reviewed context plan exceeds its reference/profile budget")
    items = list(selected.values())
    return {"valid": True, "skill": entry["id"], "mode": mode, "context_stage": stage,
            "stage_dependencies": ordered, "output_sections": contract.get("output_sections", []),
            "resources": items, "reference_file_count": len(reference_files),
            "profile_file_count": len(profile_files), "total_selected_chars": sum(item["char_count"] for item in items),
            "measurement": "static_selected_text_characters", "includes_shared_safety_policies": False,
            "workflow_executed": False, "authorization_granted": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--stage")
    args = parser.parse_args()
    try:
        _, entries = load_registry(args.root)
        entry = next((item for item in entries if item["id"] == args.skill), None)
        if entry is None:
            raise GovernanceError(f"unknown Skill: {args.skill}")
        report = build_plan(args.root.resolve(), entry, args.mode, args.stage)
    except GovernanceError as exc:
        emit(json_text({"valid": False, "errors": [str(exc)]}), None)
        return 1
    emit(json_text(report), None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
