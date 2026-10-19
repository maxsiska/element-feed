"""Publish an explicitly requested one-off test at a fixed, timezone-aware time."""

import argparse
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html import escape
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from generate_feed import build_json_feed


def parse_time(value):
    target = datetime.fromisoformat(value)
    if target.tzinfo is None:
        raise ValueError("The test time must include its UTC offset.")
    return target.astimezone(timezone.utc)


def check_window(target, now):
    if not target <= now < target + timedelta(minutes=5):
        raise ValueError("Outside the one-off test's five-minute publication window.")


def wait_until(target):
    now = datetime.now(timezone.utc)
    if target - now > timedelta(minutes=20):
        raise ValueError("Arm this one-off test no more than 20 minutes ahead.")
    while now < target:
        remaining = (target - now).total_seconds()
        print(f"Waiting for {target.isoformat()}: {remaining:.0f} seconds remaining", flush=True)
        time.sleep(min(30, remaining))
        now = datetime.now(timezone.utc)
    check_window(target, now)


def build_test(config, target, message, link):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    for name, value in (("title", config["title"]), ("description", config["description"]),
                        ("link", link)):
        ET.SubElement(channel, name).text = value
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = message
    ET.SubElement(item, "description").text = escape(message)
    # A rerun of this appointment cannot manufacture another test entry ID.
    ET.SubElement(item, "guid", isPermaLink="false").text = "scheduled-test:" + target.isoformat()
    ET.SubElement(item, "pubDate").text = format_datetime(target)
    ET.indent(rss)
    xml = ET.tostring(rss, encoding="utf-8", xml_declaration=True) + b"\n"
    return xml, build_json_feed(xml)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "guard"))
    parser.add_argument("--at", required=True)
    parser.add_argument("--message", default="15:30 test")
    parser.add_argument("--link", default="https://github.com/maxsiska/element-feed")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--output", type=Path, default=Path("public"))
    args = parser.parse_args(argv)
    try:
        target = parse_time(args.at)
        if args.command == "guard":
            check_window(target, datetime.now(timezone.utc))
            return 0
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if not config["enabled"]:
            raise ValueError("Posting is disabled in config.json.")
        wait_until(target)
        xml, data = build_test(config, target, args.message, args.link)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "feed.xml").write_bytes(xml)
        (args.output / "feed.json").write_bytes(data)
        print(f"Prepared one-off message: {args.message}")
    except (OSError, ValueError) as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
