"""Checks for the shared output-voice policy and its regression lint."""

from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "skills" / "_shared" / "output-voice.md"


def load_lint():
    spec = importlib.util.spec_from_file_location("lint_output_voice", ROOT / "scripts" / "lint_output_voice.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OutputVoiceTests(unittest.TestCase):
    def test_policy_examples_separate_form_filling_from_plain_answer(self) -> None:
        lint = load_lint()
        examples = re.findall(r"<example>\n(.*?)</example>", POLICY.read_text(encoding="utf-8"), re.S)
        self.assertEqual(2, len(examples))
        form, plain = (lint.scan(text) for text in examples)
        self.assertGreater(form[1], plain[1])
        self.assertEqual(0.0, plain[1])

    def test_code_and_info_patterns_do_not_count(self) -> None:
        lint = load_lint()
        hits, density = lint.scan("我们进行了实验分析。\n```\n# 值得注意的是 leverage\n```\n`CLM-001`")
        self.assertEqual(0.0, density)
        self.assertIn("info:翻译腔", hits)

    def test_active_skills_link_the_policy(self) -> None:
        registry = json.loads((ROOT / "skills" / "registry.yaml").read_text(encoding="utf-8"))
        for entry in registry["skills"]:
            if entry.get("status") != "active" or entry["name"].startswith("domain-"):
                continue
            text = (ROOT / entry["path"]).read_text(encoding="utf-8")
            self.assertIn("_shared/output-voice.md", text, entry["name"])

    def test_output_contract_links_policy_and_drops_generic_limitations(self) -> None:
        text = (ROOT / "skills" / "_shared" / "academic-output-contracts.md").read_text(encoding="utf-8")
        self.assertIn("output-voice.md", text)
        self.assertNotIn("list unresolved evidence", text)


if __name__ == "__main__":
    unittest.main()
