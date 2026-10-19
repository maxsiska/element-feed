"""Create the replacement lunch feed once, without changing existing feeds."""

import argparse
import json
from pathlib import Path
import shutil
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

from diagnostics import BASE_URL, read_public
from generate_feed import build_json_feed, main as generate
from publication import verify_feed


LUNCH = ("lunch/feed.json", "lunch/feed.xml")
RETIRED = ("feed.json", "feed.xml", "diagnostics/feed.json")


def guard(static=Path("static")):
    # Only an actual 404 permits initialization. Outages and existing feeds
    # must never be mistaken for permission to replace a subscribed feed.
    for path in LUNCH:
        try:
            read_public(path)
        except HTTPError as exc:
            exc.close()
            if exc.code != 404:
                raise
        else:
            raise RuntimeError("The replacement feed already exists; initialization refused.")
    for path in RETIRED:
        if read_public(path) != (static / path).read_bytes():
            raise RuntimeError("A retired feed changed; refresh its snapshot before initializing.")


def prepare(output=Path("public"), static=Path("static")):
    guard(static)
    generate([str(output / "lunch"), "--link", "https://github.com/maxsiska/element-feed"])
    xml_path = output / "lunch/feed.xml"
    root = ET.fromstring(xml_path.read_bytes())
    items = root.findall("channel/item")
    if len(items) != 1:
        raise RuntimeError("Enable the lunch feed before creating its subscription baseline.")
    [item] = items
    # A subscription baseline is distinct from the next normal daily entry.
    # Coffee Bot records existing entries when first subscribing a new URL.
    item.find("guid").text = "lunch-setup:" + item.findtext("guid")
    rss = ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"
    xml_path.write_bytes(rss)
    (output / "lunch/feed.json").write_bytes(build_json_feed(rss))
    shutil.copytree(static, output, dirs_exist_ok=True)


def verify(output=Path("public")):
    for path in ("lunch/feed.json", *RETIRED):
        if path.endswith(".json"):
            verify_feed(f"{BASE_URL}/{path}", json.loads((output / path).read_bytes()))
        elif read_public(path) != (output / path).read_bytes():
            raise RuntimeError(f"Public file differs: {path}")
    if read_public("lunch/feed.xml") != (output / "lunch/feed.xml").read_bytes():
        raise RuntimeError("Replacement RSS differs from the deployed file.")
    print("Verified the replacement lunch feed and unchanged retired feeds.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "guard", "verify"))
    args = parser.parse_args()
    globals()[args.command]()


if __name__ == "__main__":
    main()
