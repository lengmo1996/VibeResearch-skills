#!/usr/bin/env python3
"""List contained run artifacts; never execute a run or modify its files."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from validate_run_manifest import load_manifest, validate_manifest


def contained(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def inventory(manifest_path: Path, workspace_root: Path, include_hash: bool) -> dict:
    data = load_manifest(manifest_path)
    errors = validate_manifest(data)
    if errors:
        raise ValueError("; ".join(errors))
    root = workspace_root.resolve()
    output_root = (root / data["output_root"]).resolve()
    if not contained(root, output_root):
        raise ValueError("output_root resolves outside workspace_root")
    files: list[dict] = []
    if output_root.exists():
        for path in sorted(output_root.rglob("*")):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if not contained(output_root, resolved):
                raise ValueError(f"artifact resolves outside output_root: {path}")
            item = {
                "path": resolved.relative_to(root).as_posix(),
                "size": resolved.stat().st_size,
            }
            if include_hash:
                digest = hashlib.sha256()
                with resolved.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                item["sha256"] = digest.hexdigest()
            files.append(item)
    return {
        "run_id": data["run"]["id"],
        "output_root": output_root.relative_to(root).as_posix(),
        "artifacts": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--hash", action="store_true")
    args = parser.parse_args()
    try:
        report = inventory(args.manifest, args.workspace_root, args.hash)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Unable to collect artifacts: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
