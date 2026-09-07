#!/usr/bin/env python3
"""Validate a paper-to-ppt visual plan without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("The visual plan must be a JSON object.")
    return data


def relative_luminance(color: str) -> float:
    if not HEX_COLOR.match(color):
        raise ValueError(f"Invalid hex color: {color}")
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first: str, second: str) -> float:
    high, low = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    required_root = {"schema_version", "brief", "candidates", "visual_system", "slides", "warnings"}
    missing_root = sorted(required_root - set(plan))
    if missing_root:
        errors.append(f"Missing root fields: {', '.join(missing_root)}")

    candidates = plan.get("candidates", [])
    if not isinstance(candidates, list) or not 2 <= len(candidates) <= 4:
        errors.append("candidates must contain between 2 and 4 visual directions.")

    system = plan.get("visual_system", {})
    palette = system.get("palette", {}) if isinstance(system, dict) else {}
    try:
        text_contrast = contrast_ratio(palette["text"], palette["background"])
        checks["text_background_contrast"] = round(text_contrast, 2)
        if text_contrast < 4.5:
            errors.append(f"Text/background contrast is {text_contrast:.2f}:1; require at least 4.5:1.")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"Cannot validate text/background contrast: {exc}")

    type_sizes = system.get("type_sizes_pt", {}) if isinstance(system, dict) else {}
    if float(type_sizes.get("title", 0)) < 28:
        errors.append("Primary title size must be at least 28 pt.")
    if float(type_sizes.get("body", 0)) < 18:
        errors.append("Body size must be at least 18 pt.")
    if float(type_sizes.get("source", 0)) < 9:
        warnings.append("Source trace below 9 pt may be unreadable in projection or PDF.")

    spacing = system.get("spacing", {}) if isinstance(system, dict) else {}
    if float(spacing.get("safe_margin_in", 0)) < 0.35:
        errors.append("Global safe margin must be at least 0.35 in.")

    slides = plan.get("slides", [])
    if not isinstance(slides, list):
        errors.append("slides must be an array.")
        slides = []

    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            errors.append(f"Slide {index} must be an object.")
            continue
        slide_id = str(slide.get("id") or index)
        layout = slide.get("layout", {})
        if float(layout.get("safe_margin_in", 0)) < 0.35:
            errors.append(f"{slide_id}: safe margin must be at least 0.35 in.")
        if int(slide.get("item_count", 0)) > int(layout.get("max_items", 0)):
            warnings.append(f"{slide_id}: content exceeds the selected layout capacity.")

        accessibility = slide.get("accessibility", {})
        if accessibility.get("color_not_only") is not True:
            errors.append(f"{slide_id}: color_not_only must be true.")
        if accessibility.get("alt_text_required") and not str(accessibility.get("alt_text", "")).strip():
            errors.append(f"{slide_id}: meaningful visual lacks alt text or a note description.")
        if not accessibility.get("reading_order"):
            warnings.append(f"{slide_id}: reading order is not documented.")

        interaction = slide.get("interaction", {})
        if interaction.get("linear_fallback") is not True:
            errors.append(f"{slide_id}: interactive navigation requires a linear fallback.")

        motion = slide.get("motion", {})
        if motion.get("type", "none") != "none":
            if motion.get("static_fallback") is not True:
                errors.append(f"{slide_id}: motion requires a static export fallback.")
            if motion.get("reduced_motion") is not True:
                errors.append(f"{slide_id}: motion requires a reduced-motion path.")

        chart = slide.get("chart")
        if isinstance(chart, dict):
            required_fields = {str(value) for value in chart.get("required_fields", [])}
            present_fields = {str(value) for value in chart.get("fields_present", [])}
            missing_fields = sorted(required_fields - present_fields)
            if missing_fields:
                errors.append(f"{slide_id}: chart fields missing: {', '.join(missing_fields)}.")
            if not str(chart.get("source_trace", "")).strip():
                errors.append(f"{slide_id}: chart requires a source trace.")
            if not chart.get("accessibility_rules"):
                errors.append(f"{slide_id}: chart accessibility rules are missing.")

    checks["slide_count"] = len(slides)
    checks["error_count"] = len(errors)
    checks["warning_count"] = len(warnings)
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path, help="Visual plan JSON to validate.")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = validate_plan(load_json(args.plan))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("PASS" if result["valid"] else "FAIL")
        for error in result["errors"]:
            print(f"ERROR: {error}")
        for warning in result["warnings"]:
            print(f"WARNING: {warning}")
        print(json.dumps(result["checks"], ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
