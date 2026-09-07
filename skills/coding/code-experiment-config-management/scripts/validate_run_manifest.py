#!/usr/bin/env python3
"""Validate a run manifest without executing or modifying the run."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


ID_PATTERNS = {
    "run": re.compile(r"^RUN-[A-Za-z0-9._-]+$"),
    "experiment": re.compile(r"^EXP-\d{3,}$"),
    "claim": re.compile(r"^CLM-\d{3,}$"),
    "protocol": re.compile(r"^PROT-[A-Za-z0-9._-]+$"),
    "metric": re.compile(r"^MET-\d{3,}$"),
}
STATUSES = {"planned", "running", "completed", "failed", "interrupted"}
ACCEPTANCE_STATUSES = {"pending", "passed", "failed", "blocked"}
SHELL_META = {"&&", "||", ";", "|", ">", "<", "`"}
UNRESOLVED = {"", "unknown", "unresolved", "tbd", "n/a", "not provided / unclear"}


def _resolved_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() not in UNRESOLVED


def _relative_output_path(value: str) -> bool:
    path = PurePosixPath(value.replace("\\", "/"))
    windows = PureWindowsPath(value)
    return bool(path.parts) and not path.is_absolute() and not windows.anchor and ".." not in path.parts


def _contained(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _ids(errors: list[str], values: Any, label: str, pattern: re.Pattern[str]) -> None:
    if not isinstance(values, list) or not values:
        errors.append(f"{label} must be a non-empty list")
        return
    for value in values:
        if not isinstance(value, str) or not pattern.fullmatch(value):
            errors.append(f"invalid {label} value: {value!r}")


def validate_manifest(
    data: Any, *, execution_ready: bool = False, workspace_root: Path | None = None
) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest must be a JSON object"]
    required = (
        "schema_version",
        "run",
        "launch",
        "identity",
        "output_root",
        "acceptance_criteria",
        "artifacts",
    )
    for key in required:
        if key not in data:
            errors.append(f"missing field: {key}")
    if data.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")

    run = data.get("run")
    if isinstance(run, dict):
        run_id = run.get("id")
        if not isinstance(run_id, str) or not ID_PATTERNS["run"].fullmatch(run_id):
            errors.append("run.id must match RUN-*")
        _ids(errors, run.get("experiment_ids"), "experiment_ids", ID_PATTERNS["experiment"])
        _ids(errors, run.get("claim_ids"), "claim_ids", ID_PATTERNS["claim"])
        _ids(errors, run.get("protocol_ids"), "protocol_ids", ID_PATTERNS["protocol"])
        _ids(errors, run.get("metric_ids"), "metric_ids", ID_PATTERNS["metric"])
        if run.get("status") not in STATUSES:
            errors.append("run.status is invalid")
    else:
        errors.append("run must be an object")

    launch = data.get("launch")
    if isinstance(launch, dict):
        entrypoint = launch.get("entrypoint")
        argv = launch.get("argv")
        if not isinstance(entrypoint, str) or not entrypoint.strip():
            errors.append("launch.entrypoint is required")
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
            errors.append("launch.argv must be a string list")
        else:
            for token in argv:
                if token in SHELL_META or "$(" in token or "\n" in token or "\r" in token:
                    errors.append(f"launch.argv contains shell expansion token: {token!r}")
        working = launch.get("working_directory")
        if not isinstance(working, str) or not working:
            errors.append("launch.working_directory is required")
    else:
        errors.append("launch must be an object")

    output_root = data.get("output_root")
    if not _resolved_text(output_root):
        errors.append("output_root is required")
    elif not _relative_output_path(output_root):
        errors.append("output_root must be a relative contained path distinct from the workspace root")

    criteria = data.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria:
        errors.append("acceptance_criteria must be a non-empty list")
    else:
        for item in criteria:
            if not isinstance(item, dict):
                errors.append("acceptance criterion must be an object")
                continue
            if not isinstance(item.get("id"), str) or not item["id"].startswith("ACC-"):
                errors.append("acceptance criterion id must match ACC-*")
            if not isinstance(item.get("description"), str) or not item["description"].strip():
                errors.append("acceptance criterion description is required")
            if item.get("status") not in ACCEPTANCE_STATUSES:
                errors.append("acceptance criterion status is invalid")
            if not isinstance(item.get("evidence_refs"), list):
                errors.append("acceptance criterion evidence_refs must be a list")

    if not isinstance(data.get("identity"), dict):
        errors.append("identity must be an object")
    if not isinstance(data.get("artifacts"), list):
        errors.append("artifacts must be a list")
    if execution_ready:
        identity = data.get("identity")
        if isinstance(identity, dict):
            for field in ("code", "data", "config_fingerprint"):
                if not _resolved_text(identity.get(field)):
                    errors.append(f"execution-ready manifest requires resolved identity.{field}")
            seeds = identity.get("seeds")
            if not isinstance(seeds, dict) or not seeds:
                errors.append("execution-ready manifest requires a non-empty identity.seeds object")
            else:
                for name, seed in seeds.items():
                    if not _resolved_text(name) or isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
                        errors.append("identity.seeds must map component names to non-negative integers")
        if workspace_root is None:
            errors.append("execution-ready validation requires workspace_root")
        else:
            try:
                root = workspace_root.resolve(strict=True)
                if not root.is_dir():
                    errors.append("workspace_root must be an existing directory")
                if isinstance(output_root, str) and _relative_output_path(output_root):
                    resolved_output = (root / output_root.replace("\\", "/")).resolve()
                    if resolved_output == root or not _contained(root, resolved_output):
                        errors.append("output_root resolves outside the isolated workspace output boundary")
                if isinstance(launch, dict):
                    working = launch.get("working_directory")
                    entrypoint = launch.get("entrypoint")
                    if _resolved_text(working) and _resolved_text(entrypoint):
                        working_path = (root / working).resolve(strict=True)
                        entrypoint_path = (working_path / entrypoint).resolve(strict=True)
                        if not working_path.is_dir() or not _contained(root, working_path):
                            errors.append("launch.working_directory must resolve inside workspace_root")
                        if not entrypoint_path.is_file() or not _contained(root, entrypoint_path):
                            errors.append("launch.entrypoint must resolve to a repository-native file")
                    else:
                        errors.append("execution-ready launch paths must be resolved")
            except (OSError, RuntimeError, ValueError) as exc:
                errors.append(f"execution-ready path resolution failed: {exc}")
    return errors


def load_manifest(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--execution-ready", action="store_true", help="Check identity and local path prerequisites before execution; does not authorize or launch a run.")
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.self_test:
        sample = Path(__file__).resolve().parents[1] / "templates" / "run_manifest.json"
        errors = validate_manifest(load_manifest(sample))
        unsafe = load_manifest(sample)
        unsafe["launch"]["argv"] = ["--config", "x", "&&", "other"]
        if errors or not validate_manifest(unsafe):
            print("Self-test failed.", file=sys.stderr)
            return 1
        print("Self-test passed.")
        return 0
    if args.manifest is None:
        parser.error("provide a manifest path or use --self-test")
    try:
        errors = validate_manifest(load_manifest(args.manifest), execution_ready=args.execution_ready,
                                   workspace_root=args.workspace_root)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Unable to read manifest: {exc}", file=sys.stderr)
        return 2
    if errors:
        print("Run manifest validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Run manifest execution prerequisites are valid." if args.execution_ready else
          "Run manifest structure is valid; execution readiness was not checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
