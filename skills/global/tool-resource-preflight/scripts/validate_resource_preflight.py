#!/usr/bin/env python3
"""Validate a resource-preflight report without probing the environment."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


REPORT_ID = re.compile(r"^PREFLIGHT-[0-9]{3,8}$")
REQ_ID = re.compile(r"^REQ-[0-9]{3,8}$")
EVIDENCE_ID = re.compile(r"^RES-[0-9]{3,8}$")
EVIDENCE_CLASSES = {"observed", "declared", "estimated", "unknown"}
SCOPES = {"host", "process", "container", "scheduler", "runtime", "budget"}
MATCH_STATES = {"met", "unmet", "unknown", "conditional"}
VERDICTS = {"go", "conditional", "no-go", "not-evaluable"}
PLACEHOLDERS = {"", "unresolved", "unknown", "not provided", "not-provided", "not-checked",
                "unclear", "not provided / unclear", "tbd", "todo"}


def supplied(value: Any) -> bool:
    return value is not None and (
        not isinstance(value, str) or value.strip().casefold() not in PLACEHOLDERS
    )


def validate(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root must be an object"]
    if not REPORT_ID.fullmatch(str(data.get("id", ""))):
        errors.append("id must match PREFLIGHT-[0-9]{3,8}")
    requirements = data.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        errors.append("requirements must be a non-empty list")
        requirements = []
    requirement_ids: set[str] = set()
    requirement_records: dict[str, dict[str, Any]] = {}
    hard: dict[str, bool] = {}
    for index, req in enumerate(requirements):
        if not isinstance(req, dict):
            errors.append(f"requirements[{index}] must be an object")
            continue
        req_id = str(req.get("id", ""))
        if not REQ_ID.fullmatch(req_id):
            errors.append(f"requirements[{index}].id must match REQ-[0-9]{{3,8}}")
        elif req_id in requirement_ids:
            errors.append(f"requirements[{index}].id duplicates {req_id}")
        requirement_ids.add(req_id)
        requirement_records[req_id] = req
        hard[req_id] = req.get("hard") is True
        if not isinstance(req.get("hard"), bool):
            errors.append(f"requirements[{index}].hard must be boolean")
        for field in ("resource", "minimum", "unit", "hard", "source"):
            if field not in req:
                errors.append(f"requirements[{index}].{field} is required")
    observations = data.get("observations")
    if not isinstance(observations, list):
        errors.append("observations must be a list")
        observations = []
    evidence_ids: set[str] = set()
    evidence_records: dict[str, dict[str, Any]] = {}
    for index, obs in enumerate(observations):
        if not isinstance(obs, dict):
            errors.append(f"observations[{index}] must be an object")
            continue
        evidence_id = str(obs.get("id", ""))
        if not EVIDENCE_ID.fullmatch(evidence_id):
            errors.append(f"observations[{index}].id must match RES-[0-9]{{3,8}}")
        elif evidence_id in evidence_ids:
            errors.append(f"observations[{index}].id duplicates {evidence_id}")
        evidence_ids.add(evidence_id)
        evidence_records[evidence_id] = obs
        if obs.get("evidence_class") not in EVIDENCE_CLASSES:
            errors.append(f"observations[{index}].evidence_class is invalid")
        if obs.get("scope") not in SCOPES:
            errors.append(f"observations[{index}].scope is invalid")
        for field in ("resource", "value", "unit", "source", "observed_at",
                      "status"):
            if field not in obs:
                errors.append(f"observations[{index}].{field} is required")
    matches = data.get("matches")
    if not isinstance(matches, list):
        errors.append("matches must be a list")
        matches = []
    match_state: dict[str, str] = {}
    for index, match in enumerate(matches):
        if not isinstance(match, dict):
            errors.append(f"matches[{index}] must be an object")
            continue
        req_id = match.get("requirement_id")
        if not isinstance(req_id, str) or req_id not in requirement_ids:
            errors.append(f"matches[{index}] references unknown requirement")
        if isinstance(req_id, str) and req_id in match_state:
            errors.append(f"matches[{index}] duplicates requirement {req_id}")
        state = match.get("status")
        if state not in MATCH_STATES:
            errors.append(f"matches[{index}].status is invalid")
        match_state[str(req_id)] = str(state)
        refs = match.get("evidence_ids")
        if not isinstance(refs, list):
            errors.append(f"matches[{index}].evidence_ids must be a list")
        elif any(not isinstance(ref, str) or ref not in evidence_ids for ref in refs):
            errors.append(f"matches[{index}] references unknown evidence")
        if state in {"met", "unmet"}:
            req = requirement_records.get(str(req_id), {})
            if not all(supplied(req.get(field)) for field in ("resource", "minimum", "unit", "source")):
                errors.append(f"matches[{index}]: {state} requires a resolved requirement")
            linked = [evidence_records[ref] for ref in refs
                      if isinstance(ref, str) and ref in evidence_records] if isinstance(refs, list) else []
            acceptance = match.get("assumption_acceptance")
            accepted_assumption = isinstance(acceptance, dict) and acceptance.get("accepted") is True and (
                isinstance(acceptance.get("evidence"), str) and supplied(acceptance["evidence"])
            )
            supporting = [obs for obs in linked if (
                obs.get("resource") == req.get("resource")
                and obs.get("unit") == req.get("unit")
                and (not hard.get(str(req_id)) or obs.get("scope") != "host")
                and obs.get("status") == "success"
                and all(supplied(obs.get(field)) for field in ("value", "source", "observed_at"))
                and (obs.get("evidence_class") == "observed" or (
                    accepted_assumption and obs.get("evidence_class") in {"declared", "estimated"}
                ))
            )]
            if not supporting:
                errors.append(f"matches[{index}]: {state} requires successful, compatible effective-scope evidence")
            minimum = req.get("minimum")
            values = [obs.get("value") for obs in supporting]
            if isinstance(minimum, bool):
                if not values or any(not isinstance(value, bool) for value in values):
                    errors.append(f"matches[{index}]: boolean requirement needs boolean observations")
                elif (state == "met") != all(value is minimum for value in values):
                    errors.append(f"matches[{index}]: evidence contradicts the declared boolean match")
            elif isinstance(minimum, (int, float)):
                if not math.isfinite(minimum) or not values or any(
                    not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
                    for value in values
                ):
                    errors.append(f"matches[{index}]: numeric comparison requires finite values")
                elif (state == "met") != (min(values) >= minimum):
                    errors.append(f"matches[{index}]: evidence contradicts the declared numeric match")
            elif isinstance(minimum, str):
                if not values or any(not isinstance(value, str) for value in values):
                    errors.append(f"matches[{index}]: textual requirement needs textual observations; numeric strings are not coerced")
                assessment = match.get("evaluation")
                evidence_refs = assessment.get("evidence_ids") if isinstance(assessment, dict) else None
                supporting_ids = {obs["id"] for obs in supporting}
                if not isinstance(assessment, dict) or assessment.get("status") != state or not all(
                    isinstance(assessment.get(field), str) and supplied(assessment[field])
                    for field in ("method", "rationale")
                ) or not isinstance(evidence_refs, list) or not evidence_refs or any(
                    not isinstance(ref, str) or ref not in supporting_ids for ref in evidence_refs
                ):
                    errors.append(f"matches[{index}]: non-numeric comparison requires an explicit evidence-linked evaluation")
            else:
                errors.append(f"matches[{index}]: requirement minimum must be a number, boolean, or explicit textual condition")
    missing_matches = requirement_ids - set(match_state)
    if missing_matches:
        errors.append(f"requirements lack matches: {sorted(missing_matches)}")
    privacy = data.get("privacy")
    if not isinstance(privacy, dict):
        errors.append("privacy must be an object")
    elif any(privacy.get(key) is True for key in (
        "host_identifiers_exposed", "absolute_paths_exposed",
        "environment_values_exposed", "credentials_exposed"
    )):
        errors.append("preflight report exposes prohibited environment identifiers")
    for field in ("bottlenecks", "fallbacks", "warnings", "unresolved", "handoff"):
        if not isinstance(data.get(field), list):
            errors.append(f"{field} must be a list")
    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        errors.append(f"verdict must be one of {sorted(VERDICTS)}")
    hard_states = {match_state.get(req_id, "unknown") for req_id, is_hard in hard.items() if is_hard}
    if verdict == "go" and hard_states != {"met"}:
        errors.append("go verdict requires every hard requirement to be met")
    if verdict == "go" and data.get("unresolved"):
        errors.append("go verdict cannot contain unresolved checks")
    if verdict == "no-go" and "unmet" not in hard_states:
        errors.append("no-go verdict requires an unmet hard requirement")
    if verdict == "not-evaluable" and "unknown" not in hard_states:
        errors.append("not-evaluable verdict requires an unknown hard requirement")
    if verdict == "conditional":
        if hard_states & {"unknown", "unmet"}:
            errors.append("conditional verdict cannot hide an unknown or unmet hard requirement")
        if "conditional" in hard_states and not data.get("fallbacks"):
            errors.append("conditional hard matches require a named fallback")
        if "conditional" not in hard_states and not data.get("unresolved"):
            errors.append("conditional verdict requires conditional hard matches or unresolved soft checks")
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
