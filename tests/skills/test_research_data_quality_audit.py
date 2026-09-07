from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "global" / "research-data-quality-audit"
VALIDATOR_PATH = SKILL / "scripts" / "validate_data_quality_report.py"
TEMPLATE_PATH = SKILL / "templates" / "data-quality-report.json"
SPEC = importlib.util.spec_from_file_location("dq_validator", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class DataQualityAuditTests(unittest.TestCase):
    def template(self) -> dict:
        return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    def fit_report(self) -> dict:
        data = self.template()
        data.update(stated_use="schema suitability of the inspected sample", authorization="synthetic fixture scope",
                    observational_unit="record", unresolved=[])
        data["assets"] = [{"asset_id": "sample", "version": "fixture-1", "format": "csv", "source_locator": "redacted"}]
        data["coverage"].update(method="declared first partition", rows_or_records_scanned=10,
                                total_rows_or_records=100, fields_scanned=3)
        data["rule_registry"] = [{"rule_id": "schema", "critical": True, "status": "pass",
                                  "scope": "the 10 inspected records", "evidence": ["aggregate://schema-check"]}]
        data["fitness"].update(verdict="fit", scope_limit="only the inspected sample's schema")
        return data

    def test_template_is_valid(self) -> None:
        self.assertEqual(VALIDATOR.validate(self.template()), [])

    def test_sampled_scan_cannot_claim_complete(self) -> None:
        data = self.template()
        data["coverage"].update({"complete": True, "truncated": True})
        self.assertTrue(any("complete coverage" in e for e in VALIDATOR.validate(data)))

    def test_privacy_and_blocker_references_fail_closed(self) -> None:
        data = self.template()
        data["privacy"]["raw_rows_exposed"] = True
        data["fitness"]["blocking_finding_ids"] = ["DQ-999"]
        errors = VALIDATOR.validate(data)
        self.assertTrue(any("raw rows" in e for e in errors))
        self.assertTrue(any("does not reference" in e for e in errors))

    def test_empty_draft_cannot_be_promoted_by_clearing_unresolved(self) -> None:
        data = self.template()
        data["fitness"]["verdict"] = "fit"
        data["unresolved"] = []
        errors = VALIDATOR.validate(data)
        self.assertTrue(any("stated_use" in error for error in errors))
        self.assertTrue(any("critical rules" in error for error in errors))
        self.assertTrue(any("inspected records or fields" in error for error in errors))

    def test_bounded_fit_and_schema_only_fit_do_not_require_full_scan(self) -> None:
        data = self.fit_report()
        self.assertEqual(VALIDATOR.validate(data), [])
        data["stated_use"] = "header schema only"
        data["coverage"]["rows_or_records_scanned"] = 0
        data["rule_registry"][0]["scope"] = "three inspected header fields"
        data["fitness"]["scope_limit"] = "header schema only; no record fitness conclusion"
        self.assertEqual(VALIDATOR.validate(data), [])

    def test_fit_requires_critical_coverage_and_resolved_scope(self) -> None:
        for mutation in ("failed-rule", "unknown-rule", "missing-evidence", "missing-scope", "missing-authorization"):
            with self.subTest(mutation=mutation):
                data = self.fit_report()
                if mutation == "failed-rule":
                    data["rule_registry"][0]["status"] = "fail"
                elif mutation == "unknown-rule":
                    data["rule_registry"][0]["status"] = "unknown"
                elif mutation == "missing-evidence":
                    data["rule_registry"][0]["evidence"] = []
                elif mutation == "missing-scope":
                    data["fitness"]["scope_limit"] = "unresolved"
                else:
                    data["authorization"] = "unresolved"
                self.assertTrue(VALIDATOR.validate(data))

    def test_omitted_blocker_cannot_hide_critical_finding(self) -> None:
        data = self.fit_report()
        data["findings"] = [{
            "id": "DQ-001", "rule_id": "schema", "severity": "high", "evidence": "aggregate://violation",
            "denominator": 10, "affected_scope": "sample", "confidence": "high", "impact": "invalid schema",
            "remediation": "separate task", "verification": "repeat schema check",
        }]
        self.assertTrue(any("critical rule" in error for error in VALIDATOR.validate(data)))

    def test_cli_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
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
