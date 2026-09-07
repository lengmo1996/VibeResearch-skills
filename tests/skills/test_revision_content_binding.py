"""A reviewed manifest must not accept changed manuscript replacement bytes."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/global/writing-academic/scripts/apply_revision_patch.py"
spec = importlib.util.spec_from_file_location("revision_content_binding", SCRIPT)
assert spec and spec.loader
revision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revision)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class RevisionContentBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.original = "\r\nOriginal claim.\r\n"
        self.source = "Before\r\n<!-- START -->" + self.original + "<!-- END -->\r\nAfter"
        self.replacement = "\r\nA bounded claim with 中文 and \\cite{source}.\r\n"
        (self.root / "paper.md").write_bytes(self.source.encode("utf-8"))
        (self.root / "replacement.md").write_bytes(self.replacement.encode("utf-8"))
        self.manifest = {
            "schema_version": "1.1.0",
            "target_file": "paper.md",
            "target_sha256": digest(self.source),
            "patches": [{
                "id": "REV-001", "accepted_audit_ids": ["AUD-001"],
                "start_marker": "<!-- START -->", "end_marker": "<!-- END -->",
                "original_sha256": digest(self.original),
                "replacement_file": "replacement.md",
                "replacement_sha256": digest(self.replacement),
            }],
        }

    def test_bound_replacement_preserves_untouched_unicode_and_line_endings(self) -> None:
        target, before, after, prepared = revision.prepare(self.root, self.manifest)
        self.assertEqual(self.source, before)
        self.assertEqual(self.source.replace(self.original, self.replacement), after)
        self.assertEqual(digest(self.replacement), prepared[0]["replacement_sha256"])
        self.assertEqual(self.source.encode("utf-8"), target.read_bytes())

    def test_missing_hash_is_rejected_in_both_schema_versions(self) -> None:
        del self.manifest["patches"][0]["replacement_sha256"]
        for version in ("1.0.0", "1.1.0"):
            with self.subTest(version=version):
                self.manifest["schema_version"] = version
                with self.assertRaisesRegex(ValueError, "replacement_sha256 is required"):
                    revision.prepare(self.root, self.manifest)

    def test_malformed_schema_versions_fail_as_validation_errors(self) -> None:
        for value in ([], {}, None, 1):
            with self.subTest(value=value):
                self.manifest["schema_version"] = value
                with self.assertRaisesRegex(ValueError, "schema_version"):
                    revision.prepare(self.root, self.manifest)

    def test_replacement_drift_rejects_apply_without_changing_target(self) -> None:
        revision.prepare(self.root, self.manifest)  # the reviewed preview
        (self.root / "replacement.md").write_bytes((self.replacement + "!").encode("utf-8"))
        (self.root / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        output = io.StringIO()
        with patch.object(sys, "argv", [str(SCRIPT), "--root", str(self.root), "--manifest", "manifest.json", "--apply"]):
            with contextlib.redirect_stdout(output):
                self.assertEqual(1, revision.main())
        result = json.loads(output.getvalue())
        self.assertFalse(result["applied"])
        self.assertIn("replacement hash conflict", result["errors"][0])
        self.assertEqual(self.source.encode("utf-8"), (self.root / "paper.md").read_bytes())

    def test_new_reviewed_hash_can_explicitly_bind_new_content(self) -> None:
        changed = self.replacement + "!"
        (self.root / "replacement.md").write_bytes(changed.encode("utf-8"))
        self.manifest["patches"][0]["replacement_sha256"] = digest(changed)
        target, _, revised, _ = revision.prepare(self.root, self.manifest)
        revision._atomic_write(target, revised)
        self.assertEqual(self.source.replace(self.original, changed).encode("utf-8"), target.read_bytes())


if __name__ == "__main__":
    unittest.main()
