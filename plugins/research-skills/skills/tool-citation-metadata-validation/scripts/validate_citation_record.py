#!/usr/bin/env python3
"""Validate a citation metadata ledger without resolving identifiers."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


RECORD_ID = re.compile(r"^CITE-[0-9]{3,8}$")
DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
ARXIV = re.compile(r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z-]+)?/\d{7})(?:v\d+)?$", re.I)
MODES = {"normalize", "resolve", "cross-check", "deduplicate", "version-link",
         "bibliography-audit", "full"}
VERDICTS = {"verified", "partial", "conflict", "unresolved"}
FIELD_STATES = {"verified", "single-source", "conflict", "missing", "not-applicable"}
SOURCE_STATES = {"resolved", "zero-hit", "rate-limited", "timeout", "access-denied",
                 "malformed-response", "not-queried"}
PLACEHOLDERS = {"", "unresolved", "unknown", "not provided", "not-provided", "not-queried"}
TEXT_FIELDS = {"title", "venue", "journal", "booktitle", "publisher", "series", "publication_status"}
YEAR_FIELDS = {"year", "publication_year", "online_year", "print_year"}


def supplied(value: Any) -> bool:
    return isinstance(value, str) and value.strip().casefold() not in PLACEHOLDERS


def comparison_key(field: str, value: Any) -> Any:
    """Conservative, field-specific comparison; never fuzzy-match identity values."""
    field = field.casefold().replace("-", "_")
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFC", value).strip()
        if field == "doi":
            normalized = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", normalized, flags=re.I)
            return ("doi", normalized.casefold())
        if field in TEXT_FIELDS or field in {"author", "authors", "family", "given", "name", "literal"}:
            return ("text", " ".join(normalized.split()).casefold())
        if field in YEAR_FIELDS and re.fullmatch(r"[0-9]{4}", normalized):
            return ("year", int(normalized))
        return ("str", normalized)
    if field in YEAR_FIELDS and isinstance(value, int) and not isinstance(value, bool):
        return ("year", value)
    if isinstance(value, list):
        # Preserve author order and every value; do not sort, split names, or drop entries.
        return ("list", tuple(comparison_key(field, item) for item in value))
    if isinstance(value, dict):
        return ("dict", tuple(sorted((key, comparison_key(key, item)) for key, item in value.items())))
    return (type(value).__name__, value)


def validate(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root must be an object"]
    if not RECORD_ID.fullmatch(str(data.get("id", ""))):
        errors.append("id must match CITE-[0-9]{3,8}")
    if data.get("mode") not in MODES:
        errors.append(f"mode must be one of {sorted(MODES)}")
    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        errors.append(f"verdict must be one of {sorted(VERDICTS)}")
    identifiers = data.get("identifiers")
    if not isinstance(identifiers, list):
        errors.append("identifiers must be a list")
        identifiers = []
    for index, item in enumerate(identifiers):
        prefix = f"identifiers[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ("type", "original", "normalized", "status"):
            if field not in item:
                errors.append(f"{prefix}.{field} is required")
        kind, value = item.get("type"), item.get("normalized")
        if kind == "doi" and (not isinstance(value, str) or not DOI.fullmatch(value)):
            errors.append(f"{prefix}.normalized is not a valid bare DOI")
        if kind == "doi" and isinstance(value, str) and (
            value.startswith(("http://", "https://", "doi:")) or value != value.lower()
        ):
            errors.append(f"{prefix}.normalized DOI must be lowercase without wrapper")
        if kind == "pmid" and (not isinstance(value, str) or not value.isdigit()):
            errors.append(f"{prefix}.normalized PMID must contain digits only")
        if kind == "arxiv" and (not isinstance(value, str) or not ARXIV.fullmatch(value)):
            errors.append(f"{prefix}.normalized arXiv identifier is invalid")
    sources = data.get("sources")
    if not isinstance(sources, list):
        errors.append("sources must be a list")
        sources = []
    source_ids: set[str] = set()
    source_records: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"sources[{index}] must be an object")
            continue
        for field in ("id", "name", "query", "retrieved_at", "record_locator",
                      "response_state", "fields"):
            if field not in source:
                errors.append(f"sources[{index}].{field} is required")
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            errors.append(f"sources[{index}].id must be non-empty")
        elif source_id in source_ids:
            errors.append(f"sources[{index}].id duplicates {source_id}")
        source_ids.add(str(source_id))
        source_records[str(source_id)] = source
        if source.get("response_state") not in SOURCE_STATES:
            errors.append(f"sources[{index}].response_state is invalid")
        if not isinstance(source.get("fields"), dict):
            errors.append(f"sources[{index}].fields must be an object")
    canonical = data.get("canonical_fields")
    if not isinstance(canonical, dict):
        errors.append("canonical_fields must be an object")
        canonical = {}
    provenance = data.get("field_provenance")
    if not isinstance(provenance, list):
        errors.append("field_provenance must be a list")
        provenance = []
    field_names: set[str] = set()
    field_states: dict[str, str] = {}
    for index, item in enumerate(provenance):
        if not isinstance(item, dict):
            errors.append(f"field_provenance[{index}] must be an object")
            continue
        field = item.get("field")
        state = item.get("state")
        refs = item.get("source_ids")
        if not isinstance(field, str) or not field:
            errors.append(f"field_provenance[{index}].field must be non-empty")
        elif field in field_names:
            errors.append(f"field_provenance[{index}].field duplicates {field}")
        field_names.add(str(field))
        field_states[str(field)] = str(state)
        if state not in FIELD_STATES:
            errors.append(f"field_provenance[{index}].state must be valid")
        if not isinstance(refs, list):
            errors.append(f"field_provenance[{index}].source_ids must be a list")
        elif any(not isinstance(ref, str) or ref not in source_ids for ref in refs):
            errors.append(f"field_provenance[{index}] references unknown source")
        if state in {"verified", "single-source"}:
            linked = [source_records[ref] for ref in refs
                      if isinstance(ref, str) and ref in source_records] if isinstance(refs, list) else []
            if not linked:
                errors.append(f"field_provenance[{index}]: resolved field requires source evidence")
            resolved_values: list[Any] = []
            for source in linked:
                fields = source.get("fields")
                if (source.get("response_state") != "resolved"
                    or not isinstance(fields, dict) or not isinstance(field, str) or field not in fields
                    or not all(supplied(source.get(key)) for key in
                               ("name", "query", "retrieved_at", "record_locator"))):
                    errors.append(f"field_provenance[{index}]: source must have resolved this field with provenance")
                else:
                    resolved_values.append(fields[field])
            if isinstance(field, str) and field in canonical and not any(
                comparison_key(field, source_value) == comparison_key(field, canonical[field])
                for source_value in resolved_values
            ):
                errors.append(f"field_provenance[{index}]: canonical value lacks conservatively matching source evidence")
    for field in ("conflicts", "duplicate_groups", "version_links",
                  "retrieval_failures", "limitations", "unresolved", "handoff"):
        if not isinstance(data.get(field), list):
            errors.append(f"{field} must be a list")
    conflicts = data.get("conflicts", [])
    if verdict == "verified" and (conflicts or data.get("unresolved")):
        errors.append("verified verdict cannot contain conflicts or unresolved items")
    if verdict == "verified" and not sources:
        errors.append("verified verdict requires at least one source")
    if verdict == "verified":
        if not canonical:
            errors.append("verified verdict requires canonical fields")
        for field, value in canonical.items():
            if field_states.get(field) != "verified":
                errors.append(f"verified verdict requires verified provenance for canonical field: {field}")
            if value is None or value == [] or value == {} or (
                isinstance(value, str) and not supplied(value)
            ):
                errors.append(f"verified verdict requires a resolved canonical value: {field}")
        if any(state in {"missing", "conflict", "single-source"} for state in field_states.values()):
            errors.append("verified verdict cannot contain missing, conflict, or single-source field states")
        if data.get("retrieval_failures"):
            errors.append("verified verdict cannot contain unresolved retrieval failures")
    if verdict == "conflict" and not conflicts:
        errors.append("conflict verdict requires at least one conflict")
    if verdict == "unresolved" and not data.get("unresolved"):
        errors.append("unresolved verdict requires unresolved items")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.artifact.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2
    errors = validate(data)
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
