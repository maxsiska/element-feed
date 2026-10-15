#!/usr/bin/env python3
"""Write an RSS feed containing today's message, for an RSS bot in an Element room."""

import argparse
from datetime import date, datetime, time, timezone
from email.utils import format_datetime
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def build_feed(config, today, link):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = config["title"]
    ET.SubElement(channel, "link").text = link
    ET.SubElement(channel, "description").text = config["description"]
    if config["enabled"]:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = f"{config['message']} — {today.isoformat()}"
        ET.SubElement(item, "description").text = config["message"]
        # One item per date: reruns on the same day produce an identical feed,
        # so the bot does not post the message twice.
        ET.SubElement(item, "guid", isPermaLink="false").text = today.isoformat()
        ET.SubElement(item, "pubDate").text = format_datetime(
            datetime.combine(today, time(), timezone.utc))
    ET.indent(rss)
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True) + b"\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?", default=Path("public"))
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--link", default="https://github.com", help="channel link")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "feed.xml").write_bytes(build_feed(config, date.today(), args.link))


if __name__ == "__main__":
    main()
