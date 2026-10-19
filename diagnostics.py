"""Publish a separate test feed while preserving the current lunch feeds."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import ssl
import sys
import time
from urllib.request import Request, urlopen
from uuid import uuid4
import xml.etree.ElementTree as ET

from generate_feed import build_json_feed
from scheduled_test import parse_time


BASE_URL = "https://maxsiska.github.io/element-feed"
PRODUCTION = ("feed.json", "feed.xml")
DIAGNOSTIC = "diagnostics/feed.json"


def read_public(path):
    # A new query key avoids preserving a stale CDN copy during an experiment.
    request = Request(f"{BASE_URL}/{path}?diagnostic_check={uuid4().hex}",
                      headers={"Cache-Control": "no-cache", "User-Agent": "element-feed/1.0"})
    context = ssl.create_default_context()
    if sys.platform == "darwin" and Path("/etc/ssl/cert.pem").exists():
        context.load_verify_locations("/etc/ssl/cert.pem")
    with urlopen(request, context=context, timeout=15) as response:
        return response.read()


def validate_diagnostic(source):
    feed = json.loads(source.read_bytes())
    if (feed.get("version") != "https://jsonfeed.org/version/1.1"
            or not feed.get("title") or not isinstance(feed.get("items"), list)
            or not feed["items"]):
        raise ValueError("The diagnostic feed must contain a setup baseline.")
    ids = [item.get("id", "") for item in feed["items"]]
    if len(set(ids)) != len(ids) or any(not value.startswith("diagnostic:") for value in ids):
        raise ValueError("Diagnostic entries require unique diagnostic: IDs.")
    return feed


def bundle(output, source, now=None):
    feed = validate_diagnostic(source)
    now = now or datetime.now(timezone.utc)
    # Keep future appointments out of every deployment, including ordinary
    # lunch publications and manual previews of this diagnostic feed.
    feed["items"] = [item for item in feed["items"]
                     if parse_time(item["date_published"]) <= now]
    if not feed["items"]:
        raise ValueError("No published diagnostic baseline is available yet.")
    destination = output / DIAGNOSTIC
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")


def prepare(output, source):
    validate_diagnostic(source)
    # Validate both live formats before writing anything. Never generate a lunch
    # invitation as a side effect of a diagnostic publication.
    current = {path: read_public(path) for path in PRODUCTION}
    if json.loads(current["feed.json"]) != json.loads(build_json_feed(current["feed.xml"])):
        raise ValueError("Live lunch feeds disagree; refusing to replace either one.")
    output.mkdir(parents=True, exist_ok=True)
    for path, body in current.items():
        (output / path).write_bytes(body)
    bundle(output, source)
    print("Prepared the diagnostic feed; preserved both lunch feeds byte for byte.")


def guard(output):
    for path in PRODUCTION:
        if read_public(path) != (output / path).read_bytes():
            raise ValueError("The lunch feed changed during preparation; rerun this job.")


def verify(output, timeout=180):
    expected = {path: (output / path).read_bytes() for path in (*PRODUCTION, DIAGNOSTIC)}
    deadline = time.monotonic() + timeout
    while True:
        try:
            if all(read_public(path) == body for path, body in expected.items()):
                print("Verified the diagnostic feed and unchanged lunch feeds.")
                return
            detail = "Public files do not yet match the prepared files."
        except (OSError, ValueError) as exc:
            detail = str(exc)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"Diagnostic publication not verified: {detail}")
        print(f"{detail} Waiting for Pages.", flush=True)
        time.sleep(min(15, remaining))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "bundle", "guard", "verify"))
    parser.add_argument("--output", type=Path, default=Path("public"))
    parser.add_argument("--source", type=Path, default=Path(DIAGNOSTIC))
    args = parser.parse_args(argv)
    try:
        if args.command in ("prepare", "bundle"):
            globals()[args.command](args.output, args.source)
        else:
            globals()[args.command](args.output)
    except (OSError, ValueError, RuntimeError, KeyError, ET.ParseError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
