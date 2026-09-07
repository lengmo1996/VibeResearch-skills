from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "global" / "tool-zotero-pdf-ingestion"
VALIDATOR_PATH = SKILL / "scripts" / "validate_reconciliation_manifest.py"
TEMPLATE_PATH = SKILL / "templates" / "reconciliation-record.example.json"
SPEC = importlib.util.spec_from_file_location("reconciliation_validator", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ZoteroPDFIngestionTests(unittest.TestCase):
    def template(self) -> dict:
        return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    def approved(self) -> dict:
        data = self.template()
        data["kb_ready"] = True
        data["match_decision"].update(review_required=False, approval={
            "status": "approved", "actor": "fixture-user", "approved_at": "2026-09-06T00:00:00Z",
            "evidence": "Synthetic entry-specific approval fixture",
        })
        return data

    def test_template_is_valid_and_not_approved(self) -> None:
        data = self.template()
        self.assertEqual(VALIDATOR.validate_records([data]), [])
        self.assertFalse(data["kb_ready"])

    def test_approved_exact_and_manually_resolved_records_are_valid(self) -> None:
        data = self.approved()
        self.assertEqual(VALIDATOR.validate_records([data]), [])
        data["match_decision"].update(method="manual-review", previous_method="title-similarity")
        self.assertEqual(VALIDATOR.validate_records([data]), [])

    def test_original_fuzzy_conflict_kb_ready_counterexample_is_rejected(self) -> None:
        data = self.approved()
        data["match_decision"].update(method="title-similarity", review_required=True)
        data["conflicts"] = ["unresolved identity conflict"]
        errors = VALIDATOR.validate_records([data])
        self.assertTrue(any("review" in error for error in errors))
        self.assertTrue(any("conflicts" in error for error in errors))

    def test_kb_ready_requires_complete_approval_provenance(self) -> None:
        for field in ("status", "actor", "approved_at", "evidence"):
            with self.subTest(field=field):
                data = self.approved()
                data["match_decision"]["approval"].pop(field)
                self.assertTrue(VALIDATOR.validate_records([data]))
        data = self.template()
        data["kb_ready"] = True
        self.assertTrue(VALIDATOR.validate_records([data]))

    def test_placeholder_approval_counterexample_is_rejected(self) -> None:
        data = self.approved()
        for field in ("actor", "approved_at", "evidence"):
            data["match_decision"]["approval"][field] = "unresolved"
        self.assertTrue(VALIDATOR.validate_records([data]))
        for field in ("actor", "approved_at", "evidence"):
            for placeholder in (" UnReSoLvEd ", "unknown", "not provided / unclear", "TBD", "<actual approval reference>"):
                with self.subTest(field=field, placeholder=placeholder):
                    data = self.approved()
                    data["match_decision"]["approval"][field] = placeholder
                    self.assertTrue(VALIDATOR.validate_records([data]))

    def test_kb_ready_rejects_missing_pdf_unresolved_status_and_remaining_conflict(self) -> None:
        for status in ("missing_pdf", "candidate_match", "conflict", "needs_review", "duplicate_group"):
            with self.subTest(status=status):
                data = self.approved()
                data["status"] = status
                if status == "missing_pdf":
                    data.update(pdf_path=None, pdf_sha256=None)
                self.assertTrue(VALIDATOR.validate_records([data]))
        data = self.approved()
        data["conflicts"] = ["unresolved conflict"]
        self.assertTrue(VALIDATOR.validate_records([data]))

    def test_review_queue_and_explicitly_approved_loose_pdf_remain_valid(self) -> None:
        data = self.template()
        data["status"] = "candidate_match"
        data["match_decision"].update(method="title-similarity", review_required=True)
        self.assertEqual(VALIDATOR.validate_records([data]), [])
        data = self.approved()
        data.update(status="loose_pdf", zotero_key=None)
        self.assertEqual(VALIDATOR.validate_records([data]), [])
        data = self.template()
        data.update(status="missing_pdf", pdf_path=None, pdf_sha256=None)
        self.assertEqual(VALIDATOR.validate_records([data]), [])

    def test_cli_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reconciliation.jsonl"
            path.write_text(json.dumps(self.template()) + "\n", encoding="utf-8")
            before = path.read_bytes()
            result = subprocess.run(
                [sys.executable, "-B", str(VALIDATOR_PATH), str(path)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
