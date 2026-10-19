"""Gate lunch publications and verify the public feed after deployment."""

import argparse
from datetime import datetime, time, timezone
import json
import logging
import os
from pathlib import Path
import time as clock
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


BERLIN = ZoneInfo("Europe/Berlin")
WINDOW_START = time(11, 15)
WINDOW_END = time(12, 15)


def berlin_now():
    return datetime.now(timezone.utc).astimezone(BERLIN)


def read_feed(url):
    request = Request(url, headers={"User-Agent": "element-feed/1.0"})
    with urlopen(request, timeout=10) as response:
        feed = json.load(response)
    if not isinstance(feed, dict) or not isinstance(feed.get("items"), list):
        raise ValueError("Response is not a JSON Feed with an items list")
    return feed


def has_today(feed, now):
    if not feed:
        return False
    items = feed.get("items", [])
    # A test ID or a feed containing extra old entries is not today's feed.
    return (len(items) == 1 and isinstance(items[0], dict)
            and items[0].get("id") == now.astimezone(BERLIN).date().isoformat()
            and bool(items[0].get("content_html")))


def in_window(now):
    local = now.astimezone(BERLIN)
    return local.weekday() < 5 and WINDOW_START <= local.time() < WINDOW_END


def should_publish(config, live, now):
    local = now.astimezone(BERLIN)
    if not config["enabled"]:
        return (live is None or live.get("items") != []), "Posting is disabled; ensure the feed is empty."
    if has_today(live, local):
        return False, "Today's invitation is already published."
    if local.weekday() >= 5 or local.time() < WINDOW_START:
        return False, "Outside the weekday publication window (11:15–12:15 Berlin)."
    if local.time() >= WINDOW_END:
        raise RuntimeError("MISSED PUBLICATION: today's feed is absent after 12:15 Berlin; "
                           "refusing to publish a late lunch invitation.")
    return True, "Today's invitation is missing; publish it now."


def check_deployment_window(expected, now):
    if not expected["items"]:
        return  # Disabling an invitation is allowed at any time.
    if not in_window(now) or not has_today(expected, now):
        raise RuntimeError("Publication became too late or its date changed before deployment.")


def verify_feed(url, expected, timeout=180, interval=15):
    deadline = clock.monotonic() + timeout
    while True:
        try:
            if read_feed(url) == expected:
                return
            detail = "Public feed does not yet match the deployed feed."
        except (OSError, ValueError) as exc:
            detail = f"Cannot read the public feed: {exc}"
        remaining = deadline - clock.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"PUBLICATION NOT VERIFIED: {detail}")
        logging.warning("%s Retrying while Pages caches update.", detail)
        clock.sleep(min(interval, remaining))


def report(message):
    print(message)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as summary:
            summary.write(message + "\n\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "guard", "verify"))
    parser.add_argument("--feed-url")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--expected", type=Path, default=Path("public/feed.json"))
    args = parser.parse_args(argv)
    if args.command in ("plan", "verify") and not args.feed_url:
        parser.error("--feed-url is required for plan and verify")
    try:
        if args.command == "plan":
            config = json.loads(args.config.read_text(encoding="utf-8"))
            try:
                live = read_feed(args.feed_url)
            except (OSError, ValueError) as exc:
                logging.warning("Could not inspect the current feed: %s", exc)
                live = None
            publish, reason = should_publish(config, live, berlin_now())
            report(reason)
            if output := os.environ.get("GITHUB_OUTPUT"):
                with open(output, "a", encoding="utf-8") as stream:
                    stream.write(f"publish={str(publish).lower()}\n")
        else:
            expected = json.loads(args.expected.read_text(encoding="utf-8"))
            if args.command == "guard":
                check_deployment_window(expected, berlin_now())
            else:
                verify_feed(args.feed_url, expected)
                report("Verified the public feed matches this deployment. "
                       "Coffee Bot delivery still depends on its polling and room subscription.")
    except (OSError, ValueError, RuntimeError) as exc:
        report(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
