from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "global" / "tool-resource-preflight"
VALIDATOR_PATH = SKILL / "scripts" / "validate_resource_preflight.py"
TEMPLATE_PATH = SKILL / "templates" / "resource-preflight.json"
SPEC = importlib.util.spec_from_file_location("preflight_validator", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ResourcePreflightTests(unittest.TestCase):
    def template(self) -> dict:
        return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    def test_template_is_valid(self) -> None:
        self.assertEqual(VALIDATOR.validate(self.template()), [])

    def test_go_requires_hard_requirements_met(self) -> None:
        data = self.template()
        data["verdict"] = "go"
        self.assertTrue(any("every hard requirement" in e for e in VALIDATOR.validate(data)))

    def test_exposed_environment_identifiers_are_rejected(self) -> None:
        data = self.template()
        data["privacy"]["absolute_paths_exposed"] = True
        self.assertTrue(any("prohibited" in e for e in VALIDATOR.validate(data)))

    def completed(self) -> dict:
        data = self.template()
        data["requirements"][0].update(resource="memory", minimum=8, unit="GiB", source="workload manifest")
        data["observations"] = [{
            "id": "RES-001", "resource": "memory", "value": 12, "unit": "GiB",
            "source": "bounded process-limit probe", "observed_at": "2026-09-06T00:00:00Z",
            "status": "success", "evidence_class": "observed", "scope": "process",
        }]
        data["matches"][0].update(status="met", evidence_ids=["RES-001"])
        data.update(unresolved=[], warnings=[], verdict="go")
        return data

    def test_go_with_effective_observed_evidence_is_valid(self) -> None:
        self.assertEqual(VALIDATOR.validate(self.completed()), [])

    def test_original_empty_evidence_go_counterexample_is_rejected(self) -> None:
        data = self.template()
        data["matches"][0]["status"] = "met"
        data["verdict"] = "go"
        errors = VALIDATOR.validate(data)
        self.assertTrue(any("effective-scope evidence" in error for error in errors))
        self.assertTrue(any("unresolved checks" in error for error in errors))

    def test_met_requires_compatible_successful_evidence(self) -> None:
        for field, value in (("scope", "host"), ("unit", "MiB"), ("resource", "disk"),
                             ("status", "timeout"), ("evidence_class", "unknown"),
                             ("source", "unresolved"), ("observed_at", "unknown"),
                             ("value", None), ("value", 4), ("value", float("nan"))):
            with self.subTest(field=field, value=value):
                data = self.completed()
                data["observations"][0][field] = value
                self.assertTrue(VALIDATOR.validate(data))

    def test_estimate_requires_recorded_user_acceptance(self) -> None:
        data = self.completed()
        data["observations"][0]["evidence_class"] = "estimated"
        self.assertTrue(VALIDATOR.validate(data))
        data["matches"][0]["assumption_acceptance"] = {
            "accepted": True, "evidence": "User accepted this bounded estimate for the task",
        }
        self.assertEqual(VALIDATOR.validate(data), [])

    def test_conditional_does_not_hide_unknown_or_unmet_hard_requirement(self) -> None:
        for state in ("unknown", "unmet"):
            with self.subTest(state=state):
                data = self.template()
                data["matches"][0]["status"] = state
                data.update(verdict="conditional", fallbacks=["smaller workload"])
                self.assertTrue(VALIDATOR.validate(data))

    def test_bounded_conditional_and_no_go_reports_remain_valid(self) -> None:
        data = self.completed()
        data["matches"][0]["status"] = "conditional"
        data.update(verdict="conditional", fallbacks=["Named smaller workload"])
        self.assertEqual(VALIDATOR.validate(data), [])
        data = self.completed()
        data.update(verdict="conditional", unresolved=["soft disk-headroom preference"])
        self.assertEqual(VALIDATOR.validate(data), [])
        data = self.completed()
        data["matches"][0]["status"] = "unmet"
        data["observations"][0]["value"] = 4
        data["verdict"] = "no-go"
        self.assertEqual(VALIDATOR.validate(data), [])

    def test_hard_flag_and_reference_types_cannot_bypass_checks(self) -> None:
        data = self.completed()
        data["requirements"][0]["hard"] = "true"
        self.assertTrue(VALIDATOR.validate(data))
        data = self.completed()
        data["matches"][0]["evidence_ids"] = [{}]
        self.assertTrue(VALIDATOR.validate(data))

    def test_numeric_string_and_boolean_counterexamples_are_rejected(self) -> None:
        for minimum, observed in (("8", 4), (True, False), (8, "12"), (8, True), ({"minimum": 8}, 12)):
            with self.subTest(minimum=minimum, observed=observed):
                data = self.completed()
                data["requirements"][0]["minimum"] = minimum
                data["observations"][0]["value"] = observed
                self.assertTrue(VALIDATOR.validate(data))

    def test_boolean_requirements_use_boolean_equality(self) -> None:
        for required, observed, state in ((True, True, "met"), (False, False, "met"), (True, False, "unmet")):
            with self.subTest(required=required, observed=observed):
                data = self.completed()
                data["requirements"][0].update(resource="permission", minimum=required, unit="boolean")
                data["observations"][0].update(resource="permission", value=observed, unit="boolean")
                data["matches"][0]["status"] = state
                data["verdict"] = "go" if state == "met" else "no-go"
                self.assertEqual(VALIDATOR.validate(data), [])

    def test_textual_compatibility_needs_explicit_evidence_linked_evaluation(self) -> None:
        data = self.completed()
        data["requirements"][0].update(resource="runtime", minimum="Python >= 3.11", unit="version")
        data["observations"][0].update(resource="runtime", value="Python 3.12", unit="version")
        self.assertTrue(any("explicit evidence-linked evaluation" in error for error in VALIDATOR.validate(data)))
        data["matches"][0]["evaluation"] = {
            "status": "met", "method": "compare major/minor runtime version",
            "rationale": "Observed major/minor 3.12 satisfies the declared 3.11 minimum",
            "evidence_ids": ["RES-001"],
        }
        self.assertEqual(VALIDATOR.validate(data), [])
        for field, value in (("status", "unmet"), ("method", "unresolved"),
                             ("rationale", "unknown"), ("evidence_ids", ["RES-999"])):
            with self.subTest(field=field):
                candidate = json.loads(json.dumps(data))
                candidate["matches"][0]["evaluation"][field] = value
                self.assertTrue(VALIDATOR.validate(candidate))

    def test_cli_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preflight.json"
            path.write_text(json.dumps(self.template()), encoding="utf-8")
            before = path.read_bytes()
            result = subprocess.run(
                [sys.executable, "-B", str(VALIDATOR_PATH), str(path)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
