#!/usr/bin/env python3
"""Unit tests for the deterministic presentation visual recommender."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import recommend_visual_system as recommender


def base_brief() -> dict:
    return {
        "deck_type": "paper-talk",
        "audience": "lab researchers",
        "language": "zh",
        "aspect_ratio": "16:9",
        "domain": "computer-science",
        "duration_minutes": 15,
        "candidate_count": 3,
        "slides": [
            {
                "id": "s1",
                "role": "title",
                "claim": "A source-faithful paper talk",
                "content_types": ["title", "metadata"],
                "density": "low",
            },
            {
                "id": "s2",
                "role": "method-overview",
                "claim": "The method aligns two modalities in three stages",
                "content_types": ["pipeline", "architecture"],
                "density": "medium",
                "item_count": 6,
                "alt_text": "Three-stage method pipeline from two inputs to one prediction.",
                "source_trace": "Paper Figure 2, page 4",
                "interaction_intent": "progressive-reveal",
            },
        ],
    }


class RecommendVisualSystemTests(unittest.TestCase):
    def test_same_input_is_deterministic(self) -> None:
        first = recommender.build_plan(base_brief())
        second = recommender.build_plan(copy.deepcopy(base_brief()))
        self.assertEqual(
            json.dumps(first, ensure_ascii=False, sort_keys=True),
            json.dumps(second, ensure_ascii=False, sort_keys=True),
        )

    def test_research_context_changes_top_style(self) -> None:
        technical = recommender.build_plan(base_brief())
        biomedical_brief = base_brief()
        biomedical_brief["domain"] = "biomedicine"
        biomedical = recommender.build_plan(biomedical_brief)
        self.assertEqual(technical["candidates"][0]["id"], "precise-blue")
        self.assertEqual(biomedical["candidates"][0]["id"], "biomedical-teal")

    def test_layout_selection_maps_method_role(self) -> None:
        plan = recommender.build_plan(base_brief())
        self.assertEqual(plan["slides"][1]["layout"]["id"], "method-pipeline")
        self.assertEqual(plan["slides"][1]["motion"]["type"], "appear")

    def test_language_selects_font_fallbacks(self) -> None:
        chinese = recommender.build_plan(base_brief())
        english_brief = base_brief()
        english_brief["language"] = "en"
        english = recommender.build_plan(english_brief)
        self.assertIn("Microsoft YaHei", chinese["visual_system"]["typography"]["heading"])
        self.assertIn("Aptos Display", english["visual_system"]["typography"]["heading"])

    def test_unknown_context_uses_safe_fallback_with_warning(self) -> None:
        brief = base_brief()
        brief["deck_type"] = "research-retreat"
        plan = recommender.build_plan(brief)
        self.assertTrue(any("Unknown deck_type" in warning for warning in plan["warnings"]))
        self.assertGreaterEqual(len(plan["candidates"]), 2)

    def test_project_update_and_lab_meeting_receive_contextual_rankings(self) -> None:
        project = base_brief()
        project["deck_type"] = "project-update"
        project["domain"] = "artificial-intelligence"
        lab = base_brief()
        lab["deck_type"] = "lab-meeting"
        lab["domain"] = "general"
        project_plan = recommender.build_plan(project)
        lab_plan = recommender.build_plan(lab)
        self.assertEqual(project_plan["candidates"][0]["id"], "technical-indigo")
        self.assertEqual(lab_plan["candidates"][0]["id"], "precise-blue")

    def test_missing_slide_ids_receive_unique_stable_ids(self) -> None:
        brief = base_brief()
        brief["slides"] = [
            {"role": "motivation", "content_types": ["claim"], "density": "low"},
            {"role": "summary", "content_types": ["takeaways"], "density": "low"},
        ]
        plan = recommender.build_plan(brief)
        self.assertEqual([slide["id"] for slide in plan["slides"]], ["slide-1", "slide-2"])

    def test_invalid_language_is_rejected(self) -> None:
        brief = base_brief()
        brief["language"] = "fr"
        with self.assertRaises(recommender.BriefError):
            recommender.build_plan(brief)


if __name__ == "__main__":
    unittest.main()
