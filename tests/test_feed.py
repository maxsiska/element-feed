from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
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
        self.assertEqual(html.text.rstrip(), CONFIG["message"])
        self.assertIn("2026-10-15", item.findtext("title"))
        self.assertEqual(item.findtext("guid"), "2026-10-15")
        self.assertEqual(parsedate_to_datetime(item.findtext("pubDate")).date(), DAY)

    def test_disabled_feed_is_empty(self):
        self.assertEqual(items(dict(CONFIG, enabled=False)), [])

    def test_test_message_works_while_disabled_without_changing_config(self):
        config = dict(CONFIG, enabled=False)
        xml = feed.build_feed(config, DAY, "https://example.org", test_id="123")
        item = ET.fromstring(xml).find("channel/item")
        self.assertEqual(item.findtext("title"), CONFIG["message"] + " — 2026-10-15")
        self.assertEqual(item.findtext("description"), items(CONFIG)[0].findtext("description"))
        self.assertIn(CONFIG["message"], unescape(item.findtext("description")))
        self.assertFalse(config["enabled"])
        self.assertEqual(config["message"], CONFIG["message"])
        self.assertIsNotNone(parsedate_to_datetime(item.findtext("pubDate")).utcoffset())

    def test_test_ids_are_separate_from_daily_ids_and_repeatable(self):
        def guid(run_id):
            xml = feed.build_feed(CONFIG, DAY, "https://example.org", test_id=run_id)
            return ET.fromstring(xml).findtext("channel/item/guid")
        self.assertEqual(guid("123"), guid("123"))
        self.assertNotEqual(guid("123"), guid("124"))
        self.assertNotEqual(guid("123"), items(CONFIG)[0].findtext("guid"))

    def test_mensa_message_has_no_link(self):
        config = dict(CONFIG, message='🍽️ Join the Mensa Train @ 12:30? 🚂')
        [item] = items(config)
        html = ET.fromstring('<div>' + item.findtext('description') + '</div>')
        self.assertIsNone(html.find('.//a'))
        self.assertEqual(html.text.rstrip(), config['message'])
        self.assertIsNone(item.find('link'))
        self.assertEqual(item.findtext('title'), config['message'] + ' — 2026-10-15')
        self.assertEqual(item.findtext('guid'), DAY.isoformat())

    def test_literal_html_in_message_stays_text(self):
        config = dict(CONFIG, message='Mensa <script> & <b>food</b>')
        [item] = items(config)
        html = ET.fromstring('<div>' + item.findtext('description') + '</div>')
        self.assertIsNone(html.find('.//script'))
        self.assertIsNone(html.find('.//b'))
        self.assertEqual(html.text.rstrip(), config['message'])

    def test_test_message_has_no_link(self):
        config = dict(CONFIG, enabled=False, message='🍽️ Join the Mensa Train @ 12:30? 🚂')
        xml = feed.build_feed(config, DAY, 'https://example.org', test_id='menu-test')
        item = ET.fromstring(xml).find('channel/item')
        html = ET.fromstring('<div>' + item.findtext('description') + '</div>')
        self.assertEqual(html.text.rstrip(), config['message'])
        self.assertIsNone(html.find('.//a'))
        self.assertIsNone(item.find('link'))
        self.assertEqual(item.findtext('guid'), 'test-menu-test')

    def test_cli_test_mode_does_not_enable_recurring_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            original = json.dumps(dict(CONFIG, enabled=False))
            config_path.write_text(original, encoding="utf-8")
            output = Path(tmp) / "public"
            feed.main([str(output), "--config", str(config_path), "--test-id", "456"])
            self.assertEqual(ET.parse(output / "feed.xml").findtext("channel/item/guid"), "test-456")
            json_feed = json.loads((output / "feed.json").read_text(encoding="utf-8"))
            self.assertEqual(json_feed["items"][0]["id"], "test-456")
            self.assertEqual(config_path.read_text(encoding="utf-8"), original)
            self.fetch_menu.reset_mock()
            feed.main([str(output), "--config", str(config_path)])
            self.fetch_menu.assert_not_called()
            self.assertEqual(ET.parse(output / "feed.xml").findall("channel/item"), [])
            self.assertEqual(json.loads((output / "feed.json").read_text())["items"], [])

    def test_json_feed_preserves_nested_menu_labels_without_duplicates(self):
        rss = feed.build_feed(dict(CONFIG, enabled=False), DAY, "https://example.org",
                              test_id="789", menu=MENU)
        data = json.loads(feed.build_json_feed(rss))
        [item] = data["items"]
        self.assertEqual(data["version"], "https://jsonfeed.org/version/1.1")
        self.assertEqual(item["id"], "test-789")
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
        lines = [line.strip() for line in "".join(html.itertext()).splitlines() if line.strip()]
        self.assertEqual(lines, [CONFIG["message"], "Mensa X Menu", *MENU.mains,
                                 "Beilagen & Dessert", *MENU.sides])

    def test_json_feed_matches_rss_ids_dates_and_content(self):
        for day, test_id in ((DAY, None), (date(2026, 10, 16), None), (DAY, "123"), (DAY, "124")):
            with self.subTest(day=day, test_id=test_id):
                rss = feed.build_feed(CONFIG, day, "https://example.org", test_id=test_id,
                                      menu=Menu(day, MENU.mains, MENU.sides))
                xml_item = ET.fromstring(rss).find("channel/item")
                data = json.loads(feed.build_json_feed(rss))
                [item] = data["items"]
                self.assertEqual(data["title"], CONFIG["title"])
                self.assertEqual(data["description"], CONFIG["description"])
                self.assertEqual(data["home_page_url"], "https://example.org")
                self.assertEqual(item["id"], f"test-{test_id}" if test_id else day.isoformat())
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
        with tempfile.TemporaryDirectory() as tmp, self.assertLogs(level='WARNING') as logs:
            feed.main([tmp, '--config', str(ROOT / 'config.json'), '--test-id', 'offline'])
            [item] = json.loads((Path(tmp) / 'feed.json').read_text())['items']
        self.assertEqual(item['id'], 'test-offline')
        html = ET.fromstring('<div>' + item['content_html'] + '</div>')
        config = json.loads((ROOT / 'config.json').read_text())
        self.assertEqual(html.text.rstrip(), config['message'])
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
