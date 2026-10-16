#!/usr/bin/env python3
"""Write RSS and JSON feeds containing today's message for an Element feed bot."""

import argparse
from datetime import date, datetime, time, timezone
from email.utils import format_datetime, parsedate_to_datetime
from html import escape
import json
from pathlib import Path
import xml.etree.ElementTree as ET


SAMPLE_MAIN_DISHES = (
    "Alaska-Seelachs-Filet in Backteig mit Remouladensoße",
    "Gemüsepuffer mit Sauerrahm-Dip",
    "Indischer Eintopf",
)
SAMPLE_SIDE_DISHES = (
    "Bratkartoffeln mit frischen Zwiebeln",
    "Djuvec-Reis",
    "Penne Rigate",
    "Blumenkohl",
)


def dish_list(dishes):
    return "<ul>" + "".join(f"<li>{escape(dish)}</li>" for dish in dishes) + "</ul>"


def build_feed(config, today, link, test_id=None):
    if test_id is not None:
        config = dict(config, enabled=True,
                      message="🧪 TEST — not a real invitation. " + config["message"])
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = config["title"]
    ET.SubElement(channel, "link").text = link
    ET.SubElement(channel, "description").text = config["description"]
    if config["enabled"]:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = f"{config['message']} — {today.isoformat()}"
        # RSS descriptions contain HTML encoded as XML text. Escape the plain
        # message first, then add the test menus (keep the title plain).
        description = escape(config["message"])
        if test_id is not None:
            description += (
                "\n<details><summary>Mensa X Menu</summary>"
                f"{dish_list(SAMPLE_MAIN_DISHES)}"
                "<details><summary>Beilagen</summary>"
                f"{dish_list(SAMPLE_SIDE_DISHES)}"
                "</details></details>"
            )
        ET.SubElement(item, "description").text = description
        # Daily entries keep a stable date ID. Tests use the workflow run ID so
        # a new manual run is distinct and retries reuse the same identifier.
        ET.SubElement(item, "guid", isPermaLink="false").text = (
            f"test-{test_id}" if test_id is not None else today.isoformat())
        ET.SubElement(item, "pubDate").text = format_datetime(
            datetime.now(timezone.utc) if test_id is not None
            else datetime.combine(today, time(), timezone.utc))
    ET.indent(rss)
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True) + b"\n"


def build_json_feed(rss):
    """Mirror our RSS as JSON Feed so Coffee Bot preserves the <summary> labels."""
    channel = ET.fromstring(rss).find("channel")
    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": channel.findtext("title"),
        "home_page_url": channel.findtext("link"),
        "description": channel.findtext("description"),
        "items": [
            {
                "id": item.findtext("guid"),
                "title": item.findtext("title"),
                # Omit JSON Feed's plain-text "summary": maubot/rss prefers it
                # over content_html when populating its $summary variable.
                "content_html": item.findtext("description"),
                "date_published": parsedate_to_datetime(item.findtext("pubDate")).isoformat(),
            }
            for item in channel.findall("item")
        ],
    }
    return (json.dumps(feed, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?", default=Path("public"))
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--link", default="https://github.com", help="channel link")
    parser.add_argument("--test-id", help="Generate a labeled test even when disabled; use a unique run ID")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    rss = build_feed(config, date.today(), args.link, test_id=args.test_id)
    (args.output / "feed.xml").write_bytes(rss)
    (args.output / "feed.json").write_bytes(build_json_feed(rss))


if __name__ == "__main__":
    main()
