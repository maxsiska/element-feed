from datetime import timedelta
import json
import unittest
import xml.etree.ElementTree as ET

from scheduled_test import build_test, check_window, parse_time


class ScheduledTestTests(unittest.TestCase):
    def test_message_is_exact_and_reruns_reuse_the_id(self):
        target = parse_time("2026-10-19T15:30:00+02:00")
        config = {"title": "Lunch", "description": "Lunch invitations"}
        first = build_test(config, target, "15:30 test", "https://example.org")
        self.assertEqual(first, build_test(config, target, "15:30 test", "https://example.org"))
        [item] = json.loads(first[1])["items"]
        self.assertEqual(item["content_html"], "15:30 test")
        self.assertEqual(item["title"], "15:30 test")
        self.assertEqual(item["id"], "scheduled-test:2026-10-19T13:30:00+00:00")
        self.assertEqual(ET.fromstring(first[0]).findtext("channel/item/guid"), item["id"])

    def test_test_cannot_publish_early_late_or_another_day(self):
        target = parse_time("2026-10-19T15:30:00+02:00")
        for delta in (timedelta(seconds=-1), timedelta(minutes=5), timedelta(days=1)):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                check_window(target, target + delta)
        check_window(target, target)
        check_window(target, target + timedelta(minutes=4))

    def test_ambiguous_time_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_time("2026-10-19T15:30:00")


if __name__ == "__main__":
    unittest.main()
