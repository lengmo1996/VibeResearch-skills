#!/usr/bin/env python3
"""Create a deterministic public plugin ZIP from the declared public file set."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import zipfile


def build_bytes(root: Path) -> bytes:
    root = root.resolve()
    paths = json.loads((root / "PUBLIC_FILES.json").read_text(encoding="utf-8"))["files"]
    # Import through the standard dependency location, even when loaded by a
    # validation module using importlib rather than launched as a script.
    import importlib.util
    validation_spec = importlib.util.spec_from_file_location("public_build_path_validation", root / "scripts/validate_public.py")
    if validation_spec is None or validation_spec.loader is None:
        raise ValueError("Missing public path validator")
    validation = importlib.util.module_from_spec(validation_spec)
    validation_spec.loader.exec_module(validation)
    validation._validate_paths(paths)
    selected = sorted(path for path in paths if path.startswith("plugins/research-skills/"))
    if not selected:
        raise ValueError("No declared public plugin files")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for relative in selected:
            posix = PurePosixPath(relative)
            if posix.is_absolute() or ".." in posix.parts or "\\" in relative or ":" in relative:
                raise ValueError(f"Unsafe public file path: {relative}")
            path = root / relative
            if any(validation._linked(parent) for parent in (path, *path.parents) if parent != root.parent):
                raise ValueError(f"Symlink is not a public package file: {relative}")
            path.resolve().relative_to(root)
            name = relative.removeprefix("plugins/research-skills/")
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100644 << 16)
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, path.read_bytes())
    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from validate_public import validate
    report = validate(args.root)
    if report["errors"]:
        raise SystemExit(json.dumps(report, ensure_ascii=False, indent=2))
    content = build_bytes(args.root)
    output = args.output if args.output.is_absolute() else args.root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit("Output already exists; choose a new output path")
    output.write_bytes(content)
    print(json.dumps({"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
