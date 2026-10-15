from datetime import date
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import generate_feed as feed


ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 10, 15)
CONFIG = {
    "enabled": True,
    "title": "Lunch",
    "description": "Lunch invitations.",
    "message": "🍽️ <Lunch> & \"tea\"? React with ✅",
}


def items(config, day=DAY):
    return ET.fromstring(feed.build_feed(config, day, "https://example.org")).findall("channel/item")


class FeedTests(unittest.TestCase):
    def test_enabled_feed_has_one_item_for_today(self):
        [item] = items(CONFIG)
        self.assertEqual(item.findtext("description"), CONFIG["message"])
        self.assertIn("2026-10-15", item.findtext("title"))
        self.assertEqual(item.findtext("guid"), "2026-10-15")
        self.assertEqual(parsedate_to_datetime(item.findtext("pubDate")).date(), DAY)

    def test_disabled_feed_is_empty(self):
        self.assertEqual(items(dict(CONFIG, enabled=False)), [])

    def test_reruns_are_identical_and_days_are_distinct(self):
        self.assertEqual(feed.build_feed(CONFIG, DAY, "x"), feed.build_feed(CONFIG, DAY, "x"))
        other = items(CONFIG, date(2026, 10, 16))[0].findtext("guid")
        self.assertNotEqual(other, items(CONFIG)[0].findtext("guid"))

    def test_cli_writes_feed_from_project_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed.main([tmp, "--config", str(ROOT / "config.json")])
            root = ET.parse(Path(tmp) / "feed.xml").getroot()
        self.assertEqual(root.get("version"), "2.0")
        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(root.findtext("channel/title"), config["title"])


if __name__ == "__main__":
    unittest.main()
