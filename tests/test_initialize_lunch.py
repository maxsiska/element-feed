from datetime import date, datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import generate_feed
import initialize_lunch
from mensa import Menu
from publication import has_today


ROOT = Path(__file__).resolve().parents[1]


class InitializeLunchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.output = Path(tmp.name) / "public"
        self.static = ROOT / "static"

    def live(self, path):
        if path in initialize_lunch.LUNCH:
            raise HTTPError(path, 404, "Not found", {}, None)
        return (self.static / path).read_bytes()

    def test_baseline_keeps_menu_and_does_not_republish_retired_entries(self):
        day = date(2026, 10, 19)
        with (patch("initialize_lunch.read_public", side_effect=self.live),
              patch("generate_feed.berlin_today", return_value=day),
              patch("generate_feed.fetch_menu", return_value=Menu(day, ("Main",), ("Side",)))):
            initialize_lunch.prepare(self.output, self.static)
        feed = json.loads((self.output / "lunch/feed.json").read_bytes())
        self.assertEqual(feed["items"][0]["id"], "lunch-setup:2026-10-19")
        self.assertIn("Join the Mensa Train @ 12:30?", feed["items"][0]["content_html"])
        self.assertIn("<li>Main<br /></li>", feed["items"][0]["content_html"])
        self.assertIn("<li>Side<br /></li>", feed["items"][0]["content_html"])
        self.assertFalse(has_today(feed, datetime.fromisoformat("2026-10-19T11:20:00+02:00")))
        self.assertEqual(feed, json.loads(generate_feed.build_json_feed(
            (self.output / "lunch/feed.xml").read_bytes())))
        for path in initialize_lunch.RETIRED:
            self.assertEqual((self.output / path).read_bytes(), (self.static / path).read_bytes())

    def test_existing_feed_and_network_failure_cannot_reset_a_subscription(self):
        for response in (b"existing lunch feed", OSError("offline"),
                         HTTPError("url", 503, "Unavailable", {}, None)):
            with (self.subTest(response=response),
                  patch("initialize_lunch.read_public", side_effect=(
                      response if isinstance(response, Exception) else None), return_value=response),
                  self.assertRaises((OSError, RuntimeError))):
                initialize_lunch.prepare(self.output, self.static)
            self.assertFalse(self.output.exists())

    def test_changed_retired_feed_aborts_before_creating_baseline(self):
        def changed(path):
            return b"changed" if path == "feed.json" else self.live(path)
        with (patch("initialize_lunch.read_public", side_effect=changed),
              self.assertRaisesRegex(RuntimeError, "retired feed changed")):
            initialize_lunch.prepare(self.output, self.static)
        self.assertFalse(self.output.exists())

    def test_daily_update_changes_only_replacement_feed(self):
        day = date(2026, 10, 20)
        with (patch("generate_feed.berlin_today", return_value=day),
              patch("generate_feed.fetch_menu", return_value=Menu(day, ("Main",), ()))):
            generate_feed.main([str(self.output / "lunch"), "--config", str(ROOT / "config.json")])
        shutil.copytree(self.static, self.output, dirs_exist_ok=True)
        feed = json.loads((self.output / "lunch/feed.json").read_bytes())
        self.assertEqual(feed["items"][0]["id"], "2026-10-20")
        for path in initialize_lunch.RETIRED:
            self.assertEqual((self.output / path).read_bytes(), (self.static / path).read_bytes())


if __name__ == "__main__":
    unittest.main()
