"""Validate bounded reading plans against real repository resources."""

from __future__ import annotations

import copy
import runpy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/skills"))
from common import GovernanceError, load_registry
from plan_context import build_plan, section


class ContextPlanTests(unittest.TestCase):
    def entry(self) -> dict:
        _, entries = load_registry(ROOT)
        entry = copy.deepcopy(next(item for item in entries if item["id"] == "paper-to-ppt"))
        entry["mode_contracts"]["outline"] = {
            "resources": {"references_max": 1, "profiles_max": 0,
                          "required_paths": ["assets/templates/deck-content-plan.md"]}}
        return entry

    def test_initial_plan_reads_only_declared_resources_and_entry(self) -> None:
        report = build_plan(ROOT, self.entry(), "outline")
        self.assertEqual(2, len(report["resources"]))
        self.assertEqual(0, report["reference_file_count"])
        self.assertEqual(sum(item["char_count"] for item in report["resources"]), report["total_selected_chars"])
        self.assertFalse(report["workflow_executed"])
        self.assertFalse(report["authorization_granted"])
        self.assertFalse(report["includes_shared_safety_policies"])

    def test_anchor_selects_children_and_ignores_fenced_headings(self) -> None:
        content = "# Main\n## Small\ntext\n```md\n## Fake\n```\n### Child\nkept\n## Later\nexcluded\n"
        selected = section(content, "small")
        self.assertIn("kept", selected)
        self.assertNotIn("excluded", selected)
        with self.assertRaises(GovernanceError):
            section(content, "fake")
        with self.assertRaises(GovernanceError):
            section(content, "missing")

    def test_resource_escape_archives_and_missing_anchor_fail(self) -> None:
        for path in ("../other.md", "C:/secret.md", "/etc/passwd", "legacy-assets/a.md", "missing.md", "assets/templates/deck-content-plan.md#missing"):
            entry = self.entry()
            entry["mode_contracts"]["outline"]["resources"]["required_paths"] = [path]
            with self.subTest(path=path), self.assertRaises(GovernanceError):
                build_plan(ROOT, entry, "outline")

    def test_short_or_annotated_fence_does_not_expose_fake_headings(self) -> None:
        for inner in ("```", "````python", "~~~"):
            text = "````markdown\n" + inner + "\n## Fenced fake\ncode\n````\n## Real\nvalid\n"
            with self.subTest(inner=inner):
                with self.assertRaises(GovernanceError):
                    section(text, "fenced-fake")
                self.assertEqual("## Real\nvalid\n", section(text, "real"))

    def test_full_related_work_includes_evidence_map_context(self) -> None:
        _, entries = load_registry(ROOT)
        entry = next(item for item in entries if item["id"] == "literature-synthesis")
        report = build_plan(ROOT, entry, "full", "related-work")
        self.assertIn("evidence-map", [item["fragment"] for item in report["resources"]])
        self.assertIn("evidence-map", report["stage_dependencies"])

    def test_research_output_plans_match_executable_mode_contracts(self) -> None:
        _, entries = load_registry(ROOT)
        by_id = {item["id"]: item for item in entries}
        for skill, validator in (("research-dataset-metric-protocols", "validate_evaluation_protocol.py"),
                                 ("research-experiment-design", "validate_experiment_plan.py")):
            entry = by_id[skill]
            module = runpy.run_path(str(ROOT / Path(entry["path"]).parent / "scripts" / validator))
            self.assertEqual(set(entry["modes"]), set(module["MODE_HEADINGS"]))
            for mode, headings in module["MODE_HEADINGS"].items():
                with self.subTest(skill=skill, mode=mode):
                    self.assertEqual([item.removeprefix("## ") for item in headings],
                                     build_plan(ROOT, entry, mode)["output_sections"])

    def test_budget_is_enforced_without_silently_dropping_a_required_file(self) -> None:
        entry = self.entry()
        resources = entry["mode_contracts"]["outline"]["resources"]
        resources["references_max"] = 0
        resources["required_paths"] = ["references/layout-and-style-rules.md"]
        with self.assertRaisesRegex(GovernanceError, "exceeds"):
            build_plan(ROOT, entry, "outline")

    def test_stage_dependencies_are_read_once_without_running_actions(self) -> None:
        entry = self.entry()
        resources = entry["mode_contracts"]["outline"]["resources"]
        resources["stages"] = {
            "layout": {"required_paths": ["references/layout-and-style-rules.md"]},
            "qa": {"depends_on": ["layout"], "required_paths": ["references/layout-and-style-rules.md", "assets/templates/visual-qa-checklist.md"]}}
        report = build_plan(ROOT, entry, "outline", "qa")
        self.assertEqual(["layout", "qa"], report["stage_dependencies"])
        self.assertEqual(4, len(report["resources"]))
        self.assertEqual(1, report["reference_file_count"])
        self.assertFalse(report["workflow_executed"])

    def test_cycles_unknown_stages_and_missing_plans_fail(self) -> None:
        entry = self.entry()
        entry["mode_contracts"]["outline"]["resources"]["stages"] = {
            "a": {"depends_on": ["b"], "required_paths": []},
            "b": {"depends_on": ["a"], "required_paths": []}}
        for stage in ("a", "missing"):
            with self.subTest(stage=stage), self.assertRaises(GovernanceError):
                build_plan(ROOT, entry, "outline", stage)
        del entry["mode_contracts"]["outline"]["resources"]
        with self.assertRaises(GovernanceError):
            build_plan(ROOT, entry, "outline")

    def test_all_reviewed_registry_plans_and_stages_resolve(self) -> None:
        _, entries = load_registry(ROOT)
        for entry in entries:
            for mode in entry["modes"]:
                contracts = entry.get("mode_contracts", {})
                contract = {**contracts.get("*", {}), **contracts.get(mode, {})}
                resources = contract.get("resources")
                if not resources:
                    continue
                for stage in [None, *resources.get("stages", {})]:
                    with self.subTest(skill=entry["id"], mode=mode, stage=stage):
                        self.assertTrue(build_plan(ROOT, entry, mode, stage)["valid"])


if __name__ == "__main__":
    unittest.main()
