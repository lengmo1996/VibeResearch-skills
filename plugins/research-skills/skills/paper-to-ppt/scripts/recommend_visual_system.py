#!/usr/bin/env python3
"""Recommend a deterministic research-presentation visual system and slide plan."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = SKILL_ROOT / "assets" / "catalogs"
KNOWN_DECK_TYPES = {
    "paper-talk",
    "lab-meeting",
    "project-update",
    "defense",
    "conference",
    "course",
}
KNOWN_LANGUAGES = {"zh", "en", "bilingual"}
VISUAL_CONTENT_TYPES = {
    "hero-visual",
    "evidence",
    "input-output",
    "pipeline",
    "architecture",
    "flow",
    "chart",
    "table",
    "matrix",
    "small-multiples",
    "image-grid",
    "comparison",
}


class BriefError(ValueError):
    """Raised when the visual-design brief cannot be processed safely."""


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise BriefError(f"Expected a JSON object in {path}")
    return data


def normalize(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    return [normalize(item) for item in value if str(item).strip()]


def validate_brief(brief: dict[str, Any]) -> None:
    if not isinstance(brief, dict):
        raise BriefError("The brief must be a JSON object.")
    if "slides" not in brief or not isinstance(brief["slides"], list):
        raise BriefError("The brief must contain a slides array.")
    for key in ("deck_type", "audience"):
        if not str(brief.get(key, "")).strip():
            raise BriefError(f"The brief requires {key}.")
    language = normalize(brief.get("language", "bilingual"))
    if language not in KNOWN_LANGUAGES:
        raise BriefError("language must be zh, en, or bilingual.")
    aspect_ratio = str(brief.get("aspect_ratio", "16:9")).strip()
    if aspect_ratio not in {"16:9", "4:3"}:
        raise BriefError("aspect_ratio must be 16:9 or 4:3.")


def score_style(
    preset: dict[str, Any],
    deck_type: str,
    domain: str,
    tones: list[str],
    index: int,
) -> tuple[int, int]:
    score = 0
    deck_types = {normalize(item) for item in preset["preferred_deck_types"]}
    domains = {normalize(item) for item in preset["preferred_domains"]}
    preset_tones = {normalize(item) for item in preset["tone"]}
    if deck_type in deck_types:
        score += 6
    if domain and domain in domains:
        score += 4
    elif "general" in domains:
        score += 1
    score += 2 * len(set(tones) & preset_tones)
    return score, -index


def rank_styles(brief: dict[str, Any], presets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deck_type = normalize(brief["deck_type"])
    domain = normalize(brief.get("domain", "general"))
    tones = normalize_list(brief.get("tone"))
    ranked = sorted(
        enumerate(presets),
        key=lambda item: score_style(item[1], deck_type, domain, tones, item[0]),
        reverse=True,
    )
    candidate_count = int(brief.get("candidate_count", 3))
    candidate_count = max(2, min(4, candidate_count))
    candidates: list[dict[str, Any]] = []
    for index, preset in ranked[:candidate_count]:
        score, _ = score_style(preset, deck_type, domain, tones, index)
        candidates.append(
            {
                "id": preset["id"],
                "name": preset["name"],
                "score": score,
                "tone": preset["tone"],
                "palette": preset["palette"],
                "rationale": preset["rationale"],
            }
        )
    return candidates


def select_layout(
    slide: dict[str, Any],
    layouts: list[dict[str, Any]],
) -> dict[str, Any]:
    role = normalize(slide.get("role", "takeaway"))
    content_types = set(normalize_list(slide.get("content_types")))
    density = normalize(slide.get("density", "medium"))

    def layout_score(item: tuple[int, dict[str, Any]]) -> tuple[int, int]:
        index, layout = item
        score = 0
        if role in {normalize(value) for value in layout["roles"]}:
            score += 8
        score += 2 * len(content_types & {normalize(value) for value in layout["content_types"]})
        if density in {normalize(value) for value in layout["density"]}:
            score += 1
        return score, -index

    _, selected = max(enumerate(layouts), key=layout_score)
    return copy.deepcopy(selected)


def select_chart_rule(
    evidence_type: str,
    chart_rules: list[dict[str, Any]],
) -> dict[str, Any] | None:
    normalized = normalize(evidence_type)
    for rule in chart_rules:
        if normalized in {normalize(item) for item in rule["evidence_types"]}:
            return copy.deepcopy(rule)
    return None


def slide_plan(
    source: dict[str, Any],
    layouts: list[dict[str, Any]],
    chart_rules: list[dict[str, Any]],
    warnings: list[str],
    fallback_index: int,
) -> dict[str, Any]:
    slide_id = str(source.get("id") or f"slide-{fallback_index}")
    role = normalize(source.get("role", "takeaway"))
    content_types = normalize_list(source.get("content_types"))
    layout = select_layout(source, layouts)
    item_count = int(source.get("item_count", max(1, len(content_types))))
    visual_required = bool(set(content_types) & VISUAL_CONTENT_TYPES)
    alt_text = str(source.get("alt_text", "")).strip()
    source_trace = str(source.get("source_trace", "")).strip()
    interaction_intent = normalize(source.get("interaction_intent", "linear"))

    if item_count > int(layout["max_items"]):
        warnings.append(
            f"{slide_id}: item_count {item_count} exceeds {layout['id']} capacity "
            f"{layout['max_items']}; split or simplify the slide."
        )
    if visual_required and not alt_text:
        warnings.append(f"{slide_id}: meaningful visual requires alt text or an equivalent note.")

    chart = None
    evidence_type = normalize(source.get("evidence_type"))
    chart_rule = select_chart_rule(evidence_type, chart_rules) if evidence_type else None
    if chart_rule:
        fields_present = normalize_list(source.get("chart_fields"))
        chart = {
            "evidence_type": evidence_type,
            "recommended": chart_rule["recommended"],
            "avoid": chart_rule["avoid"],
            "required_fields": chart_rule["required"],
            "fields_present": fields_present,
            "accessibility_rules": chart_rule["accessibility"],
            "source_trace": source_trace,
        }
        if not source_trace:
            warnings.append(f"{slide_id}: chart or evidence view requires a source trace.")

    motion_type = "none"
    if interaction_intent in {"progressive-reveal", "compare-states"}:
        motion_type = "appear" if interaction_intent == "progressive-reveal" else "fade"
    elif role in {"method-overview", "key-module"}:
        motion_type = "appear"

    return {
        "id": slide_id,
        "role": role,
        "claim": str(source.get("claim", "")).strip(),
        "content_types": content_types,
        "density": normalize(source.get("density", "medium")),
        "item_count": item_count,
        "layout": {
            "id": layout["id"],
            "grid": layout["grid"],
            "safe_margin_in": layout["safe_margin_in"],
            "visual_ratio": layout["visual_ratio"],
            "max_items": layout["max_items"],
            "rules": layout["rules"],
        },
        "hierarchy": {
            "title_is_claim": role not in {"title", "section", "q-and-a"},
            "one_primary_visual": visual_required,
            "takeaway_adjacent_to_evidence": bool(chart or visual_required),
        },
        "chart": chart,
        "interaction": {
            "intent": interaction_intent,
            "linear_fallback": True,
        },
        "motion": {
            "type": motion_type,
            "purpose": "preserve reading order" if motion_type != "none" else "none",
            "static_fallback": True,
            "reduced_motion": True,
        },
        "accessibility": {
            "alt_text_required": visual_required,
            "alt_text": alt_text,
            "color_not_only": True,
            "reading_order": ["title", "primary-content", "takeaway", "source"],
        },
        "source_trace": source_trace,
    }


def build_plan(brief: dict[str, Any]) -> dict[str, Any]:
    validate_brief(brief)
    styles = load_json(CATALOG_ROOT / "academic-style-presets.json")["presets"]
    layouts = load_json(CATALOG_ROOT / "slide-layouts.json")["layouts"]
    chart_rules = load_json(CATALOG_ROOT / "chart-rules.json")["charts"]

    deck_type = normalize(brief["deck_type"])
    language = normalize(brief.get("language", "bilingual"))
    warnings: list[str] = []
    if deck_type not in KNOWN_DECK_TYPES:
        warnings.append(
            f"Unknown deck_type '{deck_type}'; using conservative general research defaults."
        )
    if not brief["slides"]:
        warnings.append("No slides were supplied; the visual system has no per-slide mapping.")

    candidates = rank_styles(brief, styles)
    selected_id = normalize(brief.get("selected_style"))
    selected = next((item for item in styles if item["id"] == selected_id), None)
    if selected_id and selected is None:
        warnings.append(f"Unknown selected_style '{selected_id}'; using the top-ranked candidate.")
    if selected is None:
        selected = next(item for item in styles if item["id"] == candidates[0]["id"])

    slide_plans = [
        slide_plan(item, layouts, chart_rules, warnings, index)
        for index, item in enumerate(brief["slides"], start=1)
        if isinstance(item, dict)
    ]
    if len(slide_plans) != len(brief["slides"]):
        warnings.append("One or more non-object slide entries were ignored.")

    return {
        "schema_version": "1.0.0",
        "brief": {
            "deck_type": deck_type,
            "audience": str(brief["audience"]).strip(),
            "language": language,
            "aspect_ratio": str(brief.get("aspect_ratio", "16:9")).strip(),
            "domain": normalize(brief.get("domain", "general")),
            "duration_minutes": brief.get("duration_minutes"),
            "venue": str(brief.get("venue", "")).strip(),
            "template_constraints": brief.get("template_constraints", []),
        },
        "candidates": candidates,
        "visual_system": {
            "style_id": selected["id"],
            "name": selected["name"],
            "palette": selected["palette"],
            "typography": selected["typography"][language],
            "type_sizes_pt": selected["typography"]["sizes_pt"],
            "spacing": selected["spacing"],
            "chart_style": selected["chart_style"],
            "motion_policy": selected["motion"],
            "rationale": selected["rationale"],
        },
        "slides": slide_plans,
        "validation_targets": {
            "normal_text_contrast": 4.5,
            "large_text_contrast": 3.0,
            "minimum_body_pt": 18,
            "minimum_title_pt": 28,
            "minimum_safe_margin_in": 0.35,
            "static_export_required": True,
        },
        "warnings": warnings,
    }


def to_markdown(plan: dict[str, Any]) -> str:
    system = plan["visual_system"]
    lines = [
        "# Presentation Visual Plan",
        "",
        "## Visual system",
        f"- Style: {system['name']} (`{system['style_id']}`)",
        f"- Rationale: {system['rationale']}",
        f"- Chart style: {system['chart_style']}",
        f"- Motion: {system['motion_policy']}",
        "",
        "## Candidate directions",
    ]
    for candidate in plan["candidates"]:
        lines.append(
            f"- **{candidate['name']}** (`{candidate['id']}`, score {candidate['score']}): "
            f"{candidate['rationale']}"
        )
    lines.extend(["", "## Slide mapping", "", "| Slide | Role | Layout | Motion |", "|---|---|---|---|"])
    for slide in plan["slides"]:
        lines.append(
            f"| {slide['id']} | {slide['role']} | {slide['layout']['id']} | "
            f"{slide['motion']['type']} |"
        )
    if plan["warnings"]:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in plan["warnings"])
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", required=True, type=Path, help="Input visual-design brief JSON.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path, help="Optional output path; stdout is the default.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        brief = load_json(args.brief)
        plan = build_plan(brief)
    except (OSError, json.JSONDecodeError, BriefError, KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    rendered = (
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
        if args.format == "json"
        else to_markdown(plan)
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
