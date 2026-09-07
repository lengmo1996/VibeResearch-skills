#!/usr/bin/env python3
"""Validate a research-statistical-power JSON artifact without modifying it."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


ID_PATTERN = re.compile(r"^PWR-[0-9]{3,8}$")
MODES = {"closed-form", "simulation", "sensitivity", "audit", "full"}
TARGETS = {"sample-size", "power", "mde"}
SIDEDNESS = {"one-sided", "two-sided"}
VERDICTS = {"ready", "conditional", "blocked"}
UNRESOLVED = {"", "unknown", "unresolved", "tbd", "n/a"}
ASSUMPTION_STATUSES = {"resolved", "conditional", "unresolved"}


def _unknown(value: Any) -> bool:
    if isinstance(value, (list, dict)):
        return not value or any(_unknown(item) for item in (value.values() if isinstance(value, dict) else value))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return not math.isfinite(value)
    return value is None or (
        isinstance(value, str) and value.strip().lower() in UNRESOLVED
    )


def _number(
    errors: list[str],
    value: Any,
    path: str,
    *,
    lower: float,
    upper: float,
    upper_inclusive: bool = False,
    lower_inclusive: bool = True,
) -> None:
    if not _finite(value):
        errors.append(f"{path} must be finite and numeric")
        return
    valid_upper = value <= upper if upper_inclusive else value < upper
    valid_lower = value >= lower if lower_inclusive else value > lower
    if not valid_lower or not valid_upper:
        left_bracket = "[" if lower_inclusive else "("
        bracket = "]" if upper_inclusive else ")"
        errors.append(f"{path} must be in {left_bracket}{lower}, {upper}{bracket}")


def _finite(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _sample_size(errors: list[str], value: Any, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        errors.append(f"{path} must be an integer >= 2")


def validate(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root must be a JSON object"]

    if not ID_PATTERN.fullmatch(str(data.get("id", ""))):
        errors.append("id must match PWR-[0-9]{3,8}")
    mode = data.get("mode")
    if mode not in MODES:
        errors.append(f"mode must be one of {sorted(MODES)}")
    solve_for = data.get("solve_for")
    if solve_for not in TARGETS:
        errors.append(f"solve_for must be one of {sorted(TARGETS)}")
    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        errors.append(f"verdict must be one of {sorted(VERDICTS)}")

    design = data.get("design")
    if not isinstance(design, dict):
        errors.append("design must be an object")
        design = {}
    for field in ("estimand", "analysis_unit", "test_or_model"):
        if field not in design:
            errors.append(f"design.{field} is required")
    if design.get("sidedness") not in SIDEDNESS:
        errors.append(f"design.sidedness must be one of {sorted(SIDEDNESS)}")
    allocation = design.get("allocation_ratio")
    if (
        not _finite(allocation)
        or allocation <= 0
    ):
        errors.append("design.allocation_ratio must be numeric and greater than 0")

    calculation = data.get("calculation")
    if not isinstance(calculation, dict):
        errors.append("calculation must be an object")
        calculation = {}
    _number(errors, calculation.get("alpha"), "calculation.alpha", lower=0, upper=0.5, lower_inclusive=False)
    if solve_for in {"sample-size", "mde"}:
        _number(
            errors,
            calculation.get("target_power"),
            "calculation.target_power",
            lower=0,
            upper=1,
            lower_inclusive=False,
        )
    if solve_for == "power":
        _sample_size(errors, calculation.get("adjusted_total_n"), "calculation.adjusted_total_n")
    for field in (
        "effect_scale",
        "method",
        "implementation",
        "implementation_version",
        "rounding_policy",
    ):
        if field not in calculation:
            errors.append(f"calculation.{field} is required")

    assumptions = data.get("assumptions")
    if not isinstance(assumptions, list) or not assumptions:
        errors.append("assumptions must be a non-empty list")
        assumptions = []
    for index, item in enumerate(assumptions):
        if not isinstance(item, dict):
            errors.append(f"assumptions[{index}] must be an object")
            continue
        for field in (
            "parameter",
            "value_or_range",
            "units_or_scale",
            "source_type",
            "source_locator",
            "status",
        ):
            if field not in item:
                errors.append(f"assumptions[{index}].{field} is required")
        if item.get("status") not in ASSUMPTION_STATUSES:
            errors.append(f"assumptions[{index}].status must be resolved, conditional, or unresolved")

    adjustments = data.get("adjustments")
    if not isinstance(adjustments, dict):
        errors.append("adjustments must be an object")
        adjustments = {}
    attrition = adjustments.get("attrition_rate")
    if attrition is not None:
        _number(
            errors,
            attrition,
            "adjustments.attrition_rate",
            lower=0,
            upper=1,
        )
    icc = adjustments.get("intraclass_correlation")
    if icc is not None:
        _number(
            errors,
            icc,
            "adjustments.intraclass_correlation",
            lower=0,
            upper=1,
            upper_inclusive=True,
        )
        cluster_size = adjustments.get("mean_cluster_size")
        if (
            not _finite(cluster_size)
            or cluster_size <= 1
        ):
            errors.append(
                "adjustments.mean_cluster_size must be numeric and greater than 1 "
                "when intraclass_correlation is set"
            )

    simulation = data.get("simulation")
    if mode == "simulation" or simulation is not None:
        if not isinstance(simulation, dict):
            errors.append("simulation must be an object in simulation mode")
        else:
            for field in (
                "data_generating_model",
                "decision_rule",
                "failure_policy",
                "seed",
                "repetitions",
            ):
                if _unknown(simulation.get(field)):
                    errors.append(f"simulation.{field} must be resolved")
            repetitions = simulation.get("repetitions")
            if (
                not _unknown(repetitions)
                and (
                    isinstance(repetitions, bool)
                    or not isinstance(repetitions, int)
                    or repetitions < 1
                )
            ):
                errors.append("simulation.repetitions must be a positive integer")
            seed = simulation.get("seed")
            if not _unknown(seed) and (isinstance(seed, bool) or not isinstance(seed, int) or seed < 0):
                errors.append("simulation.seed must be a non-negative integer")

    sensitivity = data.get("sensitivity")
    if mode in {"sensitivity", "full"} and (
        not isinstance(sensitivity, list) or len(sensitivity) < 2
    ):
        errors.append("sensitivity/full mode requires at least two scenarios")

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
        if not _finite(calculation.get("effect_size")):
            errors.append("ready verdict requires a numeric calculation.effect_size")
        for field in ("effect_scale", "method", "implementation", "implementation_version", "rounding_policy"):
            if _unknown(calculation.get(field)):
                errors.append(f"ready verdict requires resolved calculation.{field}")
        for field in ("estimand", "analysis_unit", "test_or_model"):
            if _unknown(design.get(field)):
                errors.append(f"ready verdict requires resolved design.{field}")
        for index, item in enumerate(assumptions):
            if not isinstance(item, dict):
                continue
            if item.get("status") != "resolved":
                errors.append(f"ready verdict requires resolved assumptions[{index}].status")
            for field in ("parameter", "value_or_range", "units_or_scale", "source_type", "source_locator"):
                if _unknown(item.get(field)):
                    errors.append(f"ready verdict requires resolved assumptions[{index}].{field}")
        if _unknown(adjustments.get("multiplicity_policy")):
            errors.append("ready verdict requires resolved adjustments.multiplicity_policy")
        if solve_for == "sample-size":
            for field in ("unadjusted_total_n", "adjusted_total_n"):
                _sample_size(errors, calculation.get(field), f"calculation.{field}")
        elif solve_for == "power":
            _number(errors, calculation.get("achieved_power"), "calculation.achieved_power",
                    lower=0, upper=1, upper_inclusive=True)
        elif solve_for == "mde" and _finite(calculation.get("effect_size")):
            if calculation["effect_size"] <= 0:
                errors.append("ready mde requires a positive calculation.effect_size")
        if isinstance(sensitivity, list):
            for index, scenario in enumerate(sensitivity):
                if not isinstance(scenario, dict) or not _finite(scenario.get("result")):
                    errors.append(f"ready verdict requires numeric sensitivity[{index}].result")
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
