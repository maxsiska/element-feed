from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import publication as pub


CONFIG = {"enabled": True}
TODAY = {"items": [{"id": "2026-10-19", "content_html": "Lunch"}]}
STALE = {"items": [{"id": "2026-10-16", "content_html": "Old lunch"}]}


def berlin(value):
    return datetime.fromisoformat(value).replace(tzinfo=pub.BERLIN)


class PublicationTests(unittest.TestCase):
    def test_missing_or_stale_feed_gets_a_publication_attempt(self):
        for live in (None, STALE, {"items": []},
                     {"items": [{"id": "test-123", "content_html": "Test"}]}):
            with self.subTest(live=live):
                publish, _ = pub.should_publish(CONFIG, live, berlin("2026-10-19T11:35"))
                self.assertTrue(publish)

    def test_successful_publication_stops_all_further_attempts(self):
        for hour in ("11:20", "11:35", "11:50", "16:23"):
            self.assertFalse(pub.should_publish(CONFIG, TODAY, berlin(f"2026-10-19T{hour}"))[0])

    def test_late_missing_feed_fails_instead_of_sending_old_lunch_invitation(self):
        for hour in ("12:15", "12:30", "16:23"):
            with self.subTest(hour=hour), self.assertRaisesRegex(RuntimeError, "MISSED PUBLICATION"):
                pub.should_publish(CONFIG, STALE, berlin(f"2026-10-19T{hour}"))

    def test_no_early_or_weekend_publication(self):
        for value in ("2026-10-19T11:14:59", "2026-10-17T11:35", "2026-10-18T11:35"):
            self.assertFalse(pub.should_publish(CONFIG, STALE, berlin(value))[0])

    def test_disable_can_clear_feed_after_hours_and_on_weekends(self):
        now = berlin("2026-10-18T23:00")
        for live in (STALE, TODAY, None):
            self.assertTrue(pub.should_publish({"enabled": False}, live, now)[0])
        self.assertFalse(pub.should_publish({"enabled": False}, {"items": []}, now)[0])
        pub.check_deployment_window({"items": []}, now)

    def test_window_uses_berlin_time_across_dst_change(self):
        for value, expected in (("2026-10-19T09:15", True),
                                ("2026-10-19T10:15", False),
                                ("2026-10-26T09:15", False),
                                ("2026-10-26T10:15", True),
                                ("2026-10-26T11:15", False)):
            now = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
            with self.subTest(value=value):
                self.assertEqual(pub.in_window(now), expected)

    def test_deployment_rechecks_date_and_time_after_generation(self):
        pub.check_deployment_window(TODAY, berlin("2026-10-19T11:50"))
        for value in ("2026-10-19T12:15", "2026-10-20T11:50"):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                pub.check_deployment_window(TODAY, berlin(value))

    def test_verify_recovers_from_stale_cache_and_network_failure(self):
        with (patch("publication.read_feed", side_effect=[OSError("offline"), STALE, TODAY]) as read,
              patch("publication.clock.sleep") as sleep,
              patch("publication.clock.monotonic", side_effect=[0, 0, 1])):
            pub.verify_feed("https://example.org/feed.json", TODAY)
        self.assertEqual(read.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_verification_requires_expected_contents_and_reports_failure(self):
        changed = {"items": [{"id": "2026-10-19", "content_html": "Wrong contents"}]}
        for live in (STALE, changed):
            with (self.subTest(live=live), patch("publication.read_feed", return_value=live),
                  patch("publication.clock.monotonic", side_effect=[0, 180]),
                  self.assertRaisesRegex(RuntimeError, "PUBLICATION NOT VERIFIED")):
                pub.verify_feed("https://example.org/feed.json", TODAY)

    def test_plan_outputs_false_when_already_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            config.write_text(json.dumps(CONFIG))
            output = Path(tmp) / "outputs"
            with (patch("publication.read_feed", return_value=TODAY),
                  patch("publication.berlin_now", return_value=berlin("2026-10-19T11:35")),
                  patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)})):
                self.assertEqual(pub.main(["plan", "--config", str(config),
                                           "--feed-url", "https://example.org/feed.json"]), 0)
            self.assertEqual(output.read_text(), "publish=false\n")


if __name__ == "__main__":
    unittest.main()
