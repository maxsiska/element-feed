"""Configure and test the independent cron-job.org clock without saving local secrets."""

import argparse
import base64
from datetime import datetime, timedelta, timezone
import getpass
import json
from pathlib import Path
import ssl
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from zoneinfo import ZoneInfo


REPO = "maxsiska/element-feed"
GITHUB = f"https://api.github.com/repos/{REPO}"
CRON = "https://api.cron-job.org"
TITLE = f"{REPO}: publish weekday lunch"
BERLIN = ZoneInfo("Europe/Berlin")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward either credential to a redirected destination.


def api(method, url, token, data=None):
    if (urlparse(url).scheme != "https"
            or urlparse(url).hostname not in ("api.github.com", "api.cron-job.org")):
        raise ValueError("Unexpected API destination")
    context = ssl.create_default_context()
    # python.org's macOS Python may not have its optional CA installation.
    if sys.platform == "darwin" and Path("/etc/ssl/cert.pem").exists():
        context.load_verify_locations("/etc/ssl/cert.pem")
    headers = {"Accept": "application/json", "Content-Type": "application/json",
               "User-Agent": "element-feed-setup/1.0", "X-GitHub-Api-Version": "2026-03-10"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, method=method,
                      data=None if data is None else json.dumps(data).encode(),
                      headers=headers)
    try:
        with build_opener(HTTPSHandler(context=context), NoRedirect()).open(request, timeout=30) as response:
            body = response.read()
        return json.loads(body) if body else {}
    except HTTPError as exc:
        # Response bodies and request headers may contain credentials; don't print them.
        raise RuntimeError(f"{method} {urlparse(url).hostname}: HTTP {exc.code}") from None


def job_spec(github_token, *, dry_run=False):
    return {
        "title": TITLE,
        "url": GITHUB + "/actions/workflows/publish.yml/dispatches",
        "enabled": True,
        "saveResponses": True,
        "requestMethod": 1,
        "requestTimeout": 30,
        "redirectSuccess": False,
        "schedule": {"timezone": "Europe/Berlin", "expiresAt": 0,
                     "hours": [11], "minutes": [25, 40, 55],
                     "mdays": [-1], "months": [-1], "wdays": [1, 2, 3, 4, 5]},
        "notification": {"onFailure": True, "onFailureCount": 1,
                         "onSuccess": True, "onDisable": True,
                         "mode": 2, "selectedChannels": [0]},
        "extendedData": {
            "headers": {"Authorization": f"Bearer {github_token}",
                        "Accept": "application/vnd.github+json",
                        "Content-Type": "application/json",
                        "X-GitHub-Api-Version": "2026-03-10"},
            "body": json.dumps({"ref": "main", "inputs": {"dry_run": dry_run}}),
        },
    }


def test_schedule(now):
    target = (now.astimezone(BERLIN) + timedelta(minutes=2)).replace(second=0, microsecond=0)
    return {"timezone": "Europe/Berlin",
            "expiresAt": int((target + timedelta(minutes=5)).strftime("%Y%m%d%H%M%S")),
            "hours": [target.hour], "minutes": [target.minute],
            "mdays": [target.day], "months": [target.month], "wdays": [-1]}


def wait_for_dry_run(run_id, github_token):
    if not isinstance(run_id, int):
        raise RuntimeError("GitHub did not return a verifiable workflow run ID.")
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        run = api("GET", f"{GITHUB}/actions/runs/{run_id}", github_token)
        if run["status"] == "completed":
            if run["conclusion"] != "success":
                raise RuntimeError(f"Dry run failed: https://github.com/{REPO}/actions/runs/{run_id}")
            return
        time.sleep(10)
    raise RuntimeError("Timed out waiting for GitHub's dry run; the hosted job will stay disabled.")


