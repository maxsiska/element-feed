from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import diagnostics
from scheduled_test import build_test


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / "public"
        self.source = Path(self.tmp.name) / "diagnostic.json"
        self.source.write_text(json.dumps({
            "version": "https://jsonfeed.org/version/1.1", "title": "Diagnostics",
            "items": [{"id": "diagnostic:baseline", "content_html": "Setup"}]}))
        xml, data = build_test({"title": "Lunch", "description": "Daily lunch"},
                               datetime(2026, 10, 19, 13, 30, tzinfo=timezone.utc),
                               "15:30 test", "https://example.org")
        self.live = {"feed.json": data, "feed.xml": xml}

    def test_diagnostic_publication_preserves_production_bytes_and_ids(self):
        with patch("diagnostics.read_public", side_effect=self.live.__getitem__):
            diagnostics.prepare(self.output, self.source)
            diagnostics.guard(self.output)
        for path, content in self.live.items():
            self.assertEqual((self.output / path).read_bytes(), content)
        self.assertEqual((self.output / diagnostics.DIAGNOSTIC).read_bytes(),
                         self.source.read_bytes())

    def test_download_failure_or_mixed_versions_never_creates_output(self):
        mixed = json.loads(self.live["feed.json"])
        mixed["items"][0]["id"] = "a-different-production-entry"
        for second in (OSError("offline"), self.live["feed.xml"]):
            with (self.subTest(second=type(second).__name__),
                  patch("diagnostics.read_public", side_effect=[json.dumps(mixed).encode(), second]),
                  self.assertRaises((OSError, ValueError))):
                diagnostics.prepare(self.output, self.source)
            self.assertFalse(self.output.exists())

    def test_changed_production_blocks_deployment(self):
        with patch("diagnostics.read_public", side_effect=self.live.__getitem__):
            diagnostics.prepare(self.output, self.source)
        with (patch("diagnostics.read_public", return_value=b"new production contents"),
              self.assertRaisesRegex(ValueError, "changed")):
            diagnostics.guard(self.output)

    def test_normal_publication_can_bundle_diagnostics_without_changing_lunch(self):
        self.output.mkdir()
        for path, body in self.live.items():
            (self.output / path).write_bytes(body)
        diagnostics.bundle(self.output, self.source)
        for path, body in self.live.items():
            self.assertEqual((self.output / path).read_bytes(), body)

    def test_test_ids_cannot_use_the_production_namespace_or_repeat(self):
        original = json.loads(self.source.read_text())
        for ids in (("2026-10-19",), ("diagnostic:one", "diagnostic:one")):
            original["items"] = [{"id": value} for value in ids]
            self.source.write_text(json.dumps(original))
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                diagnostics.bundle(self.output, self.source)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
