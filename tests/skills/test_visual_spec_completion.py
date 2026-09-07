"""Completed visual records need closed provenance and honest validation states."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/global/visual-research-artifact-generation"
spec = importlib.util.spec_from_file_location("visual_spec_completion", SKILL / "scripts/validate_visual_spec.py")
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def completed_record() -> str:
    return """# Visual Research Artifact Specification

## Contract
- Figure ID: FIG-001
- Panel IDs: PAN-001
- Primary narrative role: method
- Target claim IDs: CLM-001
- Upstream evidence/artifact IDs: SRC-001
- Companion figure IDs: none
- Mode / intended use: drawio-diagram / method
- Requested editable/rendered formats: drawio, svg
- Backend and rationale: Draw.io for editable nodes
- Authorized output paths: figures/method.drawio

## Source facts and elements
| Source ID | Supplied fact/data/relation | Provenance | Evidence status | Claim IDs | Output element/panel IDs |
|---|---|---|---|---|---|
| SRC-001 | A precedes B | supplied graph.json | verified | CLM-001 | ELEM-001 / PAN-001 |

| Element ID | Figure/panel ID | Type | Label/value | Narrative function | Geometry/encoding | Source IDs | Editable |
|---|---|---|---|---|---|---|---|
| ELEM-001 | FIG-001 / PAN-001 | node | A | input | rectangle | SRC-001 | yes |

## Claim and figure coverage
| Claim ID | Evidence source IDs | Figure/panel IDs | Visible assertion | Caption boundary | Coverage status |
|---|---|---|---|---|---|
| CLM-001 | SRC-001 | FIG-001 / PAN-001 | ordering | no performance claim | verified |

## Cross-figure relationships
| Figure ID | Related figure ID | Relation | Shared invariant | Check status | Evidence |
|---|---|---|---|---|---|
| FIG-001 | none | independent | terminology | not-applicable | no companions requested |

## Revision ledger
- Preserved element IDs: none
- Changed element IDs and reason: none
- Added element IDs: ELEM-001
- Removed element IDs and authorization: none

## Validation matrix
| Layer | Command/tool | Expected | Observed | Status | Blocker |
|---|---|---|---|---|---|
| source/content | graph review | same edges | same edges | passed | |
| structure/schema | validate_drawio.py | valid | no issues | passed | |
| compile/build | build_drawio.py | editable nodes | nodes produced | passed | |
| render/export | | | | blocked | renderer unavailable |
| visual inspection | | | | blocked | renderer unavailable |
| semantic/value cross-check | source comparison | A before B | A before B | passed | |
| claim-evidence trace | coverage review | all sources linked | SRC-001 linked | passed | |
| cross-figure consistency | | | | not-applicable | no companions requested |