def install(cron_token, github_token):
    # Make sure the deployed workflow supports safe previews before triggering it.
    source = api("GET", f"{GITHUB}/contents/.github/workflows/publish.yml?ref=main", None)
    if "dry_run:" not in base64.b64decode(source["content"]).decode():
        raise RuntimeError("Deploy the updated workflow before configuring the hosted scheduler.")
    jobs = api("GET", CRON + "/jobs", cron_token)
    if jobs.get("someFailed"):
        raise RuntimeError("The job listing was incomplete; refusing to create a possible duplicate.")
    matching = [j for j in jobs["jobs"] if j["title"] == TITLE
                and j["url"] == job_spec(github_token)["url"]]
    if len(matching) > 1:
        raise RuntimeError("Multiple matching jobs exist; resolve them in cron-job.org first.")
    print("Checking the restricted GitHub token with a dry run (no publication)…", flush=True)
    check = api("POST", GITHUB + "/actions/workflows/publish.yml/dispatches", github_token,
                {"ref": "main", "inputs": {"dry_run": True}})
    wait_for_dry_run(check.get("workflow_run_id"), github_token)
    spec = job_spec(github_token, dry_run=True)
    started = datetime.now(timezone.utc)
    spec["schedule"] = test_schedule(started)
    job_id = matching[0]["jobId"] if matching else None
    if job_id is None:
        job_id = api("PUT", CRON + "/jobs", cron_token, {"job": spec})["jobId"]
    else:
        api("PATCH", f"{CRON}/jobs/{job_id}", cron_token, {"job": spec})
    print(f"Hosted job {job_id}: testing the external clock in approximately two minutes…", flush=True)
    try:
        deadline = time.monotonic() + 480
        while time.monotonic() < deadline:
            history = api("GET", f"{CRON}/jobs/{job_id}/history", cron_token)
            attempts = [h for h in history["history"] if h["date"] >= started.timestamp()]
            if attempts:
                latest = max(attempts, key=lambda h: h["date"])
                if latest["status"] != 1:
                    raise RuntimeError(f"Hosted test failed with HTTP {latest.get('httpStatus')}.")
                detail = api("GET", f"{CRON}/jobs/{job_id}/history/{latest['identifier']}", cron_token)
                response = json.loads(detail["jobHistoryDetails"]["body"])
                wait_for_dry_run(response.get("workflow_run_id"), github_token)
                break
            time.sleep(15)
        else:
            raise RuntimeError("The external clock did not execute its test within eight minutes.")
        final = job_spec(github_token)
        api("PATCH", f"{CRON}/jobs/{job_id}", cron_token, {"job": final})
        saved = api("GET", f"{CRON}/jobs/{job_id}", cron_token)["jobDetails"]
        if any(saved.get(k) != final[k] for k in ("enabled", "url", "schedule", "requestMethod", "extendedData")):
            raise RuntimeError("The saved scheduler configuration did not match the requested job.")
    except BaseException:
        api("PATCH", f"{CRON}/jobs/{job_id}", cron_token, {"job": {"enabled": False}})
        print(f"Hosted job {job_id} disabled because setup did not finish.", flush=True)
        raise
    print(f"Verified and enabled hosted job {job_id}: weekdays at 11:25, 11:40 and 11:55 Berlin.")
    print("HTTP failure/recovery alerts go to your cron-job.org account email.")
    print("No credentials were saved to local files. Rotate the GitHub token before it expires.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Prompt for keys, configure and test the hosted job")
    args = parser.parse_args(argv)
    if not args.apply:
        print(json.dumps(job_spec("REPOSITORY_SCOPED_TOKEN"), indent=2))
        print("Run with --apply after creating the accounts/tokens described in README.md.")
        return 0
    print("This sends a repository-scoped GitHub token to cron-job.org for storage in this job.")
    print("Use a fine-grained token for maxsiska/element-feed ONLY, with Actions: read and write.")
    github_token = getpass.getpass("Restricted GitHub token (hidden): ").strip()
    if not github_token.startswith("github_pat_"):
        raise SystemExit("A fine-grained GitHub token is required; do not use your general Git credential.")
    cron_token = getpass.getpass("cron-job.org API key (hidden): ").strip()
    if not cron_token:
        raise SystemExit("Missing cron-job.org API key.")
    try:
        install(cron_token, github_token)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"Setup incomplete: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
