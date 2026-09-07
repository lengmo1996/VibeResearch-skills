#!/usr/bin/env python3
"""Export a validated Draw.io file with an optional local Draw.io CLI."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from validate_drawio import validate_path


CLI_CANDIDATES = ("drawio", "draw.io", "diagrams.net")
FORMATS = ("svg", "png", "pdf", "jpg")


class ExportError(RuntimeError):
    """Raised for safe, user-actionable export failures."""


def find_cli(explicit: str | None = None) -> str | None:
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return str(path)
        return shutil.which(explicit)
    for candidate in CLI_CANDIDATES:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def export(
    input_path: Path,
    output_path: Path,
    output_format: str,
    cli: str,
    force: bool = False,
    timeout: int = 120,
) -> None:
    if timeout <= 0:
        raise ExportError("timeout must be positive")
    errors = validate_path(input_path)
    if errors:
        raise ExportError("input Draw.io is invalid: " + "; ".join(errors))
    if output_path.exists() and not force:
        raise ExportError(f"output exists; pass --force to replace it: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="drawio-export-", dir=output_path.parent) as temp_dir:
        temporary = Path(temp_dir) / f"preview.{output_format}"
        command = [
            cli,
            "--export",
            "--format",
            output_format,
            "--output",
            str(temporary),
            str(input_path),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExportError(f"Draw.io CLI could not complete export: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic output"
            raise ExportError(f"Draw.io CLI exited with {completed.returncode}: {detail}")
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise ExportError("Draw.io CLI reported success but produced no non-empty output")
        os.replace(temporary, output_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Validated .drawio source")
    parser.add_argument("--format", choices=FORMATS, default="svg")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--drawio-bin", help="Explicit Draw.io executable or command")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    cli = find_cli(args.drawio_bin)
    if cli is None:
        parser.error(
            "Draw.io CLI not found. Keep the validated .drawio source and export it manually from "
            "diagrams.net, or pass --drawio-bin."
        )
    try:
        export(args.input, args.output, args.format, cli, args.force, args.timeout)
    except ExportError as exc:
        parser.error(str(exc))
    print(f"WROTE: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
