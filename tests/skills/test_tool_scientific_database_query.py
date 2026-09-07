from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "global" / "tool-scientific-database-query"
VALIDATOR_PATH = SKILL / "scripts" / "validate_query_ledger.py"
TEMPLATE_PATH = SKILL / "templates" / "query-ledger.json"
SPEC = importlib.util.spec_from_file_location("query_validator", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ScientificDatabaseQueryTests(unittest.TestCase):
    def template(self) -> dict:
        return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    def test_template_is_valid(self) -> None:
        self.assertEqual(VALIDATOR.validate(self.template()), [])

    def test_secret_keys_are_rejected(self) -> None:
        data = self.template()
        data["plan"]["parameters_redacted"]["api_key"] = "secret"
        self.assertTrue(any("secret-bearing" in e for e in VALIDATOR.validate(data)))

    def test_exhaustive_complete_requires_count_reconciliation(self) -> None:
        data = self.template()
        data.update({"scope": "exhaustive", "verdict": "complete", "unresolved": []})
        data["next_state"] = "done"
        self.assertTrue(any("expected count" in e for e in VALIDATOR.validate(data)))

    def completed(self, count: int = 2) -> dict:
        data = self.template()
        data.update(mode="exhaustive", scope="exhaustive", verdict="complete", unresolved=[],
                    coverage_limits=["Named source and exact query only"], next_state="done")
        data["contract"].update(target="supplied identifier lookup", fields=["id"], deduplication_key="id")
        data["source"].update(database="fixture-db", api_version_or_date="2026-09-06",
                              documentation_locator="fixture-api-documentation", authentication_mode="anonymous")
        data["plan"].update(endpoint="fixture-api/search", pagination="offset", stable_sort="id asc",
                            request_budget=1, record_budget=count)
        data["pages"] = [{"request_id": "REQUEST-001", "position": 0, "requested": count,
                          "returned": count, "cumulative": count, "status": "success", "next_state": "done"}]
        data["counts"] = dict(expected=count, server_retrieved=count, local_filtered=count,
                              deduplicated=count, final=count)
        return data

    def test_complete_execution_and_explicit_zero_result_are_valid(self) -> None:
        for count in (0, 2):
            with self.subTest(count=count):
                self.assertEqual(VALIDATOR.validate(self.completed(count)), [])

    def test_original_pageless_exhaustive_counterexample_is_rejected(self) -> None:
        data = self.completed(10)
        data["pages"] = []
        errors = VALIDATOR.validate(data)
        self.assertTrue(any("page records" in error for error in errors))
        self.assertTrue(any("page cumulative" in error for error in errors))
        data = self.completed(0)
        data["pages"] = []
        self.assertTrue(VALIDATOR.validate(data), "zero results still require an executed response")

    def test_complete_requires_resolved_contract_and_source(self) -> None:
        for section, field in (("contract", "target"), ("contract", "deduplication_key"),
                               ("source", "database"), ("source", "api_version_or_date"),
                               ("source", "documentation_locator"), ("source", "authentication_mode"),
                               ("plan", "endpoint"), ("plan", "pagination"), ("plan", "stable_sort")):
            with self.subTest(section=section, field=field):
                data = self.completed()
                data[section][field] = "unresolved"
                self.assertTrue(VALIDATOR.validate(data))

    def test_complete_rejects_failed_or_unfinished_pages(self) -> None:
        for field, value in (("status", "timeout"), ("next_state", "next-cursor"), ("requested", 1)):
            with self.subTest(field=field):
                data = self.completed()
                data["pages"][0][field] = value
                self.assertTrue(VALIDATOR.validate(data))
        data = self.completed()
        data.update(mode="targeted", scope="targeted")
        data["pages"][0]["status"] = "timeout"
        self.assertTrue(VALIDATOR.validate(data))

    def test_duplicate_requests_and_budget_overruns_are_rejected(self) -> None:
        for field, value in (("request_budget", 0), ("record_budget", 1)):
            with self.subTest(field=field):
                data = self.completed()
                data["plan"][field] = value
                self.assertTrue(VALIDATOR.validate(data))
        data = self.completed(0)
        data["pages"] *= 2
        data["plan"]["request_budget"] = 2
        self.assertTrue(any("unique" in error for error in VALIDATOR.validate(data)))

    def test_partial_and_blocked_execution_remain_valid(self) -> None:
        data = self.completed()
        data.update(verdict="partial", unresolved=["next page"], next_state="cursor-2")
        data["pages"][0]["next_state"] = "cursor-2"
        self.assertEqual(VALIDATOR.validate(data), [])
        data = self.template()
        data.update(verdict="blocked", failures=["access-denied"])
        self.assertEqual(VALIDATOR.validate(data), [])

    def two_page_offset_query(self) -> dict:
        data = self.completed(4)
        data["plan"]["request_budget"] = 2
        data["pages"] = [
            {"request_id": "REQUEST-001", "position": 0, "requested": 2, "returned": 2,
             "cumulative": 2, "status": "success", "next_state": 2},
            {"request_id": "REQUEST-002", "position": 2, "requested": 2, "returned": 2,
             "cumulative": 4, "status": "success", "next_state": "done"},
        ]
        return data

    def test_contiguous_offset_execution_is_valid(self) -> None:
        self.assertEqual(VALIDATOR.validate(self.two_page_offset_query()), [])

    def test_duplicate_offset_counterexample_is_rejected(self) -> None:
        data = self.two_page_offset_query()
        data["pages"][1]["position"] = 0
        errors = VALIDATOR.validate(data)
        self.assertTrue(any("preceding next_state" in error for error in errors))
        self.assertTrue(any("contiguous offset" in error for error in errors))

    def test_offset_gaps_wrong_next_state_and_invalid_positions_are_rejected(self) -> None:
        for position in (3, -1, "2", True):
            with self.subTest(position=position):
                data = self.two_page_offset_query()
                data["pages"][0]["next_state"] = position
                data["pages"][1]["position"] = position
                self.assertTrue(VALIDATOR.validate(data))
        data = self.two_page_offset_query()
        data["pages"][0]["next_state"] = "done"
        self.assertTrue(VALIDATOR.validate(data))

    def test_cursor_pages_follow_the_returned_next_state(self) -> None:
        data = self.two_page_offset_query()
        data["plan"]["pagination"] = "cursor"
        data["pages"][0].update(position=None, next_state="cursor-2")
        data["pages"][1]["position"] = "cursor-2"
        self.assertEqual(VALIDATOR.validate(data), [])
        data["pages"][1]["position"] = "cursor-3"
        self.assertTrue(VALIDATOR.validate(data))

    def test_cli_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "query.json"
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
