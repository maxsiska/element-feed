from datetime import date
from email.utils import parsedate_to_datetime
from html import unescape
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
        self.assertEqual(unescape(item.findtext("description")), CONFIG["message"])
        self.assertIn("2026-10-15", item.findtext("title"))
        self.assertEqual(item.findtext("guid"), "2026-10-15")
        self.assertEqual(parsedate_to_datetime(item.findtext("pubDate")).date(), DAY)

    def test_disabled_feed_is_empty(self):
        self.assertEqual(items(dict(CONFIG, enabled=False)), [])

    def test_test_message_works_while_disabled_without_changing_config(self):
        config = dict(CONFIG, enabled=False)
        xml = feed.build_feed(config, DAY, "https://example.org", test_id="123")
        item = ET.fromstring(xml).find("channel/item")
        self.assertIn("TEST — not a real invitation", item.findtext("title"))
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

    def test_mensa_link_is_in_description_and_item_link_but_not_title(self):
        config = dict(CONFIG, message='🍽️ Mensa at 12:30? 🚂',
                      menu_url='https://example.org/menu?x=1&y="two"')
        [item] = items(config)
        html = ET.fromstring('<div>' + item.findtext('description') + '</div>')
        self.assertEqual(html.find('a').text, 'Mensa')
        self.assertEqual(html.find('a').get('href'), config['menu_url'])
        self.assertEqual(''.join(html.itertext()), config['message'])
        self.assertEqual(item.findtext('link'), config['menu_url'])
        self.assertEqual(item.findtext('title'), config['message'] + ' — 2026-10-15')
        self.assertEqual(item.findtext('guid'), DAY.isoformat())

    def test_literal_html_in_message_stays_text(self):
        config = dict(CONFIG, message='Mensa <script> & <b>food</b>',
                      menu_url='https://example.org/menu')
        [item] = items(config)
        html = ET.fromstring('<div>' + item.findtext('description') + '</div>')
        self.assertEqual([child.tag for child in html], ['a'])
        self.assertEqual(''.join(html.itertext()), config['message'])

    def test_test_prefix_keeps_mensa_link(self):
        config = dict(CONFIG, enabled=False, message='🍽️ Mensa at 12:30? 🚂',
                      menu_url='https://example.org/menu')
        xml = feed.build_feed(config, DAY, 'https://example.org', test_id='linked-test')
        item = ET.fromstring(xml).find('channel/item')
        html = ET.fromstring('<div>' + item.findtext('description') + '</div>')
        self.assertIn('TEST — not a real invitation', html.text)
        self.assertEqual(html.find('a').text, 'Mensa')
        self.assertEqual(item.findtext('guid'), 'test-linked-test')

    def test_missing_mensa_word_keeps_message_and_provides_item_link(self):
        config = dict(CONFIG, menu_url='https://example.org/menu')
        [item] = items(config)
        self.assertEqual(unescape(item.findtext('description')), config['message'])
        self.assertEqual(item.findtext('link'), config['menu_url'])

    def test_menu_link_rejects_non_web_schemes(self):
        for url in ('javascript:alert(1)', '/relative/menu', 'file:///menu.html'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                items(dict(CONFIG, menu_url=url))

    def test_cli_test_mode_does_not_enable_recurring_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            original = json.dumps(dict(CONFIG, enabled=False))
            config_path.write_text(original, encoding="utf-8")
            output = Path(tmp) / "public"
            feed.main([str(output), "--config", str(config_path), "--test-id", "456"])
            self.assertEqual(ET.parse(output / "feed.xml").findtext("channel/item/guid"), "test-456")
            self.assertEqual(config_path.read_text(encoding="utf-8"), original)
            feed.main([str(output), "--config", str(config_path)])
            self.assertEqual(ET.parse(output / "feed.xml").findall("channel/item"), [])

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
