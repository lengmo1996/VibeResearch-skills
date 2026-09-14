#!/usr/bin/env python3
"""Validate a public Skill tree without private history or third-party packages.

This is a structural and bounded privacy check, not publication authorization or
proof of copyright ownership. All findings include a rule and relative location.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from typing import Any
from urllib.parse import unquote, urlsplit

PRIVATE_PATTERNS = {
    "home_path": r"(?i)(?:[a-z]:[\\/]+Users[\\/]+[^\s/\\\"'<>]+|/(?:home|Users)/[^\s/\\\"'<>]+)",
    "private_ipv4": r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b",
    "private_key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "api_secret": r"\b(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{24,})\b",
    "secret_assignment": r"(?i)(?:api[_-]?key|client[_-]?secret|access[_-]?token)\s*[\"']?\s*[:=]\s*[\"'][A-Za-z0-9._/+~-]{24,}[\"']",
    "bearer_secret": r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{24,}",
    "email_address": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
}
ALLOWED_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "invalid.test"}
IGNORED_BUILD_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", ".test-tmp", "dist"}
NAME_RE = re.compile(r"^(?:paper|literature|research|code|writing|publish|visual|tool)-[a-z0-9]+(?:-[a-z0-9]+)*$")


def safe_relative(path: str) -> bool:
    if not isinstance(path, str) or not path or path in {".", ".."} or "\\" in path or re.search(r'[<>:"|?*\x00-\x1f]', path):
        return False
    value = PurePosixPath(path)
    if value.is_absolute() or path != value.as_posix():
        return False
    return all(part not in {".", ".."} and part.casefold() != ".git" and not part.endswith((".", " "))
               and not re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
               for part in value.parts)


def _validate_paths(paths: list[str]) -> None:
    if not isinstance(paths, list) or any(not safe_relative(path) for path in paths):
        raise ValueError("PUBLIC_FILES must contain safe canonical relative file paths")
    folded: set[str] = set()
    components: dict[str, str] = {}
    for path in paths:
        if path.casefold() in folded:
            raise ValueError("Duplicate or case-colliding public file path")
        folded.add(path.casefold())
        parts = PurePosixPath(path).parts
        if any(part.casefold() in IGNORED_BUILD_DIRS for part in parts):
            raise ValueError("Build/cache/Git directories cannot contain declared public source files")
        for index in range(1, len(parts) + 1):
            component = "/".join(parts[:index])
            previous = components.setdefault(component.casefold(), component)
            if previous != component:
                raise ValueError("Case-colliding public directory")
    for path in paths:
        parts = PurePosixPath(path).parts
        if any("/".join(parts[:index]).casefold() in folded for index in range(1, len(parts))):
            raise ValueError("Public file/directory prefix collision")


def _linked(path: Path) -> bool:
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    # pathlib.is_junction was added after Python 3.11. Reparse-point metadata
    # keeps the public package's supported 3.11 Windows check conservative.
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _scalar(text: str, key: str) -> str:
    match = re.search(r"^\s*" + re.escape(key) + r":\s*(.*?)\s*$", text, re.MULTILINE)
    return match[1].strip("\"'") if match else ""


def _anchors(text: str) -> set[str]:
    result: set[str] = set()
    counts: dict[str, int] = {}
    fence = False
    for line in text.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            fence = not fence
        if fence:
            continue
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            title = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", match[1])
            slug = re.sub(r"[^\w\-\s]", "", title.lower()).replace(" ", "-")
            number = counts.get(slug, 0)
            counts[slug] = number + 1
            result.add(slug + (f"-{number}" if number else ""))
    return result


def privacy_findings(path: str, data: bytes, exceptions: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    text = data.decode("utf-8-sig")
    digest = hashlib.sha256(data).hexdigest()
    findings = []
    for rule, pattern in PRIVATE_PATTERNS.items():
        for match in re.finditer(pattern, text):
            value = match[0]
            if rule == "email_address" and value.rsplit("@", 1)[1].lower() in ALLOWED_EMAIL_DOMAINS:
                continue  # RFC-reserved illustrative addresses, not an examples-directory bypass.
            accepted = any(item.get("path") == path and item.get("sha256") == digest and item.get("rule") == rule
                           and item.get("match") == value and item.get("reason") and item.get("review_status") == "approved"
                           for item in (exceptions or []))
            if not accepted:
                findings.append({"path": path, "line": text[:match.start()].count("\n") + 1,
                                 "rule": rule, "message": "Possible private value; inspect the exact file locally."})
    return findings


def validate(root: Path) -> dict[str, Any]:
    linked_root = _linked(root)
    root = root.resolve()
    errors: list[dict[str, Any]] = []
    report: dict[str, Any] = {"valid": False, "errors": errors, "skill_count": 0, "file_count": 0,
                              "routing_modes_checked": 0, "context_plans_checked": 0, "plugin_context_plans_checked": 0,
                              "historical_baseline": "not_applicable_for_initial_public_release",
                              "publication_authorized": False, "provenance_clearance": "requires_separate_review"}

    def fail(path: str, rule: str, message: str):
        errors.append({"path": path, "rule": rule, "message": message})

    try:
        if linked_root:
            raise ValueError("Linked public root is not accepted")
        declared = json.loads((root / "PUBLIC_FILES.json").read_text(encoding="utf-8"))["files"]
        _validate_paths(declared)
        declared_set = set(declared) | {"PUBLIC_FILES.json"}
        data: dict[str, bytes] = {}

        def walk_error(error):
            raise error

        for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
            for name in list(dirs):
                child = Path(directory) / name
                relative = child.relative_to(root).as_posix()
                if _linked(child):
                    fail(relative, "symlink", "Directory links are not accepted")
                    dirs.remove(name)
                elif name.casefold() in IGNORED_BUILD_DIRS:
                    dirs.remove(name)
            for name in names:
                path = Path(directory) / name
                relative = path.relative_to(root).as_posix()
                if _linked(path):
                    fail(relative, "symlink", "File links are not accepted")
                    continue
                data[relative] = path.read_bytes()
        _validate_paths(list(data))
        for path in sorted(declared_set - data.keys()):
            fail(path, "missing_file", "Declared public file is missing")
        for path in sorted(data.keys() - declared_set):
            fail(path, "undeclared_file", "File was not included in the reviewed public file list")
        report["file_count"] = len(data)
        exceptions = json.loads(data.get("privacy-exceptions.json", b"{\"exceptions\":[]}"))["exceptions"]
        text: dict[str, str] = {}
        for path, content in data.items():
            if any(part in {"legacy-assets", "profiles"} for part in PurePosixPath(path).parts):
                fail(path, "private_archive", "Personal profile/archive directory is not public")
            try:
                text[path] = content.decode("utf-8-sig")
                errors.extend(privacy_findings(path, content, exceptions))
            except UnicodeError:
                fail(path, "unreviewed_binary", "Binary content requires a separate explicit review profile")
            if path.endswith(".py"):
                try:
                    ast.parse(text[path], filename=path)
                except (SyntaxError, KeyError) as exc:
                    fail(path, "python_syntax", str(exc))
        registry = json.loads(data["skills/registry.yaml"])
        entries = registry["skills"]
        by_id = {entry["id"]: entry for entry in entries}
        if len(by_id) != len(entries) or len(entries) != 31:
            fail("skills/registry.yaml", "registry_size", "Expected 31 distinct public Skills")
        report["skill_count"] = len(entries)
        discovered = {path for path in data if path.startswith(("skills/global/", "skills/coding/")) and path.endswith("/SKILL.md")}
        if discovered != {entry["path"] for entry in entries}:
            fail("skills/registry.yaml", "entrypoint_set", "Registry and canonical Skill entrypoints disagree")
        for entry in entries:
            name = entry["id"]
            path = entry["path"]
            source = text.get(path, "")
            frontmatter = source.split("---", 2)[1] if source.startswith("---\n") or source.startswith("---\r\n") else ""
            if not NAME_RE.fullmatch(name) or name != entry.get("name") or PurePosixPath(path).parent.name != name or _scalar(frontmatter, "name") != name:
                fail(path, "skill_name", "Canonical prefix, directory, registry, and frontmatter must agree")
            if not _scalar(frontmatter, "description").strip():
                fail(path, "description", "Description must identify the main trigger")
            ui_path = str(PurePosixPath(path).parent / "agents/openai.yaml")
            ui = text.get(ui_path, "")
            for key in ("display_name", "short_description", "default_prompt"):
                if not re.search(r"[\u4e00-\u9fff]", _scalar(ui, key)):
                    fail(ui_path, "chinese_ui", f"Missing Chinese {key}")
            if "$" + name not in _scalar(ui, "default_prompt"):
                fail(ui_path, "invocation", "Default prompt must contain the canonical invocation")
            for field in ("handoff_to", "references_to", "dependencies"):
                for target in entry.get(field, []):
                    if target not in by_id:
                        fail(path, "missing_skill_dependency", f"{field}: {target}")
            prefix = str(PurePosixPath(path).parent) + "/"
            for canonical, content in data.items():
                if not canonical.startswith(prefix):
                    continue
                mirror = "plugins/research-skills/skills/" + name + "/" + canonical[len(prefix):]
                expected = content.replace(b"../../_shared/", b"../_shared/") if canonical.endswith(".md") else content
                if data.get(mirror) != expected:
                    fail(mirror, "plugin_mirror", "Generated plugin does not match canonical source")
        for path, content in data.items():
            if path.startswith("skills/_shared/") and data.get("plugins/research-skills/" + path) != content:
                fail(path, "shared_mirror", "Plugin shared resource mismatch")
        for path in {"LICENSE", "NOTICE.md", "LICENSES/Apache-2.0.txt"} | {p for p in data if p.startswith("LICENSES/")}:
            if path not in data:
                fail(path, "missing_license", "Required distribution notice or license is missing")
            elif data.get("plugins/research-skills/" + path) != data[path]:
                fail(path, "license_mirror", "Plugin must include the same distribution notices and license text")
        expected_plugin_skills = {"plugins/research-skills/skills/" + item["id"] + "/SKILL.md" for item in entries}
        actual_plugin_skills = {path for path in data if path.startswith("plugins/research-skills/skills/") and path.endswith("/SKILL.md")}
        if expected_plugin_skills != actual_plugin_skills:
            fail("plugins/research-skills/skills", "plugin_skill_set", "Plugin Skill entrypoints must exactly match the public registry")
        plugin = json.loads(data["plugins/research-skills/.codex-plugin/plugin.json"])
        if plugin.get("name") != "research-skills" or plugin.get("skills") != "./skills/" or "mcpServers" in plugin:
            fail("plugins/research-skills/.codex-plugin/plugin.json", "plugin_manifest", "Unexpected plugin identity or bundled service")
        plugin_registry = json.loads(data["plugins/research-skills/skills/registry.yaml"])
        expected_plugin_registry = json.loads(data["skills/registry.yaml"])
        for item in expected_plugin_registry["skills"]:
            item["path"] = "skills/" + item["id"] + "/SKILL.md"
        if plugin_registry != expected_plugin_registry:
            fail("plugins/research-skills/skills/registry.yaml", "plugin_registry", "Standalone plugin registry paths or contracts disagree")
        for path, content in text.items():
            if not path.endswith(".md"):
                continue
            for match in re.finditer(r"\[[^\]]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)", content):
                target = match[1].strip("<>")
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc:
                    continue
                if "<" in target or ">" in target or "{" in target:
                    continue  # Explicit parameterized links are template values.
                file_part, _, fragment = unquote(target).partition("#")
                resolved = (root / PurePosixPath(path).parent / file_part).resolve()
                try:
                    relative = resolved.relative_to(root).as_posix()
                except ValueError:
                    fail(path, "link_escape", target)
                    continue
                if not resolved.exists():
                    fail(path, "missing_link", target)
                elif fragment and relative in text and fragment not in _anchors(text[relative]):
                    fail(path, "missing_anchor", target)
        scripts = str(root / "scripts/skills")
        sys.path.insert(0, scripts)
        try:
            # Loading these modules has no filesystem mutation or network effects.
            _load_module(root / "scripts/skills/common.py", "common")
            router = _load_module(root / "scripts/skills/router.py", "public_profile_router")
            planner = _load_module(root / "scripts/skills/plan_context.py", "public_profile_context")
            for entry in entries:
                for mode in entry.get("modes", []):
                    decision = router.route(f"${entry['id']} mode: {mode}", entries)
                    report["routing_modes_checked"] += 1
                    if decision.primary_skill != entry["id"] or decision.mode != mode:
                        if not (entry["id"] == "literature-synthesis" and mode == "compare" and decision.mode == "comparison"):
                            fail(entry["path"], "mode_route", f"Explicit mode routed incorrectly: {mode}")
                    contract = {**entry.get("mode_contracts", {}).get("*", {}), **entry.get("mode_contracts", {}).get(mode, {})}
                    if "resources" in contract:
                        for stage in [None, *contract["resources"].get("stages", {})]:
                            planner.build_plan(root, entry, mode, stage)
                            report["context_plans_checked"] += 1
            for entry in plugin_registry["skills"]:
                for mode in entry.get("modes", []):
                    contract = {**entry.get("mode_contracts", {}).get("*", {}), **entry.get("mode_contracts", {}).get(mode, {})}
                    if "resources" in contract:
                        for stage in [None, *contract["resources"].get("stages", {})]:
                            planner.build_plan(root / "plugins/research-skills", entry, mode, stage)
                            report["plugin_context_plans_checked"] += 1
        finally:
            sys.path.remove(scripts)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        fail(".", "validation_error", str(exc))
    report["valid"] = not errors
    return report


def run_tests(root: Path) -> list[dict[str, Any]]:
    results = []
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
    declared = json.loads((root / "PUBLIC_FILES.json").read_text(encoding="utf-8"))["files"]
    groups = sorted({str(PurePosixPath(path).parent) for path in declared if PurePosixPath(path).name.startswith("test_") and path.endswith(".py") and not path.startswith("plugins/")})
    commands = [[sys.executable, "-B", "-m", "unittest", "discover", "-s", group, "-p", "test_*.py"] for group in groups]
    for path in declared:
        if path.startswith(("skills/global/", "skills/coding/")) and "/scripts/" in path and path.endswith(".py"):
            source = (root / path).read_text(encoding="utf-8")
            if re.search(r"add_argument\(\s*[\"']--self-test[\"']", source):
                commands.append([sys.executable, "-B", path, "--self-test"])
    for command in commands:
        process = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
        results.append({"command": command[2:], "returncode": process.returncode, "output": (process.stdout + process.stderr)[-12000:]})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--build-check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    report = validate(root)
    if report["valid"] and args.test:
        report["tests"] = run_tests(root)
        report["valid"] = all(result["returncode"] == 0 for result in report["tests"])
    if report["valid"] and args.build_check:
        builder = _load_module(root / "scripts/build_public.py", "public_profile_build")
        first, second = builder.build_bytes(root), builder.build_bytes(root)
        report["reproducible_archive"] = first == second
        report["archive_sha256"] = hashlib.sha256(first).hexdigest()
        report["valid"] = first == second
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
