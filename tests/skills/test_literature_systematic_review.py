"""Behavioral checks for screening completion and quantitative-study binding."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "global" / "literature-systematic-review"
SPEC = importlib.util.spec_from_file_location(
    "systematic_review_validator", SKILL / "scripts" / "validate_systematic_review.py"
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def sample() -> dict:
    return json.loads((SKILL / "templates" / "systematic-review-ledger.json").read_text(encoding="utf-8"))


def quantitative_sample() -> dict:
    data = sample()
    data["studies"][1].update(full_text_decision="include", exclusion_reason=None)
    for study in data["studies"]:
        study["effect_data_status"] = "available"
    data["flow"].update(excluded_full_text=0, included_qualitative=2, included_quantitative=2)
    data["meta_analysis_gate"].update(
        status="eligible", compatible=True,
        effect_definition="Mean difference in the protocol outcome",
        heterogeneity_plan="Assess design differences and run prespecified sensitivity analysis",
        quantitative_study_ids=["STUDY-001", "STUDY-002"],
    )
    return data


class LiteratureSystematicReviewTests(unittest.TestCase):
    def test_complete_qualitative_template_and_zero_count_legacy_form_pass(self) -> None:
        data = sample()
        self.assertEqual(VALIDATOR.validate(data), [])
        data["meta_analysis_gate"].pop("quantitative_study_ids", None)
        self.assertEqual(VALIDATOR.validate(data), [])

    def test_pending_full_text_is_valid_partial_but_cannot_be_complete(self) -> None:
        data = sample()
        data["studies"][1].update(full_text_decision="not-assessed", exclusion_reason=None)
        data["flow"].update(full_text_assessed=1, excluded_full_text=0)
        self.assertTrue(any("complete coverage" in error for error in VALIDATOR.validate(data)))
        data["coverage_status"] = "partial"
        self.assertEqual(VALIDATOR.validate(data), [])

    def test_title_exclusion_does_not_require_full_text_assessment(self) -> None:
        data = sample()
        data["studies"][1].update(title_abstract_decision="exclude", full_text_decision="not-assessed")
        data["flow"].update(full_text_assessed=1, excluded_full_text=0)
        self.assertEqual(VALIDATOR.validate(data), [])

    def test_full_text_decision_requires_title_abstract_inclusion(self) -> None:
        data = sample()
        data["studies"][0]["title_abstract_decision"] = "exclude"
        self.assertTrue(any("title/abstract inclusion" in error for error in VALIDATOR.validate(data)))

    def test_protocol_only_with_no_executed_work_remains_valid(self) -> None:
        data = sample()
        data.update(coverage_status="protocol-only", studies=[], search_batches=[])
        data["flow"] = dict.fromkeys(data["flow"], 0)
        self.assertEqual(VALIDATOR.validate(data), [])

    def test_bound_compatible_quantitative_studies_pass(self) -> None:
        self.assertEqual(VALIDATOR.validate(quantitative_sample()), [])

    def test_quantitative_inclusion_rejects_unavailable_effects(self) -> None:
        for status in ("incompatible", "incomplete", "not-requested"):
            with self.subTest(status=status):
                data = quantitative_sample()
                data["studies"][0]["effect_data_status"] = status
                self.assertTrue(any("available effect data" in error for error in VALIDATOR.validate(data)))

    def test_positive_quantitative_count_requires_explicit_study_binding(self) -> None:
        data = quantitative_sample()
        del data["meta_analysis_gate"]["quantitative_study_ids"]
        self.assertTrue(any("quantitative_study_ids" in error for error in VALIDATOR.validate(data)))

    def test_quantitative_binding_rejects_duplicate_unknown_and_count_mismatch(self) -> None:
        for ids in (["STUDY-001", "STUDY-001"], ["STUDY-001", "STUDY-999"], ["STUDY-001"]):
            with self.subTest(ids=ids):
                data = quantitative_sample()
                data["meta_analysis_gate"]["quantitative_study_ids"] = ids
                self.assertTrue(VALIDATOR.validate(data))

    def test_qualitative_only_incompatible_study_does_not_block_compatible_subset(self) -> None:
        data = quantitative_sample()
        qualitative = copy.deepcopy(data["studies"][0])
        qualitative.update(study_id="STUDY-003", source_ref="paper-c.pdf", effect_data_status="incompatible")
        data["studies"].append(qualitative)
        data["search_batches"][0]["records_found"] = 3
        data["flow"].update(identified=3, title_abstract_screened=3, full_text_assessed=3, included_qualitative=3)
        self.assertEqual(VALIDATOR.validate(data), [])


if __name__ == "__main__":
    unittest.main()
