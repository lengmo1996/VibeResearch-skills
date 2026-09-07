from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "global" / "tool-citation-metadata-validation"
VALIDATOR_PATH = SKILL / "scripts" / "validate_citation_record.py"
TEMPLATE_PATH = SKILL / "templates" / "citation-validation-record.json"
SPEC = importlib.util.spec_from_file_location("citation_validator", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class CitationMetadataValidationTests(unittest.TestCase):
    def template(self) -> dict:
        return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    def test_template_is_valid(self) -> None:
        self.assertEqual(VALIDATOR.validate(self.template()), [])

    def test_doi_must_be_bare_and_normalized(self) -> None:
        data = self.template()
        data["identifiers"] = [{
            "type": "doi", "original": "https://doi.org/10.1/X",
            "normalized": "https://doi.org/10.1/X", "status": "invalid"
        }]
        self.assertTrue(any("bare DOI" in e for e in VALIDATOR.validate(data)))

    def test_verified_requires_sources_and_no_unresolved(self) -> None:
        data = self.template()
        data["verdict"] = "verified"
        errors = VALIDATOR.validate(data)
        self.assertTrue(any("conflicts or unresolved" in e for e in errors))
        self.assertTrue(any("requires at least one source" in e for e in errors))

    def completed(self) -> dict:
        data = self.template()
        data.update(verdict="verified", unresolved=[], limitations=[])
        data["canonical_fields"] = {"title": "Fixture article"}
        data["sources"] = [{
            "id": "SOURCE-001", "name": "fixture authoritative source", "query": "supplied ID",
            "retrieved_at": "2026-09-06T00:00:00Z", "record_locator": "fixture-record-001",
            "response_state": "resolved", "fields": {"title": "Fixture article"},
        }]
        data["field_provenance"] = [{"field": "title", "state": "verified", "source_ids": ["SOURCE-001"]}]
        return data

    def test_verified_record_with_resolved_field_provenance_is_valid(self) -> None:
        self.assertEqual(VALIDATOR.validate(self.completed()), [])

    def field_record(self, field: str, canonical: object, source: object) -> dict:
        data = self.completed()
        data["canonical_fields"] = {field: canonical}
        data["sources"][0]["fields"] = {field: source}
        data["field_provenance"][0]["field"] = field
        return data

    def test_unrelated_canonical_title_is_rejected(self) -> None:
        data = self.field_record("title", "Unrelated Paper B", "Paper A")
        self.assertTrue(any("canonical value" in error for error in VALIDATOR.validate(data)))

    def test_conservative_normalization_preserves_valid_variants(self) -> None:
        for field, canonical, source in (
            ("title", "A Study of Café", "  A  STUDY\nof Cafe\u0301  "),
            ("doi", "10.1234/paper.a", "https://doi.org/10.1234/PAPER.A"),
            ("doi", "10.1234/paper.a", "DOI: 10.1234/PAPER.A"),
            ("year", 2026, "2026"),
            ("authors", ["Alice Smith", "Bob Lee"], [" Alice  Smith ", "BOB LEE"]),
            ("authors", [{"family": "Smith", "given": "Alice"}], [{"given": "ALICE", "family": "SMITH"}]),
        ):
            with self.subTest(field=field, source=source):
                self.assertEqual(VALIDATOR.validate(self.field_record(field, canonical, source)), [])

    def test_comparison_never_fuzzy_matches_or_discards_identity_differences(self) -> None:
        for field, canonical, source in (
            ("title", "Ablation Study", "Ablation-Study"),
            ("doi", "10.1234/paper.a", "https://doi.org/10.1234/paper.b"),
            ("authors", ["Alice Smith", "Bob Lee"], ["Bob Lee", "Alice Smith"]),
            ("authors", ["Alice Smith"], ["Alice Smith", "Bob Lee"]),
            ("url", "https://example.invalid/PaperA", "https://example.invalid/papera"),
            ("year", 2026, 2025),
            ("volume", 1, True),
        ):
            with self.subTest(field=field, source=source):
                self.assertTrue(VALIDATOR.validate(self.field_record(field, canonical, source)))

    def test_only_linked_resolved_source_values_can_support_canonical(self) -> None:
        data = self.field_record("title", "Paper B", "Paper A")
        data["sources"].append({**data["sources"][0], "id": "SOURCE-002", "fields": {"title": "Paper B"}})
        self.assertTrue(VALIDATOR.validate(data), "an unlinked source cannot fill the provenance gap")
        data["field_provenance"][0]["source_ids"].append("SOURCE-002")
        self.assertEqual(VALIDATOR.validate(data), [])
        data["sources"][1]["response_state"] = "timeout"
        self.assertTrue(VALIDATOR.validate(data))

    def test_original_timeout_missing_field_counterexample_is_rejected(self) -> None:
        data = self.completed()
        data["sources"][0].update(response_state="timeout", fields={})
        data["field_provenance"][0].update(state="missing", source_ids=[])
        self.assertTrue(VALIDATOR.validate(data))

    def test_verified_requires_every_canonical_field_to_be_supported(self) -> None:
        for change in ("no-provenance", "no-refs", "unknown-ref", "source-missing-field",
                       "source-timeout", "single-source", "missing", "conflict", "unresolved-value"):
            with self.subTest(change=change):
                data = self.completed()
                if change == "no-provenance":
                    data["field_provenance"] = []
                elif change == "no-refs":
                    data["field_provenance"][0]["source_ids"] = []
                elif change == "unknown-ref":
                    data["field_provenance"][0]["source_ids"] = ["SOURCE-999"]
                elif change == "source-missing-field":
                    data["sources"][0]["fields"] = {"year": 2026}
                elif change == "source-timeout":
                    data["sources"][0]["response_state"] = "timeout"
                elif change == "unresolved-value":
                    data["canonical_fields"]["title"] = "unresolved"
                else:
                    data["field_provenance"][0]["state"] = change
                self.assertTrue(VALIDATOR.validate(data))

    def test_single_source_partial_and_conflict_records_remain_valid(self) -> None:
        data = self.completed()
        data["field_provenance"][0]["state"] = "single-source"
        data["verdict"] = "partial"
        self.assertEqual(VALIDATOR.validate(data), [])
        data = self.completed()
        data["field_provenance"][0]["state"] = "conflict"
        data.update(verdict="conflict", conflicts=["title variants require review"])
        self.assertEqual(VALIDATOR.validate(data), [])

    def test_verified_rejects_empty_canonical_record_and_pending_failures(self) -> None:
        data = self.completed()
        data["canonical_fields"] = {}
        self.assertTrue(VALIDATOR.validate(data))
        data = self.completed()
        data["retrieval_failures"] = ["unresolved timeout"]
        self.assertTrue(VALIDATOR.validate(data))

    def test_cli_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "citation.json"
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
