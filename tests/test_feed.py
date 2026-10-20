from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from contextlib import redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import generate_feed as feed
from mensa import Menu, MenuUnavailable


ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 10, 15)
MENU = Menu(DAY, ("Main dish", "Vegetarian dish", "Soup"),
            ("Potatoes", "Rice", "Pasta", "Cauliflower"))
CONFIG = {
    "enabled": True,
    "title": "Lunch",
    "description": "Lunch invitations.",
    "message": "🍽️ <Lunch> & \"tea\"? React with ✅",
}


def items(config, day=DAY):
    return ET.fromstring(feed.build_feed(config, day, "https://example.org")).findall("channel/item")


class FeedTests(unittest.TestCase):
    def setUp(self):
        # CLI tests must never depend on the network or the wall-clock menu.
        fetch = patch("generate_feed.fetch_menu",
                      side_effect=lambda day: Menu(day, MENU.mains, MENU.sides))
        self.fetch_menu = fetch.start()
        self.addCleanup(fetch.stop)

    def test_enabled_feed_has_one_item_for_today(self):
        [item] = items(CONFIG)
        html = ET.fromstring('<div>' + item.findtext('description') + '</div>')
        self.assertEqual(html.findtext("h3"), CONFIG["message"])
        self.assertEqual([child.tag for child in html], ["h3", "details"])
        self.assertIn("2026-10-15", item.findtext("title"))
        self.assertEqual(item.findtext("guid"), "2026-10-15")
        self.assertEqual(parsedate_to_datetime(item.findtext("pubDate")).date(), DAY)

    def test_disabled_feed_is_empty(self):
        self.assertEqual(items(dict(CONFIG, enabled=False)), [])

    def test_content_changes_keep_the_same_daily_identity(self):
        # A recovered menu or wording edit must not become another invitation.
        original = items(CONFIG)[0]
        for menu in (None, MENU):
            rss = feed.build_feed(dict(CONFIG, message="Updated invitation"), DAY,
                                  "https://example.org", menu=menu)
            updated = ET.fromstring(rss).find("channel/item")
            self.assertEqual(updated.findtext("guid"), original.findtext("guid"))
            self.assertEqual(updated.findtext("pubDate"), original.findtext("pubDate"))
            [json_item] = json.loads(feed.build_json_feed(rss))["items"]
            self.assertEqual(json_item["id"], DAY.isoformat())

    def test_mensa_message_has_no_link(self):
        config = dict(CONFIG, message='🍽️ Join the Mensa Train @ 12:30? 🚂')
        [item] = items(config)
        html = ET.fromstring('<div>' + item.findtext('description') + '</div>')
        self.assertIsNone(html.find('.//a'))
        self.assertEqual(html.findtext('h3'), config['message'])
        self.assertIsNone(item.find('link'))
        self.assertEqual(item.findtext('title'), config['message'] + ' — 2026-10-15')
        self.assertEqual(item.findtext('guid'), DAY.isoformat())

    def test_literal_html_in_message_stays_text(self):
        config = dict(CONFIG, message='Mensa <script> & <b>food</b>')
        [item] = items(config)
        html = ET.fromstring('<div>' + item.findtext('description') + '</div>')
        self.assertIsNone(html.find('.//script'))
        self.assertIsNone(html.find('.//b'))
        self.assertEqual(html.findtext('h3'), config['message'])

    def test_cli_disabled_mode_does_not_fetch_or_enable_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            original = json.dumps(dict(CONFIG, enabled=False))
            config_path.write_text(original, encoding="utf-8")
            output = Path(tmp) / "public"
            feed.main([str(output), "--config", str(config_path)])
            self.fetch_menu.assert_not_called()
            self.assertEqual(config_path.read_text(encoding="utf-8"), original)
            self.assertEqual(ET.parse(output / "feed.xml").findall("channel/item"), [])
            self.assertEqual(json.loads((output / "feed.json").read_text())["items"], [])

    def test_cli_reruns_keep_one_daily_item(self):
        with tempfile.TemporaryDirectory() as tmp, patch("generate_feed.berlin_today", return_value=DAY):
            config_path = Path(tmp) / "config.json"
            config_path.write_text(json.dumps(CONFIG), encoding="utf-8")
            output = Path(tmp) / "public"
            results = []
            for _ in range(2):
                feed.main([str(output), "--config", str(config_path)])
                [xml_item] = ET.parse(output / "feed.xml").findall("channel/item")
                [json_item] = json.loads((output / "feed.json").read_text())["items"]
                self.assertEqual(xml_item.findtext("guid"), DAY.isoformat())
                self.assertEqual(json_item["id"], DAY.isoformat())
                results.append(((output / "feed.xml").read_bytes(),
                                (output / "feed.json").read_bytes()))
            self.assertEqual(results[0], results[1])

    def test_cli_rejects_unique_test_ids_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stderr(StringIO()):
            output = Path(tmp) / "public"
            with self.assertRaises(SystemExit) as error:
                feed.main([str(output), "--test-id", "another-message"])
            self.assertEqual(error.exception.code, 2)
            self.assertFalse(output.exists())
            self.fetch_menu.assert_not_called()

    def test_json_feed_preserves_nested_menu_labels_without_duplicates(self):
        rss = feed.build_feed(CONFIG, DAY, "https://example.org", menu=MENU)
        data = json.loads(feed.build_json_feed(rss))
        [item] = data["items"]
        self.assertEqual(data["version"], "https://jsonfeed.org/version/1.1")
        self.assertEqual(item["id"], DAY.isoformat())
        self.assertNotIn("summary", item)
        html = ET.fromstring("<div>" + item["content_html"] + "</div>")
        [menu] = html.findall("details")
        [sides] = menu.findall("details")
        self.assertEqual(menu.findtext("summary"), "Mensa X Menu")
        self.assertEqual(sides.findtext("summary"), "Beilagen & Dessert")
        self.assertEqual(len(menu.findall("ul/li")), 3)
        self.assertEqual(len(sides.findall("ul/li")), 4)
        self.assertNotIn("open", menu.attrib)
        self.assertNotIn("open", sides.attrib)
        text = "".join(html.itertext())
        self.assertEqual(text.count("Mensa X Menu"), 1)
        self.assertEqual(text.count("Beilagen & Dessert"), 1)
        self.assertNotIn("Details", text)
        self.assertIsNone(html.find(".//a"))
        # Check the fallback without relying on block/list layout. This verifies
        # explicit breaks, not the rendering of a particular Element version.
        for line_break in html.iter("br"):
            line_break.text = "\n"
        # Ignore the zero-width word joiners that protect these breaks on iOS.
        fallback = "".join(html.itertext()).replace("\u2060", "")
        self.assertIn("Mensa X Menu\n\n" + MENU.mains[0], fallback)
        self.assertIn("Beilagen & Dessert\n\n" + MENU.sides[0], fallback)
        lines = [line.strip() for line in fallback.splitlines() if line.strip()]
        self.assertEqual(lines, [CONFIG["message"], "Mensa X Menu", *MENU.mains,
                                 "Beilagen & Dessert", *MENU.sides])

    def test_json_feed_matches_rss_ids_dates_and_content(self):
        for day in (DAY, date(2026, 10, 16)):
            with self.subTest(day=day):
                rss = feed.build_feed(CONFIG, day, "https://example.org",
                                      menu=Menu(day, MENU.mains, MENU.sides))
                xml_item = ET.fromstring(rss).find("channel/item")
                data = json.loads(feed.build_json_feed(rss))
                [item] = data["items"]
                self.assertEqual(data["title"], CONFIG["title"])
                self.assertEqual(data["description"], CONFIG["description"])
                self.assertEqual(data["home_page_url"], "https://example.org")
                self.assertEqual(item["id"], day.isoformat())
                self.assertEqual(item["id"], xml_item.findtext("guid"))
                self.assertEqual(item["title"], xml_item.findtext("title"))
                self.assertEqual(item["content_html"], xml_item.findtext("description"))
                self.assertEqual(datetime.fromisoformat(item["date_published"]),
                                 parsedate_to_datetime(xml_item.findtext("pubDate")))
                self.assertIn("<summary>Beilagen &amp; Dessert</summary>", item["content_html"])

    def test_yesterdays_menu_cannot_be_used(self):
        with self.assertRaisesRegex(ValueError, "menu date"):
            feed.build_feed(CONFIG, date(2026, 10, 16), "https://example.org", menu=MENU)

    def test_dish_names_are_escaped_and_empty_sides_are_explained(self):
        menu = Menu(DAY, ('Soup <b>special</b> & bread',), ())
        rss = feed.build_feed(CONFIG, DAY, 'https://example.org', menu=menu)
        html = ET.fromstring('<div>' + ET.fromstring(rss).findtext('channel/item/description') + '</div>')
        self.assertEqual(html.findtext('details/ul/li'), menu.mains[0])
        self.assertIsNone(html.find('.//b'))
        self.assertEqual(html.findtext('details/details/p'), 'No side dishes listed for today.')

    def test_fetch_failure_still_publishes_invitation_with_unavailable_notice(self):
        self.fetch_menu.side_effect = MenuUnavailable('site offline')
        with (tempfile.TemporaryDirectory() as tmp,
              patch("generate_feed.berlin_today", return_value=DAY),
              self.assertLogs(level='WARNING') as logs):
            config_path = Path(tmp) / 'config.json'
            config_path.write_text(json.dumps(CONFIG), encoding='utf-8')
            feed.main([tmp, '--config', str(config_path)])
            [item] = json.loads((Path(tmp) / 'feed.json').read_text())['items']
        self.assertEqual(item['id'], DAY.isoformat())
        html = ET.fromstring('<div>' + item['content_html'] + '</div>')
        self.assertEqual(html.findtext('h3'), CONFIG['message'])
        self.assertIn("Today's menu is currently unavailable.", item['content_html'])
        self.assertNotIn('<li>', item['content_html'])
        self.assertIn('site offline', logs.output[0])

    def test_berlin_date_near_midnight_and_across_dst(self):
        for utc, expected in (
            ('2026-01-15T22:30:00', date(2026, 1, 15)),
            ('2026-07-15T22:30:00', date(2026, 7, 16)),
            ('2026-03-28T22:30:00', date(2026, 3, 28)),
            ('2026-03-29T22:30:00', date(2026, 3, 30)),
            ('2026-10-24T22:30:00', date(2026, 10, 25)),
            ('2026-10-25T22:30:00', date(2026, 10, 25)),
        ):
            with self.subTest(utc=utc):
                self.assertEqual(feed.berlin_today(datetime.fromisoformat(utc).replace(tzinfo=timezone.utc)),
                                 expected)

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
