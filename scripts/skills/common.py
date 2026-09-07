#!/usr/bin/env python3
"""Shared, dependency-free helpers for Skill governance commands.

The repository deliberately stores ``*.yaml`` governance artifacts as JSON-
compatible YAML.  Parsing them with :mod:`json` keeps CI deterministic and
avoids making PyYAML a hidden runtime dependency.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = Path("skills/registry.yaml")
WORKFLOWS_PATH = Path("tests/skills/user_workflows.yaml")


class GovernanceError(ValueError):
    """Raised for actionable input or repository-governance errors."""


def load_json_yaml(path: Path) -> Any:
    """Load a JSON-compatible YAML document and give a useful parse error."""

    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise GovernanceError(f"cannot read {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GovernanceError(
            f"{path}: expected JSON-compatible YAML; line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc


def load_registry(root: Path, registry: Path | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load a registry and normalize list- or mapping-shaped Skill entries."""

    path = resolve_under(root, registry or REGISTRY_PATH)
    raw = load_json_yaml(path)
    if not isinstance(raw, Mapping):
        raise GovernanceError(f"{path}: registry root must be an object")
    skills = raw.get("skills")
    entries: list[dict[str, Any]] = []
    if isinstance(skills, list):
        for index, entry in enumerate(skills, 1):
            if not isinstance(entry, Mapping):
                raise GovernanceError(f"{path}: skills[{index}] must be an object")
            entries.append(dict(entry))
    elif isinstance(skills, Mapping):
        for skill_id, entry in skills.items():
            if not isinstance(entry, Mapping):
                raise GovernanceError(f"{path}: skills[{skill_id!r}] must be an object")
            normalized = dict(entry)
            normalized.setdefault("id", str(skill_id))
            entries.append(normalized)
    else:
        raise GovernanceError(f"{path}: 'skills' must be an array or object")
    return dict(raw), entries


def load_cases(root: Path, cases_path: Path | None = None) -> list[dict[str, Any]]:
    """Load an evaluation document with a top-level ``cases`` array."""

    path = resolve_under(root, cases_path or WORKFLOWS_PATH)
    raw = load_json_yaml(path)
    if not isinstance(raw, Mapping) or not isinstance(raw.get("cases"), list):
        raise GovernanceError(f"{path}: expected an object with a 'cases' array")
    cases: list[dict[str, Any]] = []
    for index, case in enumerate(raw["cases"], 1):
        if not isinstance(case, Mapping):
            raise GovernanceError(f"{path}: cases[{index}] must be an object")
        cases.append(dict(case))
    return cases


def resolve_under(root: Path, path: Path | str) -> Path:
    """Resolve ``path`` below ``root`` and reject path traversal."""

    root = root.resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise GovernanceError(f"path escapes repository root: {path}") from exc
    return candidate


def relative_posix(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def parse_frontmatter(path: Path) -> dict[str, str]:
    """Parse scalar frontmatter fields needed for inventory consistency."""

    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise GovernanceError(f"cannot read {path}: {exc}") from exc
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*?)\s*$", line)
        if not match:
            continue
        key, raw_value = match.groups()
        value = raw_value
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            if value[0] == '"':
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = value[1:-1]
            else:
                value = value[1:-1].replace("''", "'")
        result[key] = value
    return result


def discover_skill_docs(root: Path) -> list[dict[str, str]]:
    """Discover routable Skills; shared capabilities are intentionally excluded."""

    skills_root = root / "skills"
    records: list[dict[str, str]] = []
    if not skills_root.exists():
        return records
    for path in sorted(skills_root.rglob("SKILL.md")):
        relative = path.relative_to(skills_root)
        if relative.parts and relative.parts[0] == "_shared":
            continue
        metadata = parse_frontmatter(path)
        records.append(
            {
                "id": metadata.get("name", ""),
                "name": metadata.get("name", ""),
                "description": metadata.get("description", ""),
                "path": relative_posix(root, path.parent),
                "skill_file": relative_posix(root, path),
            }
        )
    return records


def flatten_strings(value: Any) -> list[str]:
    """Flatten registry values to comparable, non-sensitive strings."""

    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        result: list[str] = []
        for key, nested in value.items():
            result.append(str(key))
            result.extend(flatten_strings(nested))
        return result
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        result = []
        for nested in value:
            result.extend(flatten_strings(nested))
        return result
    return [str(value)]


_ASCII_WORD = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", re.I)
_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")


def tokens(value: Any) -> set[str]:
    """Tokenize English identifiers and CJK bigrams for explainable overlap."""

    result: set[str] = set()
    for item in flatten_strings(value):
        lowered = item.casefold()
        result.update(match.group(0) for match in _ASCII_WORD.finditer(lowered))
        for match in _CJK_RUN.finditer(lowered):
            run = match.group(0)
            if len(run) == 1:
                result.add(run)
            else:
                result.update(run[index : index + 2] for index in range(len(run) - 1))
    return result


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    return len(left & right) / len(left | right)


def path_matches(path: str, pattern: str) -> bool:
    """Match repository POSIX paths against proposal path patterns."""

    normalized_path = path.replace("\\", "/")
    normalized_pattern = pattern.replace("\\", "/")
    if normalized_path.startswith("./"):
        normalized_path = normalized_path[2:]
    if normalized_pattern.startswith("./"):
        normalized_pattern = normalized_pattern[2:]
    normalized_path = normalized_path.lstrip("/")
    normalized_pattern = normalized_pattern.lstrip("/")
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3].rstrip("/")
        return normalized_path == prefix or normalized_path.startswith(prefix + "/")
    return PurePosixPath(normalized_path).match(normalized_pattern)


def markdown_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Render a compact GitHub-flavored Markdown table."""

    def cell(value: Any) -> str:
        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    header = "| " + " | ".join(cell(item) for item in headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(cell(item) for item in row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def emit(text: str, output: str | None = None) -> None:
    """Print output or write it only when an explicit output path is supplied."""

    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip() + "\n", encoding="utf-8")
    else:
        try:
            print(text)
        except UnicodeEncodeError:
            sys.stdout.buffer.write((text + "\n").encode("utf-8"))


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def semver(value: Any) -> bool:
    return isinstance(value, str) and bool(
        re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value)
    )


def list_of_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)
