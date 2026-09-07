"""Offline distribution contracts for included notices and visual resources."""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import unittest

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/research-skills"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicDistributionContracts(unittest.TestCase):
    def test_upstream_license_bytes_and_attributed_files_survive_packaging(self):
        expected = {
            "LICENSES/Apache-2.0.txt": "c0cfc8f0c446c128ddb9bcd1455b45926e5fb8ba4f1230c47b14721351148328",
            "LICENSES/UI-UX-Pro-Max-MIT.txt": "738f69dfa83db5c347c678fb9d90e560877059f0de93a327c39001bff92dc014",
        }
        for relative, digest in expected.items():
            with self.subTest(path=relative):
                original = (ROOT / relative).read_bytes()
                self.assertEqual(digest, hashlib.sha256(original).hexdigest())
                self.assertEqual(original, (PLUGIN / relative).read_bytes())
        for relative in ("LICENSE", "NOTICE.md"):
            self.assertEqual((ROOT / relative).read_bytes(), (PLUGIN / relative).read_bytes())
        for filename in ("arxiv_pdf_compat.py", "arxiv_priority_mcp_server.py"):
            for base in (ROOT / "skills/global/literature-monitor", PLUGIN / "skills/literature-monitor"):
                header = (base / "scripts" / filename).read_text(encoding="utf-8").splitlines()[:20]
                self.assertIn("# SPDX-License-Identifier: Apache-2.0", header)
                self.assertIn("# Copyright 2024 Joseph Blazick", header)
                self.assertTrue(any("d22255b0c24578ed214d2918d2ff2786d92a778e" in line for line in header))

    def test_source_and_plugin_generate_compatible_visual_plans(self):
        bases = (ROOT / "skills/global/paper-to-ppt", PLUGIN / "skills/paper-to-ppt")
        modules = [load_module(base / "scripts/recommend_visual_system.py", f"_distribution_visual_{i}")
                   for i, base in enumerate(bases)]
        validators = [load_module(base / "scripts/validate_visual_plan.py", f"_distribution_visual_check_{i}")
                      for i, base in enumerate(bases)]
        schema = json.loads((bases[0] / "assets/schemas/visual-plan.schema.json").read_text(encoding="utf-8"))
        for deck, language, ratio in itertools.product(
            ("paper-talk", "lab-meeting", "project-update", "defense", "conference", "course"),
            ("zh", "en", "bilingual"), ("16:9", "4:3"),
        ):
            with self.subTest(deck=deck, language=language, ratio=ratio):
                brief = {"deck_type": deck, "audience": "research audience", "language": language,
                         "aspect_ratio": ratio, "duration_minutes": 20, "slides": [
                    {"id": "fixture-result", "role": "main-results", "claim": "Synthetic comparison fixture",
                     "content_types": ["chart"], "evidence_type": "comparison", "item_count": 1,
                     "chart_fields": ["metric-name", "units", "baseline-identity", "direct-takeaway"],
                     "alt_text": "Synthetic comparison used to test plan structure", "source_trace": "synthetic-fixture"},
                ]}
                plans = [module.build_plan(brief) for module in modules]
                self.assertEqual(plans[0], plans[1])
                for plan, validator in zip(plans, validators):
                    jsonschema.validate(plan, schema)
                    checked = validator.validate_plan(plan)
                    self.assertTrue(checked["valid"], checked)
                    self.assertTrue(plan["slides"][0]["motion"]["static_fallback"])
                    self.assertTrue(plan["slides"][0]["accessibility"]["color_not_only"])


if __name__ == "__main__":
    unittest.main()
