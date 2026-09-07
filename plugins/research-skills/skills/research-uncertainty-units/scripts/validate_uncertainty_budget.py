#!/usr/bin/env python3
"""Validate an uncertainty-and-units JSON artifact without modifying it."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


ID_PATTERN = re.compile(r"^UNC-[0-9]{3,8}$")
MODES = {"unit-audit", "budget", "propagation", "reporting", "plausibility", "full"}
VERDICTS = {"ready", "conditional", "blocked"}
EVALUATION_TYPES = {"A", "B"}
PROPAGATION_METHODS = {"gum-linear", "monte-carlo", "hybrid", "not-applicable"}
UNKNOWN = {"", "unknown", "unresolved", "tbd", "n/a"}


def _unknown(value: Any) -> bool:
    return value is None or (
        isinstance(value, str) and value.strip().lower() in UNKNOWN
    )


def _finite(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def validate(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root must be a JSON object"]
    if not ID_PATTERN.fullmatch(str(data.get("id", ""))):
        errors.append("id must match UNC-[0-9]{3,8}")
    mode = data.get("mode")
    if mode not in MODES:
        errors.append(f"mode must be one of {sorted(MODES)}")
    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        errors.append(f"verdict must be one of {sorted(VERDICTS)}")

    measurand = data.get("measurand")
    if not isinstance(measurand, dict):
        errors.append("measurand must be an object")
        measurand = {}
    for field in ("name", "value", "unit", "measurement_model"):
        if field not in measurand:
            errors.append(f"measurand.{field} is required")

    inputs = data.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        errors.append("inputs must be a non-empty list")
        inputs = []
    symbols: set[str] = set()
    for index, item in enumerate(inputs):
        prefix = f"inputs[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            errors.append(f"{prefix}.symbol must be non-empty")
        elif symbol in symbols:
            errors.append(f"{prefix}.symbol duplicates {symbol}")
        else:
            symbols.add(symbol)
        for field in (
            "estimate",
            "unit",
            "stated_uncertainty",
            "uncertainty_unit",
            "evaluation_type",
            "distribution",
            "divisor",
            "standard_uncertainty",
            "degrees_of_freedom",
            "sensitivity_coefficient",
            "source",
            "status",
        ):
            if field not in item:
                errors.append(f"{prefix}.{field} is required")
        evaluation_type = item.get("evaluation_type")
        if not _unknown(evaluation_type) and evaluation_type not in EVALUATION_TYPES:
            errors.append(f"{prefix}.evaluation_type must be A, B, or unresolved")
        for field in ("stated_uncertainty", "standard_uncertainty"):
            value = item.get(field)
            if value is not None and (not _finite(value) or value < 0):
                errors.append(f"{prefix}.{field} must be finite and non-negative")
        divisor = item.get("divisor")
        if divisor is not None and (not _finite(divisor) or divisor <= 0):
            errors.append(f"{prefix}.divisor must be finite and greater than 0")
        dof = item.get("degrees_of_freedom")
        if dof is not None and (not _finite(dof) or dof <= 0):
            errors.append(
                f"{prefix}.degrees_of_freedom must be finite and greater than 0"
            )

    correlations = data.get("correlations")
    if not isinstance(correlations, list):
        errors.append("correlations must be a list")
        correlations = []
    seen_pairs: set[tuple[str, str]] = set()
    for index, item in enumerate(correlations):
        prefix = f"correlations[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        left, right = item.get("left"), item.get("right")
        if left not in symbols or right not in symbols or left == right:
            errors.append(f"{prefix} must reference two distinct input symbols")
        pair = tuple(sorted((str(left), str(right))))
        if pair in seen_pairs:
            errors.append(f"{prefix} duplicates correlation pair {pair}")
        seen_pairs.add(pair)
        coefficient = item.get("coefficient")
        if not _finite(coefficient) or not -1 <= coefficient <= 1:
            errors.append(f"{prefix}.coefficient must be finite and in [-1, 1]")
        if _unknown(item.get("source")):
            errors.append(f"{prefix}.source must be resolved")

    unit_audit = data.get("unit_audit")
    if not isinstance(unit_audit, list):
        errors.append("unit_audit must be a list")
        unit_audit = []
    for index, item in enumerate(unit_audit):
        if not isinstance(item, dict):
            errors.append(f"unit_audit[{index}] must be an object")
        elif item.get("status") not in {"pass", "fail", "unknown", "unresolved", "not-applicable"}:
            errors.append(f"unit_audit[{index}].status is invalid")

    correlation_policy = data.get("correlation_policy")
    if correlation_policy is not None and not isinstance(correlation_policy, dict):
        errors.append("correlation_policy must be an object")
    elif isinstance(correlation_policy, dict):
        policy_status = correlation_policy.get("status")
        if policy_status not in {"independent", "specified", "unresolved"}:
            errors.append("correlation_policy.status must be independent, specified, or unresolved")
        if policy_status == "independent" and correlations:
            errors.append("independent correlation_policy cannot contain correlation pairs")

    propagation = data.get("propagation")
    if not isinstance(propagation, dict):
        errors.append("propagation must be an object")
        propagation = {}
    for field in ("method", "implementation", "implementation_version", "linearization_check"):
        if field not in propagation:
            errors.append(f"propagation.{field} is required")
    method = propagation.get("method")
    if not _unknown(method) and method not in PROPAGATION_METHODS:
        errors.append(f"propagation.method must be one of {sorted(PROPAGATION_METHODS)}")
    if method in {"monte-carlo", "hybrid"}:
        seed = propagation.get("seed")
        repetitions = propagation.get("repetitions")
        if isinstance(seed, bool) or not isinstance(seed, int):
            errors.append("Monte Carlo propagation requires an integer seed")
        if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
            errors.append("Monte Carlo propagation requires positive integer repetitions")

    result = data.get("result")
    if not isinstance(result, dict):
        errors.append("result must be an object")
        result = {}
    for field in (
        "estimate",
        "unit",
        "combined_standard_uncertainty",
        "coverage_factor",
        "coverage_probability",
        "expanded_uncertainty",
        "rounding_rule",
        "reporting_statement",
    ):
        if field not in result:
            errors.append(f"result.{field} is required")
    coverage = result.get("coverage_probability")
    if coverage is not None and (not _finite(coverage) or not 0 < coverage < 1):
        errors.append("result.coverage_probability must be strictly between 0 and 1")
    factor = result.get("coverage_factor")
    if factor is not None and (not _finite(factor) or factor <= 0):
        errors.append("result.coverage_factor must be finite and greater than 0")
    for field in ("combined_standard_uncertainty", "expanded_uncertainty"):
        value = result.get(field)
        if value is not None and (not _finite(value) or value < 0):
            errors.append(f"result.{field} must be finite and non-negative")

    unresolved = data.get("unresolved")
    if not isinstance(unresolved, list):
        errors.append("unresolved must be a list")
        unresolved = []
    for field in ("limitations", "handoff"):
        if not isinstance(data.get(field), list):
            errors.append(f"{field} must be a list")

    if verdict == "ready":
        if unresolved:
            errors.append("ready verdict cannot contain unresolved items")
        for field in ("name", "value", "unit", "measurement_model"):
            if _unknown(measurand.get(field)):
                errors.append(f"ready verdict requires resolved measurand.{field}")
        if not _finite(measurand.get("value")):
            errors.append("ready verdict requires a finite measurand.value")
        if not unit_audit:
            errors.append("ready verdict requires a non-empty unit_audit")
        for index, item in enumerate(unit_audit):
            if not isinstance(item, dict):
                continue
            if item.get("status") == "not-applicable":
                if _unknown(item.get("reason")):
                    errors.append(f"unit_audit[{index}] requires a reason for not-applicable")
            elif item.get("status") != "pass":
                errors.append(f"ready verdict requires a passing unit_audit[{index}]")
            else:
                for field in ("expression", "expected_dimension", "observed_dimension"):
                    if _unknown(item.get(field)):
                        errors.append(f"ready verdict requires resolved unit_audit[{index}].{field}")
        if not isinstance(correlation_policy, dict) or correlation_policy.get("status") not in {"independent", "specified"}:
            errors.append("ready verdict requires an explicit resolved correlation_policy")
        elif _unknown(correlation_policy.get("source")):
            errors.append("ready verdict requires resolved correlation_policy.source")
        elif correlation_policy["status"] == "specified" and not correlations:
            errors.append("specified correlation_policy requires correlation pairs")
        for index, item in enumerate(inputs):
            if not isinstance(item, dict):
                continue
            if item.get("status") != "resolved":
                errors.append(f"ready verdict requires resolved inputs[{index}].status")
            for field in ("estimate", "sensitivity_coefficient"):
                if not _finite(item.get(field)):
                    errors.append(f"ready verdict requires finite inputs[{index}].{field}")
            for field in (
                "estimate",
                "unit",
                "standard_uncertainty",
                "uncertainty_unit",
                "evaluation_type",
                "distribution",
                "divisor",
                "sensitivity_coefficient",
                "source",
            ):
                if _unknown(item.get(field)):
                    errors.append(f"ready verdict requires resolved inputs[{index}].{field}")
        for field in ("method", "implementation", "implementation_version"):
            if _unknown(propagation.get(field)):
                errors.append(f"ready verdict requires resolved propagation.{field}")
        if method in {"gum-linear", "hybrid"} and (
            _unknown(propagation.get("linearization_check"))
            or str(propagation.get("linearization_check")).strip().lower() in {"fail", "failed"}
        ):
            errors.append("ready verdict requires a resolved non-failing propagation.linearization_check")
        for field in (
            "estimate",
            "unit",
            "combined_standard_uncertainty",
            "rounding_rule",
            "reporting_statement",
        ):
            if _unknown(result.get(field)):
                errors.append(f"ready verdict requires resolved result.{field}")
        if not _finite(result.get("estimate")):
            errors.append("ready verdict requires a finite result.estimate")
    if verdict == "blocked" and not unresolved:
        errors.append("blocked verdict requires at least one unresolved item")
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
