from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "global" / "research-statistical-power"
VALIDATOR_PATH = SKILL / "scripts" / "validate_power_plan.py"
TEMPLATE_PATH = SKILL / "templates" / "power-plan.json"

SPEC = importlib.util.spec_from_file_location("validate_power_plan", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class StatisticalPowerValidationTests(unittest.TestCase):
    def template(self) -> dict:
        return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    def ready_plan(self, solve_for: str = "sample-size") -> dict:
        data = self.template()
        data.update(mode="closed-form", verdict="ready", unresolved=[], sensitivity=[], solve_for=solve_for)
        data["design"].update(estimand="mean difference", analysis_unit="independent participant", test_or_model="two-sample t test")
        data["calculation"].update(
            effect_size=0.5, effect_scale="Cohen d", method="noncentral t",
            implementation="synthetic test fixture", implementation_version="1.0",
            unadjusted_total_n=128, adjusted_total_n=128, achieved_power=0.8,
        )
        data["assumptions"] = [{
            "parameter": "effect_size", "value_or_range": 0.5, "units_or_scale": "Cohen d",
            "source_type": "user-approved planning scenario", "source_locator": "synthetic test fixture",
            "status": "resolved",
        }]
        data["adjustments"]["multiplicity_policy"] = "one prespecified comparison"
        return data

    def test_blocked_template_is_structurally_valid(self) -> None:
        self.assertEqual(VALIDATOR.validate(self.template()), [])

    def test_ready_requires_resolved_effect_and_implementation(self) -> None:
        data = self.template()
        data["verdict"] = "ready"
        data["unresolved"] = []
        errors = VALIDATOR.validate(data)
        self.assertTrue(any("numeric calculation.effect_size" in error for error in errors))
        self.assertTrue(any("resolved calculation.method" in error for error in errors))

    def test_simulation_requires_reproducibility_fields(self) -> None:
        data = self.template()
        data["mode"] = "simulation"
        data["simulation"] = {}
        errors = VALIDATOR.validate(data)
        self.assertTrue(any("simulation.seed" in error for error in errors))
        self.assertTrue(any("simulation.repetitions" in error for error in errors))

    def test_ready_controls_for_each_calculation_target(self) -> None:
        for target in ("sample-size", "power", "mde"):
            with self.subTest(target=target):
                self.assertEqual(VALIDATOR.validate(self.ready_plan(target)), [])

    def test_ready_cannot_hide_unresolved_nested_assumptions(self) -> None:
        for field, value in (("status", "unresolved"), ("status", "conditional"),
                             ("source_locator", "unresolved"), ("value_or_range", [None, 0.5])):
            with self.subTest(field=field, value=value):
                data = self.ready_plan()
                data["assumptions"][0][field] = value
                self.assertTrue(VALIDATOR.validate(data))

    def test_ready_requires_requested_result_and_sensitivity_outputs(self) -> None:
        for target, field in (("sample-size", "unadjusted_total_n"),
                              ("sample-size", "adjusted_total_n"), ("power", "achieved_power")):
            with self.subTest(target=target, field=field):
                data = self.ready_plan(target)
                data["calculation"][field] = None
                self.assertTrue(VALIDATOR.validate(data))
        data = self.ready_plan()
        data["mode"] = "sensitivity"
        data["sensitivity"] = [{"scenario": "lower", "result": 200}, {"scenario": "upper", "result": 80}]
        self.assertEqual(VALIDATOR.validate(data), [])
        data["sensitivity"][1]["result"] = None
        self.assertTrue(VALIDATOR.validate(data))

    def test_probability_and_nonfinite_values_fail_closed(self) -> None:
        for field, value in (("alpha", 0), ("target_power", 0), ("alpha", float("nan")),
                             ("effect_size", float("inf"))):
            with self.subTest(field=field, value=value):
                data = self.ready_plan()
                data["calculation"][field] = value
                self.assertTrue(VALIDATOR.validate(data))
        data = self.ready_plan()
        data["design"]["allocation_ratio"] = float("nan")
        self.assertTrue(VALIDATOR.validate(data))

    def test_conditional_assumption_remains_valid_without_ready_verdict(self) -> None:
        data = self.ready_plan()
        data["verdict"] = "conditional"
        data["assumptions"][0]["status"] = "conditional"
        data["unresolved"] = ["confirm pilot applicability"]
        self.assertEqual(VALIDATOR.validate(data), [])

    def test_cli_does_not_modify_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "plan.json"
            artifact.write_text(
                json.dumps(self.template(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            before = artifact.read_bytes()
            result = subprocess.run(
                [sys.executable, "-B", str(VALIDATOR_PATH), str(artifact)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(artifact.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
