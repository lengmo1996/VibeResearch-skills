#!/usr/bin/env python3
"""Validate a systematic-review ledger without modifying it."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


TOP_FIELDS = {
    "schema_version",
    "review_id",
    "coverage_status",
    "protocol",
    "search_batches",
    "flow",
    "studies",
    "meta_analysis_gate",
    "unresolved",
}
PROTOCOL_FIELDS = {
    "question",
    "eligibility",
    "declared_sources",
    "date_range",
    "deduplication_key",
    "screening_process",
    "outcomes",
    "amendments",
}
FLOW_FIELDS = {
    "identified",
    "duplicates_removed",
    "title_abstract_screened",
    "full_text_assessed",
    "excluded_full_text",
    "included_qualitative",
    "included_quantitative",
}
DECISIONS = {"include", "exclude", "unclear", "not-assessed"}
BIAS_STATUSES = {"low", "some-concerns", "high", "unclear", "not-assessed"}
EFFECT_STATUSES = {"available", "incomplete", "incompatible", "not-requested"}
COVERAGE_STATUSES = {"protocol-only", "partial", "complete"}
META_STATUSES = {"eligible", "not-eligible", "not-requested", "pending"}
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["ledger root must be an object"]
    if set(data) != TOP_FIELDS:
        errors.append("ledger fields must match the version 1.0.0 contract")
    if data.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    if not re.fullmatch(r"SR-\d{3,}", str(data.get("review_id", ""))):
        errors.append("review_id must match SR-###")
    coverage = data.get("coverage_status")
    if coverage not in COVERAGE_STATUSES:
        errors.append("coverage_status is invalid")

    protocol = data.get("protocol")
    if not isinstance(protocol, dict):
        errors.append("protocol must be an object")
        protocol = {}
    elif set(protocol) != PROTOCOL_FIELDS:
        errors.append("protocol fields do not match the contract")
    for field in ("question", "eligibility", "date_range", "deduplication_key", "screening_process"):
        if not _nonempty(protocol.get(field)):
            errors.append(f"protocol.{field} is required")
    declared_sources = protocol.get("declared_sources")
    if not isinstance(declared_sources, list) or not declared_sources or not all(
        _nonempty(value) for value in declared_sources
    ):
        errors.append("protocol.declared_sources must be a non-empty string array")
        declared_sources = []
    outcomes = protocol.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        errors.append("protocol.outcomes must be a non-empty array")
    if not isinstance(protocol.get("amendments"), list):
        errors.append("protocol.amendments must be an array")

    batches = data.get("search_batches")
    if not isinstance(batches, list):
        errors.append("search_batches must be an array")
        batches = []
    batch_ids: set[str] = set()
    batch_sources: set[str] = set()
    incomplete_batches = 0
    identified_from_batches = 0
    for index, batch in enumerate(batches):
        label = f"search_batches[{index}]"
        if not isinstance(batch, dict):
            errors.append(f"{label} must be an object")
            continue
        batch_id = batch.get("batch_id")
        if not re.fullmatch(r"SEARCH-\d{3,}", str(batch_id or "")):
            errors.append(f"{label}.batch_id must match SEARCH-###")
        elif batch_id in batch_ids:
            errors.append(f"{label}.batch_id is duplicated")
        else:
            batch_ids.add(batch_id)
        source = batch.get("source")
        if not _nonempty(source):
            errors.append(f"{label}.source is required")
        else:
            batch_sources.add(source)
        if not HEX_SHA256.fullmatch(str(batch.get("query_sha256", ""))):
            errors.append(f"{label}.query_sha256 is invalid")
        records = batch.get("records_found")
        if not isinstance(records, int) or isinstance(records, bool) or records < 0:
            errors.append(f"{label}.records_found must be a non-negative integer")
        else:
            identified_from_batches += records
        if not isinstance(batch.get("complete"), bool):
            errors.append(f"{label}.complete must be boolean")
        elif not batch["complete"]:
            incomplete_batches += 1
        if not _nonempty(batch.get("executed_at")) or not _nonempty(batch.get("evidence_ref")):
            errors.append(f"{label} requires executed_at and evidence_ref")

    flow = data.get("flow")
    if not isinstance(flow, dict):
        errors.append("flow must be an object")
        flow = {}
    elif set(flow) != FLOW_FIELDS:
        errors.append("flow fields do not match the contract")
    for field in FLOW_FIELDS:
        value = flow.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"flow.{field} must be a non-negative integer")

    studies = data.get("studies")
    if not isinstance(studies, list):
        errors.append("studies must be an array")
        studies = []
    study_ids: set[str] = set()
    studies_by_id: dict[str, dict[str, Any]] = {}
    included = excluded_full = 0
    unresolved_decisions = 0
    for index, study in enumerate(studies):
        label = f"studies[{index}]"
        if not isinstance(study, dict):
            errors.append(f"{label} must be an object")
            continue
        study_id = study.get("study_id")
        if not re.fullmatch(r"STUDY-\d{3,}", str(study_id or "")):
            errors.append(f"{label}.study_id must match STUDY-###")
        elif study_id in study_ids:
            errors.append(f"{label}.study_id is duplicated")
        else:
            study_ids.add(study_id)
            studies_by_id[study_id] = study
        if not _nonempty(study.get("source_ref")):
            errors.append(f"{label}.source_ref is required")
        title_decision = study.get("title_abstract_decision")
        full_decision = study.get("full_text_decision")
        if title_decision not in DECISIONS:
            errors.append(f"{label}.title_abstract_decision is invalid")
        if full_decision not in DECISIONS:
            errors.append(f"{label}.full_text_decision is invalid")
        if full_decision in {"include", "exclude", "unclear"} and title_decision != "include":
            errors.append(f"{label}: full-text assessment requires title/abstract inclusion")
        if full_decision == "exclude":
            excluded_full += 1
            if not _nonempty(study.get("exclusion_reason")):
                errors.append(f"{label}: full-text exclusion requires a reason")
        elif full_decision == "include":
            included += 1
        if (
            title_decision in {"unclear", "not-assessed"}
            or full_decision == "unclear"
            or (title_decision == "include" and full_decision == "not-assessed")
        ):
            unresolved_decisions += 1
        if study.get("risk_of_bias_status") not in BIAS_STATUSES:
            errors.append(f"{label}.risk_of_bias_status is invalid")
        if study.get("effect_data_status") not in EFFECT_STATUSES:
            errors.append(f"{label}.effect_data_status is invalid")

    unresolved = data.get("unresolved")
    if not isinstance(unresolved, list):
        errors.append("unresolved must be an array")
        unresolved = []

    if all(
        isinstance(flow.get(field), int) and not isinstance(flow.get(field), bool)
        for field in FLOW_FIELDS
    ):
        if flow["identified"] != identified_from_batches and coverage != "protocol-only":
            errors.append("flow.identified must equal summed search batch records")
        deduplicated = flow["identified"] - flow["duplicates_removed"]
        if flow["title_abstract_screened"] != deduplicated:
            errors.append("title_abstract_screened must equal identified minus duplicates")
        if flow["full_text_assessed"] > flow["title_abstract_screened"]:
            errors.append("full_text_assessed exceeds title_abstract_screened")
        if flow["excluded_full_text"] + flow["included_qualitative"] != flow["full_text_assessed"]:
            errors.append("full-text exclusions plus qualitative includes must reconcile")
        if flow["included_quantitative"] > flow["included_qualitative"]:
            errors.append("quantitative includes exceed qualitative includes")
        if len(studies) != flow["title_abstract_screened"]:
            errors.append("study ledger count must equal title_abstract_screened")
        if excluded_full != flow["excluded_full_text"]:
            errors.append("excluded study decisions do not match flow")
        if included != flow["included_qualitative"]:
            errors.append("included study decisions do not match flow")

    meta = data.get("meta_analysis_gate")
    if not isinstance(meta, dict):
        errors.append("meta_analysis_gate must be an object")
        meta = {}
    status = meta.get("status")
    if status not in META_STATUSES:
        errors.append("meta_analysis_gate.status is invalid")
    quantitative_count = flow.get("included_quantitative")
    valid_quantitative_count = (
        isinstance(quantitative_count, int)
        and not isinstance(quantitative_count, bool)
        and quantitative_count >= 0
    )
    quantitative_ids = meta.get("quantitative_study_ids", [])
    if not isinstance(quantitative_ids, list) or not all(
        isinstance(study_id, str) and re.fullmatch(r"STUDY-\d{3,}", study_id)
        for study_id in quantitative_ids
    ):
        errors.append("meta_analysis_gate.quantitative_study_ids must be an array of STUDY-### IDs")
        quantitative_ids = []
    if len(set(quantitative_ids)) != len(quantitative_ids):
        errors.append("meta_analysis_gate.quantitative_study_ids must be unique")
    if valid_quantitative_count and len(quantitative_ids) != quantitative_count:
        errors.append("quantitative_study_ids must explicitly account for included_quantitative")
    for study_id in quantitative_ids:
        study = studies_by_id.get(study_id)
        if study is None:
            errors.append(f"quantitative_study_ids references unknown study: {study_id}")
        elif (
            study.get("title_abstract_decision") != "include"
            or study.get("full_text_decision") != "include"
            or study.get("effect_data_status") != "available"
        ):
            errors.append(f"{study_id}: quantitative inclusion requires full-text inclusion and available effect data")
    if status == "eligible":
        if meta.get("compatible") is not True:
            errors.append("eligible meta-analysis requires compatible: true")
        if not _nonempty(meta.get("effect_definition")):
            errors.append("eligible meta-analysis requires an effect definition")
        if not _nonempty(meta.get("heterogeneity_plan")):
            errors.append("eligible meta-analysis requires a heterogeneity plan")
        if not valid_quantitative_count or quantitative_count < 2:
            errors.append("eligible meta-analysis requires at least two quantitative studies")

    if coverage == "protocol-only" and (batches or studies or any(flow.get(field, 0) for field in FLOW_FIELDS)):
        errors.append("protocol-only coverage cannot claim executed batches or flow")
    if coverage == "complete":
        if incomplete_batches or unresolved or unresolved_decisions:
            errors.append("complete coverage requires complete batches and no unresolved decisions")
        missing_sources = set(declared_sources) - batch_sources
        if missing_sources:
            errors.append(
                "complete coverage is missing declared sources: "
                + ", ".join(sorted(missing_sources))
            )
    return errors


def run_self_test() -> int:
    template = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "systematic-review-ledger.json"
    )
    data = json.loads(template.read_text(encoding="utf-8"))
    invalid = json.loads(json.dumps(data))
    invalid["flow"]["included_qualitative"] = 2
    if validate(data) or not validate(invalid):
        print("Self-test failed.", file=sys.stderr)
        return 1
    print("Self-test passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    if args.ledger is None:
        parser.error("provide a ledger path or use --self-test")
    try:
        data = json.loads(args.ledger.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"unable to read ledger: {exc}", file=sys.stderr)
        return 2
    errors = validate(data)
    if errors:
        print(f"Systematic review validation failed ({len(errors)} issue(s)):")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Systematic review ledger is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
