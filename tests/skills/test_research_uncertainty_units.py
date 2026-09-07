from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "global" / "research-uncertainty-units"
VALIDATOR_PATH = SKILL / "scripts" / "validate_uncertainty_budget.py"
TEMPLATE_PATH = SKILL / "templates" / "uncertainty-budget.json"

SPEC = importlib.util.spec_from_file_location("validate_uncertainty_budget", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class UncertaintyUnitsValidationTests(unittest.TestCase):
    def template(self) -> dict:
        return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    def ready_budget(self) -> dict:
        data = self.template()
        data.update(verdict="ready", unresolved=[])
        data["measurand"].update(name="length", value=1, unit="m", measurement_model="y=x")
        data["inputs"][0].update(
            estimate=1, unit="m", stated_uncertainty=0.01, standard_uncertainty=0.01,
            uncertainty_unit="m", evaluation_type="B", distribution="normal", divisor=1,
            sensitivity_coefficient=1, source="synthetic fixture", status="resolved",
        )
        data["correlation_policy"] = {"status": "independent", "source": "single-input synthetic model"}
        data["unit_audit"] = [{"expression": "y=x", "expected_dimension": "length",
                               "observed_dimension": "length", "status": "pass"}]
        data["propagation"].update(method="gum-linear", implementation="synthetic fixture",
                                   implementation_version="1.0", linearization_check="exact linear model")
        data["result"].update(estimate=1, unit="m", combined_standard_uncertainty=0.01,
                              rounding_rule="two significant figures", reporting_statement="standard uncertainty")
        return data

    def test_blocked_template_is_valid(self) -> None:
        self.assertEqual(VALIDATOR.validate(self.template()), [])

    def test_duplicate_symbols_and_bad_correlation_are_rejected(self) -> None:
        data = self.template()
        duplicate = dict(data["inputs"][0])
        data["inputs"].append(duplicate)
        data["correlations"] = [
            {"left": "x", "right": "missing", "coefficient": 2, "source": "unresolved"}
        ]
        errors = VALIDATOR.validate(data)
        self.assertTrue(any("duplicates x" in error for error in errors))
        self.assertTrue(any("two distinct input symbols" in error for error in errors))
        self.assertTrue(any("in [-1, 1]" in error for error in errors))

    def test_monte_carlo_requires_seed_and_repetitions(self) -> None:
        data = self.template()
        data["propagation"]["method"] = "monte-carlo"
        errors = VALIDATOR.validate(data)
        self.assertTrue(any("integer seed" in error for error in errors))
        self.assertTrue(any("positive integer repetitions" in error for error in errors))

    def test_resolved_linear_and_correlated_budgets_are_valid(self) -> None:
        data = self.ready_budget()
        self.assertEqual(VALIDATOR.validate(data), [])
        second = dict(data["inputs"][0], symbol="z")
        data["inputs"].append(second)
        data["measurand"]["measurement_model"] = "y=x+z"
        data["unit_audit"][0]["expression"] = "y=x+z"
        data["correlation_policy"] = {"status": "specified", "source": "synthetic paired model"}
        data["correlations"] = [{"left": "x", "right": "z", "coefficient": 0.2, "source": "synthetic covariance"}]
        self.assertEqual(VALIDATOR.validate(data), [])

    def test_ready_rejects_failed_or_unresolved_unit_audit(self) -> None:
        for status in ("fail", "unknown", "unresolved"):
            with self.subTest(status=status):
                data = self.ready_budget()
                data["unit_audit"][0]["status"] = status
                self.assertTrue(VALIDATOR.validate(data))
        data = self.ready_budget()
        data["unit_audit"] = []
        self.assertTrue(VALIDATOR.validate(data))

    def test_ready_requires_explicit_correlation_assumption_and_input_status(self) -> None:
        for mutation in ("missing-policy", "unresolved-policy", "unresolved-input", "failed-linearization"):
            with self.subTest(mutation=mutation):
                data = self.ready_budget()
                if mutation == "missing-policy":
                    del data["correlation_policy"]
                elif mutation == "unresolved-policy":
                    data["correlation_policy"]["status"] = "unresolved"
                elif mutation == "unresolved-input":
                    data["inputs"][0]["status"] = "unresolved"
                else:
                    data["propagation"]["linearization_check"] = "fail"
                self.assertTrue(VALIDATOR.validate(data))

    def test_conditional_failure_and_legacy_draft_remain_valid(self) -> None:
        data = self.ready_budget()
        data["verdict"] = "conditional"
        data["unit_audit"][0]["status"] = "fail"
        data["unresolved"] = ["unit mismatch"]
        self.assertEqual(VALIDATOR.validate(data), [])
        legacy = self.template()
        del legacy["correlation_policy"]
        self.assertEqual(VALIDATOR.validate(legacy), [])

    def test_cli_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "budget.json"
            artifact.write_text(json.dumps(self.template()), encoding="utf-8")
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