## Reproduction and uncertainty
- Exact command: python build_drawio.py graph.json figures/method.drawio
- Runtime/version: Python 3.11
- Unresolved labels/data/geometry: none
- Preview identity:
"""


class VisualSpecCompletionTests(unittest.TestCase):
    def test_template_is_only_valid_as_a_template(self) -> None:
        text = (SKILL / "templates/visual-artifact-spec.md").read_text(encoding="utf-8")
        self.assertEqual([], validator.validate(text))
        self.assertTrue(validator.validate(text, completed=True))

    def test_honest_blocked_rendering_record_is_consistent(self) -> None:
        self.assertEqual([], validator.validate(completed_record(), completed=True))

    def test_standalone_does_not_need_invented_claims(self) -> None:
        text = completed_record().replace("Primary narrative role: method", "Primary narrative role: standalone")
        text = text.replace("Target claim IDs: CLM-001", "Target claim IDs: none")
        text = text.replace("| verified | CLM-001 |", "| verified | none |")
        text = text.replace("| CLM-001 | SRC-001 | FIG-001 / PAN-001 | ordering | no performance claim | verified |\n", "")
        text = text.replace("| claim-evidence trace | coverage review | all sources linked | SRC-001 linked | passed | |", "| claim-evidence trace | | | | not-applicable | standalone has no upstream claim |")
        self.assertEqual([], validator.validate(text, completed=True))

    def test_broken_claim_references_are_rejected(self) -> None:
        text = completed_record().replace("| CLM-001 | SRC-001 | FIG-001 / PAN-001 |", "| CLM-001 | SRC-999 | FIG-999 / PAN-999 |")
        self.assertTrue(any("broken" in e for e in validator.validate(text, completed=True)))

    def test_verified_claim_rejects_candidate_source(self) -> None:
        text = completed_record().replace("| verified | CLM-001 |", "| candidate | CLM-001 |")
        self.assertTrue(any("unverified source" in e for e in validator.validate(text, completed=True)))

    def test_duplicate_source_ids_and_malformed_tables_fail(self) -> None:
        row = "| SRC-001 | A precedes B | supplied graph.json | verified | CLM-001 | ELEM-001 / PAN-001 |"
        text = completed_record().replace(row, row + "\n" + row)
        self.assertTrue(any("unique" in e for e in validator.validate(text, completed=True)))
        text = completed_record().replace("| Source ID | Supplied fact/data/relation | Provenance | Evidence status | Claim IDs | Output element/panel IDs |", "| Source ID |")
        self.assertTrue(validator.validate(text, completed=True))

    def test_render_success_needs_evidence_and_preview_identity(self) -> None:
        text = completed_record().replace("| render/export | | | | blocked | renderer unavailable |", "| render/export | export_drawio.py | SVG | SVG created | passed | |")
        self.assertTrue(any("preview identity" in e for e in validator.validate(text, completed=True)))
        self.assertEqual([], validator.validate(text.replace("- Preview identity:", "- Preview identity: figures/method.svg SHA256 recorded in render log"), completed=True))

    def test_unknown_status_is_rejected(self) -> None:
        text = completed_record().replace("| source/content | graph review | same edges | same edges | passed | |", "| source/content | graph review | same edges | same edges | maybe | |")
        self.assertTrue(any("validation status" in e for e in validator.validate(text, completed=True)))

    def test_verified_panel_needs_actual_source_to_element_path(self) -> None:
        text = completed_record().replace("Panel IDs: PAN-001", "Panel IDs: PAN-001, PAN-002")
        text = text.replace("| CLM-001 | SRC-001 | FIG-001 / PAN-001 |", "| CLM-001 | SRC-001 | PAN-002 |")
        self.assertTrue(any("source-to-element path" in e for e in validator.validate(text, completed=True)))

    def test_malformed_explicit_ids_are_not_silently_ignored(self) -> None:
        text = completed_record().replace("Target claim IDs: CLM-001", "Target claim IDs: CLM-001, CLM-invalid")
        self.assertTrue(any("unique valid IDs" in e for e in validator.validate(text, completed=True)))

    def test_placeholders_do_not_count_as_success_evidence(self) -> None:
        text = completed_record().replace("Runtime/version: Python 3.11", "Runtime/version: not checked")
        self.assertTrue(any("runtime identity" in e for e in validator.validate(text, completed=True)))
        text = completed_record().replace("| render/export | | | | blocked | renderer unavailable |", "| render/export | export_drawio.py | SVG | SVG created | passed | |")
        text = text.replace("- Preview identity:", "- Preview identity: not checked")
        self.assertTrue(any("preview identity" in e for e in validator.validate(text, completed=True)))

    def test_aggregate_success_cannot_contradict_its_detail_records(self) -> None:
        base = completed_record()
        blocked_claim = base.replace("no performance claim | verified", "no performance claim | blocked")
        self.assertTrue(any("blocked claim" in e for e in validator.validate(blocked_claim, completed=True)))
        missing_source = blocked_claim.replace("| verified | CLM-001 |", "| missing | CLM-001 |")
        self.assertTrue(any("contradictory sources" in e for e in validator.validate(missing_source, completed=True)))
        companion = base.replace("Companion figure IDs: none", "Companion figure IDs: FIG-002")
        companion = companion.replace("| FIG-001 | none | independent | terminology | not-applicable | no companions requested |", "| FIG-001 | FIG-002 | companion | terminology | failed | symbol mismatch |")
        companion = companion.replace("| cross-figure consistency | | | | not-applicable | no companions requested |", "| cross-figure consistency | comparison | same symbols | same symbols | passed | |")
        self.assertTrue(any("failed relationships" in e for e in validator.validate(companion, completed=True)))


if __name__ == "__main__":
    unittest.main()
