#!/usr/bin/env python3
"""Write an RSS feed containing today's message, for an RSS bot in an Element room."""

import argparse
from datetime import date, datetime, time, timezone
from email.utils import format_datetime
import json
from pathlib import Path
import xml.etree.ElementTree as ET


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
        ET.SubElement(item, "description").text = config["message"]
        # Daily entries keep a stable date ID. Tests use the workflow run ID so
        # a new manual run is distinct and retries reuse the same identifier.
        ET.SubElement(item, "guid", isPermaLink="false").text = (
            f"test-{test_id}" if test_id is not None else today.isoformat())
        ET.SubElement(item, "pubDate").text = format_datetime(
            datetime.now(timezone.utc) if test_id is not None
            else datetime.combine(today, time(), timezone.utc))
    ET.indent(rss)
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True) + b"\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?", default=Path("public"))
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--link", default="https://github.com", help="channel link")
    parser.add_argument("--test-id", help="Generate a labeled test even when disabled; use a unique run ID")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "feed.xml").write_bytes(
        build_feed(config, date.today(), args.link, test_id=args.test_id))


if __name__ == "__main__":
    main()
