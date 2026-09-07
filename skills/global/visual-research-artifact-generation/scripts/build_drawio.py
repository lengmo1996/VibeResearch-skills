#!/usr/bin/env python3
"""Build a deterministic, uncompressed Draw.io diagram from normalized JSON."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from drawio_model import SpecError, build_tree, load_presets, load_spec, serialize
from validate_drawio import validate_path


HERE = Path(__file__).resolve().parent
DEFAULT_PRESETS = HERE.parent / "assets" / "drawio-style-presets.json"


def build(input_path: Path, output_path: Path, presets_path: Path, force: bool = False) -> None:
    if output_path.exists() and not force:
        raise SpecError(f"output exists; pass --force to replace it: {output_path}")
    spec = load_spec(input_path)
    presets = load_presets(presets_path)
    tree = build_tree(spec, presets)
    payload = serialize(tree)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
        errors = validate_path(temporary)
        if errors:
            raise SpecError("generated Draw.io failed validation: " + "; ".join(errors))
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="UTF-8 normalized graph JSON")
    parser.add_argument("output", type=Path, help="Output .drawio path")
    parser.add_argument(
        "--presets",
        type=Path,
        default=DEFAULT_PRESETS,
        help="Style preset JSON (defaults to bundled presets)",
    )
    parser.add_argument("--force", action="store_true", help="Replace the exact output path")
    args = parser.parse_args(argv)
    try:
        build(args.input, args.output, args.presets, args.force)
    except SpecError as exc:
        parser.error(str(exc))
    print(f"WROTE: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
