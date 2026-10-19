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
            "items": [{"id": "diagnostic:baseline", "content_html": "Setup",
                       "date_published": "2026-10-19T13:40:00+00:00"}]}))
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
        self.assertEqual(json.loads((self.output / diagnostics.DIAGNOSTIC).read_bytes()),
                         json.loads(self.source.read_bytes()))

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


    def test_scheduled_entries_are_released_only_at_their_own_times(self):
        feed = json.loads(self.source.read_text())
        for minute in (30, 25):
            feed['items'].insert(0, {
                'id': f'diagnostic:comparison:{minute}',
                'content_html': f'16:{minute} test',
                'date_published': f'2026-10-19T16:{minute}:00+02:00'})
        self.source.write_text(json.dumps(feed))
        for moment, expected in (
            ('2026-10-19T14:24:59+00:00', ['diagnostic:baseline']),
            ('2026-10-19T14:25:00+00:00', ['diagnostic:comparison:25', 'diagnostic:baseline']),
            ('2026-10-19T14:30:00+00:00', ['diagnostic:comparison:25', 'diagnostic:comparison:30',
                                        'diagnostic:baseline']),
        ):
            with self.subTest(moment=moment):
                diagnostics.bundle(self.output, self.source, datetime.fromisoformat(moment))
                actual = json.loads((self.output / diagnostics.DIAGNOSTIC).read_text())
                self.assertEqual([item['id'] for item in actual['items']], expected)
        self.assertEqual(json.loads(self.source.read_text()), feed)

    def test_ambiguous_scheduled_time_is_rejected_before_writing(self):
        feed = json.loads(self.source.read_text())
        feed['items'][0]['date_published'] = '2026-10-19T16:25:00'
        self.source.write_text(json.dumps(feed))
        with self.assertRaisesRegex(ValueError, 'UTC offset'):
            diagnostics.bundle(self.output, self.source)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
