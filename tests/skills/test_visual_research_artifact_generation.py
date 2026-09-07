"""Regression tests for the deterministic Draw.io research-visual backend."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "skills" / "global" / "visual-research-artifact-generation"
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_drawio import build  # noqa: E402
from drawio_model import SpecError  # noqa: E402
from export_drawio import ExportError, export, find_cli  # noqa: E402
from validate_drawio import validate_path  # noqa: E402


class VisualResearchArtifactGenerationTests(unittest.TestCase):
    def sample(self) -> dict:
        return {
            "title": "方法 & 结果 <overview>",
            "layout": "horizontal",
            "theme": "paper-light",
            "nodes": [
                {"id": "input", "label": "输入 <data>", "kind": "data"},
                {"id": "model", "label": "模型 & loss", "kind": "process"},
                {
                    "id": "analysis",
                    "label": "分析",
                    "kind": "group",
                    "container": True,
                    "width": 360,
                    "height": 240,
                },
                {"id": "metric", "label": "指标 $m$", "parent": "analysis"},
            ],
            "edges": [
                {"source": "input", "target": "model", "label": "预处理"},
                {"source": "model", "target": "metric", "kind": "dashed"},
            ],
        }

    def write_spec(self, directory: Path, data: dict | None = None) -> Path:
        path = directory / "graph.json"
        path.write_text(
            json.dumps(data or self.sample(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def test_builds_valid_editable_drawio_with_unicode_and_container(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
            directory = Path(temporary)
            source = self.write_spec(directory)
            output = directory / "diagram.drawio"
            presets = SKILL_ROOT / "assets" / "drawio-style-presets.json"

            build(source, output, presets)

            self.assertEqual([], validate_path(output))
            root = ET.parse(output).getroot()
            cells = {cell.get("id"): cell for cell in root.findall(".//mxCell")}
            self.assertEqual("输入 <data>", cells["input"].get("value"))
            self.assertEqual("模型 & loss", cells["model"].get("value"))
            self.assertEqual("analysis", cells["metric"].get("parent"))
            self.assertEqual("1", cells["analysis"].get("vertex"))
            self.assertEqual("input", next(cell for cell in cells.values() if cell.get("edge") == "1").get("source"))

    def test_output_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
            directory = Path(temporary)
            source = self.write_spec(directory)
            first = directory / "first.drawio"
            second = directory / "second.drawio"
            presets = SKILL_ROOT / "assets" / "drawio-style-presets.json"

            build(source, first, presets)
            build(source, second, presets)

            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_rejects_duplicate_node_ids(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
            directory = Path(temporary)
            data = self.sample()
            data["nodes"].append({"id": "input", "label": "duplicate"})
            source = self.write_spec(directory, data)
            output = directory / "diagram.drawio"

            with self.assertRaisesRegex(SpecError, "duplicate node ID"):
                build(
                    source,
                    output,
                    SKILL_ROOT / "assets" / "drawio-style-presets.json",
                )
            self.assertFalse(output.exists())

    def test_rejects_container_parent_cycle(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
            directory = Path(temporary)
            data = {
                "nodes": [
                    {"id": "a", "label": "A", "container": True, "parent": "b"},
                    {"id": "b", "label": "B", "container": True, "parent": "a"},
                ]
            }
            source = self.write_spec(directory, data)

            with self.assertRaisesRegex(SpecError, "parent cycle"):
                build(
                    source,
                    directory / "cycle.drawio",
                    SKILL_ROOT / "assets" / "drawio-style-presets.json",
                )

    def test_validator_reports_missing_edge_endpoint_and_bad_geometry(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
            path = Path(temporary) / "invalid.drawio"
            path.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<mxfile><diagram><mxGraphModel><root>
<mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="n" vertex="1" parent="1"><mxGeometry x="0" y="0" width="-1" height="x"/></mxCell>
<mxCell id="e" edge="1" parent="1" source="n" target="missing"><mxGeometry relative="1"/></mxCell>
<mxCell id="e2" edge="1" parent="1" source="e" target="n"><mxGeometry relative="1"/></mxCell>
</root></mxGraphModel></diagram></mxfile>""",
                encoding="utf-8",
            )

            errors = validate_path(path)

            self.assertTrue(any("non-positive width" in error for error in errors))
            self.assertTrue(any("invalid height" in error for error in errors))
            self.assertTrue(any("missing target" in error for error in errors))
            self.assertTrue(any("source 'e' is not a vertex" in error for error in errors))

    def test_does_not_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
            directory = Path(temporary)
            source = self.write_spec(directory)
            output = directory / "diagram.drawio"
            output.write_text("user content", encoding="utf-8")

            with self.assertRaisesRegex(SpecError, "pass --force"):
                build(
                    source,
                    output,
                    SKILL_ROOT / "assets" / "drawio-style-presets.json",
                )
            self.assertEqual("user content", output.read_text(encoding="utf-8"))

    def test_missing_explicit_cli_is_detected_without_output_mutation(self) -> None:
        self.assertIsNone(find_cli("definitely-missing-drawio-cli-for-test"))

    def test_export_atomically_replaces_authorized_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
            directory = Path(temporary)
            source = self.write_spec(directory)
            drawio = directory / "source.drawio"
            output = directory / "preview.svg"
            output.write_text("previous preview", encoding="utf-8")
            build(
                source,
                drawio,
                SKILL_ROOT / "assets" / "drawio-style-presets.json",
            )

            def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                destination = Path(command[command.index("--output") + 1])
                destination.write_text("<svg>verified</svg>", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("export_drawio.subprocess.run", side_effect=fake_run):
                export(drawio, output, "svg", "fake-drawio", force=True)

            self.assertEqual("<svg>verified</svg>", output.read_text(encoding="utf-8"))

    def test_export_failure_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
            directory = Path(temporary)
            source = self.write_spec(directory)
            drawio = directory / "source.drawio"
            output = directory / "preview.svg"
            output.write_text("keep me", encoding="utf-8")
            build(
                source,
                drawio,
                SKILL_ROOT / "assets" / "drawio-style-presets.json",
            )
            failed = subprocess.CompletedProcess(
                ["fake-drawio"], 1, "", "render failure"
            )

            with patch("export_drawio.subprocess.run", return_value=failed):
                with self.assertRaisesRegex(ExportError, "render failure"):
                    export(drawio, output, "svg", "fake-drawio", force=True)

            self.assertEqual("keep me", output.read_text(encoding="utf-8"))

    def test_export_rejects_success_without_artifact(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
            directory = Path(temporary)
            source = self.write_spec(directory)
            drawio = directory / "source.drawio"
            output = directory / "preview.svg"
            output.write_text("keep me", encoding="utf-8")
            build(
                source,
                drawio,
                SKILL_ROOT / "assets" / "drawio-style-presets.json",
            )
            empty = subprocess.CompletedProcess(["fake-drawio"], 0, "", "")

            with patch("export_drawio.subprocess.run", return_value=empty):
                with self.assertRaisesRegex(ExportError, "produced no non-empty output"):
                    export(drawio, output, "svg", "fake-drawio", force=True)

            self.assertEqual("keep me", output.read_text(encoding="utf-8"))

    def test_cli_build_and_json_validation_round_trip(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
            directory = Path(temporary)
            source = self.write_spec(directory)
            output = directory / "cli.drawio"

            built = subprocess.run(
                [sys.executable, str(SCRIPTS / "build_drawio.py"), str(source), str(output)],
                check=False,
                capture_output=True,
                text=True,
                shell=False,
            )
            self.assertEqual(0, built.returncode, built.stderr)
            validated = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_drawio.py"),
                    str(output),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
                shell=False,
            )
            self.assertEqual(0, validated.returncode, validated.stderr)
            self.assertTrue(json.loads(validated.stdout)["valid"])


if __name__ == "__main__":
    unittest.main()
