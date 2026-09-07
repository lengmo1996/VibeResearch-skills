#!/usr/bin/env python3
"""Read explicit user configuration for the public category-selected daily digest.

Configuration never grants permission to send. This helper performs no network,
Gmail, state initialization, or profile migration operations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from daily_digest_categories import ALIASES, CANONICAL_CATEGORIES, MAX_SELECTED_CATEGORIES

CONFIG_FILENAME = "daily-digest-config.json"
TRACKED_CATEGORIES = ()  # No research-category default is active before configuration.
TOPIC_GROUPS = ("direct_interest", "method_interest", "transfer_interest", "other_relevant")
NEUTRAL_TOPIC_LABELS = {
    "direct_interest": "直接关注主题", "method_interest": "方法主题",
    "transfer_interest": "可迁移主题", "other_relevant": "其他相关主题",
}


class PublicDigestConfigError(ValueError):
    """The explicit public digest configuration is missing, unsafe, or changed."""


def _terms(value: Any, label: str, required: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 64 or (required and not value):
        raise PublicDigestConfigError(f"public_digest_not_configured: {label} requires a bounded term list")
    result: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            raise PublicDigestConfigError(f"public_digest_not_configured: {label} term must be text")
        term = " ".join(raw.casefold().split())
        placeholder_text = re.sub(r"[_-]+", " ", term)
        if not 2 <= len(term) <= 128 or re.search(r"[<>\x00-\x1f]", term) or re.search(r"\b(?:todo|tbd|replace|placeholder|your topic|your keyword)\b|待填写|请填写", placeholder_text):
            raise PublicDigestConfigError(f"public_digest_not_configured: {label} contains an empty or placeholder term")
        if term not in result:
            result.append(term)
    return tuple(result)


def _absolute(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip() or any(char in value for char in "<>\x00"):
        raise PublicDigestConfigError(f"public_digest_not_configured: {label} must be an explicit absolute path")
    path = Path(value)
    if not path.is_absolute():
        raise PublicDigestConfigError(f"public_digest_not_configured: {label} must be absolute on this platform")
    return path.resolve()


def validate_config(data: Any, root: Path) -> dict[str, Any]:
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data.get("schema_version") != 1 or data.get("configured") is not True:
        raise PublicDigestConfigError("public_digest_not_configured: complete the example and set configured=true")
    supported = {"schema_version", "configured", "digest_root", "coordination_root", "recipient", "timezone",
                 "categories", "category_order", "report_category", "topic_tiers", "topic_labels", "architecture_terms", "context_terms", "exclusions"}
    if set(data) - supported:
        raise PublicDigestConfigError("public_digest_unknown_fields: configuration contains unsupported fields; sending authorization and output-language overrides are not configuration options")
    result = dict(data)
    actual_root = root.resolve()
    if _absolute(data.get("digest_root"), "digest_root") != actual_root:
        raise PublicDigestConfigError("public_digest_root_mismatch: --root differs from the configured digest_root")
    result["digest_root"] = str(actual_root)
    result["coordination_root"] = str(_absolute(data.get("coordination_root"), "coordination_root"))
    if data.get("recipient") != "me":
        raise PublicDigestConfigError("public_digest_recipient_unsupported: verified delivery supports authenticated self only")
    timezone = data.get("timezone")
    if not isinstance(timezone, str) or not timezone:
        raise PublicDigestConfigError("public_digest_not_configured: timezone is required")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise PublicDigestConfigError("public_digest_timezone_unavailable: provide a valid IANA timezone and local timezone data") from exc
    values = data.get("categories")
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_SELECTED_CATEGORIES or any(not isinstance(value, str) for value in values):
        raise PublicDigestConfigError("public_digest_categories_unsupported: choose 1..16 canonical specific arXiv categories")
    if len(values) != len(set(values)):
        raise PublicDigestConfigError("public_digest_categories_duplicate")
    for category in values:
        if category in ALIASES:
            raise PublicDigestConfigError(f"public_digest_category_alias: use canonical {ALIASES[category]} instead of {category}")
        if category not in CANONICAL_CATEGORIES:
            raise PublicDigestConfigError("public_digest_categories_unsupported: broad archives, wildcards, unknown codes and paths are not inventory categories")
    order = data.get("category_order")
    if not isinstance(order, list) or len(order) != len(values) or any(not isinstance(value, str) for value in order) or set(order) != set(values):
        raise PublicDigestConfigError("public_digest_category_order_invalid: category_order must be an exact permutation of categories")
    report_category = data.get("report_category")
    if not isinstance(report_category, str) or report_category not in values:
        raise PublicDigestConfigError("public_digest_report_category_invalid: explicitly select one configured category for the complete report")
    result["categories"], result["category_order"] = tuple(values), tuple(order)
    tiers = data.get("topic_tiers")
    if not isinstance(tiers, dict) or set(tiers) != {"A", "B", "C"}:
        raise PublicDigestConfigError("public_digest_not_configured: topic_tiers must declare A, B, and C")
    result["topic_tiers"] = {name: _terms(tiers[name], f"topic_tiers.{name}", required=name == "A") for name in "ABC"}
    labels = data.get("topic_labels")
    if not isinstance(labels, dict) or set(labels) != set(TOPIC_GROUPS):
        raise PublicDigestConfigError("public_digest_not_configured: topic_labels must declare the four public topic groups")
    for key, value in labels.items():
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 128 or any(ord(char) < 32 for char in value):
            raise PublicDigestConfigError(f"public_digest_not_configured: invalid label for {key}")
    result["topic_labels"] = dict(labels)
    result["architecture_terms"] = _terms(data.get("architecture_terms"), "architecture_terms")
    result["context_terms"] = _terms(data.get("context_terms"), "context_terms")
    exclusions = data.get("exclusions")
    if not isinstance(exclusions, dict) or set(exclusions) != {"primary", "secondary"}:
        raise PublicDigestConfigError("public_digest_not_configured: exclusions must explicitly declare primary and secondary lists")
    result["exclusions"] = {name: _terms(exclusions[name], f"exclusions.{name}") for name in ("primary", "secondary")}
    return result


def load_config(root: Path, config_path: Path | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    path = Path(config_path) if config_path is not None else root / CONFIG_FILENAME
    if path.resolve() != root / CONFIG_FILENAME or path.is_symlink():
        raise PublicDigestConfigError("public_digest_config_path_mismatch: configuration must be the regular config file inside its digest root")
    try:
        content = path.read_bytes()
        if len(content) > 128_000:
            raise PublicDigestConfigError("public_digest_config_too_large")
        data = json.loads(content)
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise PublicDigestConfigError("public_digest_not_configured: a readable daily-digest-config.json is required") from exc
    result = validate_config(data, root)
    result["_config_sha256"] = hashlib.sha256(content).hexdigest()
    binding = root / "config.md"
    if binding.exists():
        match = re.search(r"^public_profile_sha256: ([0-9a-f]{64})$", binding.read_text(encoding="utf-8"), re.MULTILINE)
        if match is None or match[1] != result["_config_sha256"]:
            raise PublicDigestConfigError("public_digest_configuration_changed: this state root is bound to its original configuration; restore the original JSON or use a new state root")
    elif any((root / marker).exists() for marker in ("pending-run.json", "sent-papers.json", "last-successful-run.json", "runs")):
        raise PublicDigestConfigError("public_digest_configuration_unbound: existing run, history, or cursor state cannot be reinterpreted under a new profile")
    return result


def apply_config(namespace: dict[str, Any], root: Path, config_path: Path | None = None) -> dict[str, Any]:
    namespace["_PUBLIC_DIGEST_CONFIG"] = None
    config = load_config(root, config_path)
    tiers = config["topic_tiers"]
    highlight = [term for name in "ABC" for term in tiers[name]]
    namespace.update(
        _PUBLIC_DIGEST_CONFIG=config,
        TOPIC_GROUPS=TOPIC_GROUPS,
        TOPIC_LABELS=dict(config["topic_labels"]),
        DIRECT_TOPIC_TERMS=tiers["A"], METHOD_TOPIC_TERMS=tiers["B"], TRANSFER_TOPIC_TERMS=tiers["C"],
        DEFAULT_TOPIC_TIERS={name: tuple(tiers[name]) for name in "ABC"},
        ARCHITECTURE_TERMS=config["architecture_terms"], VISION_CONTEXT_TERMS=config["context_terms"],
        CATEGORY_ORDER=tuple(config["category_order"]),
        TRACKED_CATEGORIES=tuple(config["categories"]), REPORT_CATEGORY=config["report_category"],
        THEME_RE=re.compile("(" + "|".join(re.escape(term) for term in sorted(set(highlight), key=lambda term: (-len(term), term))) + ")", re.IGNORECASE),
    )
    return config


def configured_topic_group(config: dict[str, Any], text: str) -> str:
    normalized = " ".join(text.casefold().split())
    for tier, group in zip("ABC", TOPIC_GROUPS[:3]):
        if any(term in normalized for term in config["topic_tiers"][tier]):
            return group
    return "other_relevant"


def configured_exclusion(config: dict[str, Any], text: str) -> str | None:
    normalized = " ".join(text.casefold().split())
    for name in ("primary", "secondary"):
        if any(term in normalized for term in config["exclusions"][name]):
            return "configured_" + name + "_exclusion"
    return None


def render_config_md(config: dict[str, Any]) -> str:
    # Operational limits remain defined by the reviewed runtime/protocol. This
    # companion records explicit user interests and binds this state root.
    values = {key: value for key, value in config.items() if not key.startswith("_")}
    return ("# Public Daily arXiv Digest Configuration\n\n"
            + "public_profile_sha256: " + config["_config_sha256"] + "\n\n"
            + "```json\n" + json.dumps(values, ensure_ascii=False, indent=2) + "\n```\n\n"
            + "This profile is immutable for this state root. Configuration does not authorize sending.\n"
            + "Use the complete bundled daily protocol; coverage of every selected category and the chosen complete-report category remain mandatory.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--check", action="store_true", required=True)
    args = parser.parse_args()
    config = load_config(args.root)
    print(json.dumps({"valid": True, "configured": True, "config_sha256": config["_config_sha256"],
                      "categories": config["categories"], "report_category": config["report_category"], "recipient": "me", "send_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublicDigestConfigError as exc:
        raise SystemExit(str(exc)) from exc
