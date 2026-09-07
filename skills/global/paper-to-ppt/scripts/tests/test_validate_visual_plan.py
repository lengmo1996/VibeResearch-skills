#!/usr/bin/env python3
"""Unit tests for paper-to-ppt visual-plan validation."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import recommend_visual_system as recommender
import validate_visual_plan as validator


def valid_brief() -> dict:
    chart_fields = [
        "metric-name",
        "units",
        "baseline-identity",
        "direct-takeaway",
    ]
    return {
        "deck_type": "defense",
        "audience": "thesis committee",
        "language": "bilingual",
        "aspect_ratio": "16:9",
        "domain": "artificial-intelligence",
        "slides": [
            {
                "id": "result",
                "role": "main-results",
                "claim": "The proposed model improves the primary benchmark",
                "content_types": ["chart", "comparison"],
                "density": "medium",
                "evidence_type": "comparison",
                "chart_fields": chart_fields,
                "alt_text": "Dot plot comparing the proposed model with three baselines.",
                "source_trace": "Verified experiment table 1",
            }
        ],
    }


class ValidateVisualPlanTests(unittest.TestCase):
    def test_generated_complete_plan_passes(self) -> None:
        result = validator.validate_plan(recommender.build_plan(valid_brief()))
        self.assertTrue(result["valid"], result["errors"])

    def test_low_contrast_and_small_type_fail(self) -> None:
        plan = recommender.build_plan(valid_brief())
        plan["visual_system"]["palette"]["text"] = "#777777"
        plan["visual_system"]["palette"]["background"] = "#888888"
        plan["visual_system"]["type_sizes_pt"]["body"] = 14
        result = validator.validate_plan(plan)
        self.assertFalse(result["valid"])
        self.assertTrue(any("contrast" in item for item in result["errors"]))
        self.assertTrue(any("Body size" in item for item in result["errors"]))

    def test_alt_text_and_color_only_fail(self) -> None:
        plan = recommender.build_plan(valid_brief())
        plan["slides"][0]["accessibility"]["alt_text"] = ""
        plan["slides"][0]["accessibility"]["color_not_only"] = False
        result = validator.validate_plan(plan)
        self.assertFalse(result["valid"])
        self.assertTrue(any("alt text" in item for item in result["errors"]))
        self.assertTrue(any("color_not_only" in item for item in result["errors"]))

    def test_chart_fields_and_source_are_required(self) -> None:
        plan = recommender.build_plan(valid_brief())
        plan["slides"][0]["chart"]["fields_present"] = []
        plan["slides"][0]["chart"]["source_trace"] = ""
        result = validator.validate_plan(plan)
        self.assertFalse(result["valid"])
        self.assertTrue(any("chart fields missing" in item for item in result["errors"]))
        self.assertTrue(any("chart requires a source trace" in item for item in result["errors"]))

    def test_motion_requires_static_and_reduced_motion_fallbacks(self) -> None:
        plan = recommender.build_plan(valid_brief())
        plan["slides"][0]["motion"] = {
            "type": "fade",
            "purpose": "compare states",
            "static_fallback": False,
            "reduced_motion": False,
        }
        result = validator.validate_plan(plan)
        self.assertFalse(result["valid"])
        self.assertTrue(any("static export fallback" in item for item in result["errors"]))
        self.assertTrue(any("reduced-motion" in item for item in result["errors"]))

    def test_excess_density_is_a_warning(self) -> None:
        plan = recommender.build_plan(valid_brief())
        dense = copy.deepcopy(plan)
        dense["slides"][0]["item_count"] = dense["slides"][0]["layout"]["max_items"] + 1
        result = validator.validate_plan(dense)
        self.assertTrue(result["valid"])
        self.assertTrue(any("layout capacity" in item for item in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
