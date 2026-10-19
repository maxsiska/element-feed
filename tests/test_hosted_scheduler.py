import base64
from copy import deepcopy
from datetime import datetime
import json
import unittest
from unittest.mock import patch

import setup_hosted_scheduler as setup


class HostedSchedulerTests(unittest.TestCase):
    def fake_api(self, *, existing=False, external_failure=False):
        self.calls = []
        self.saved = {}

        def api(method, url, token, data=None):
            self.calls.append((method, url, deepcopy(data)))
            if "/contents/" in url:
                self.assertIsNone(token)  # No Contents permission needed on the limited token.
                return {"content": base64.b64encode(b"workflow_dispatch:\n  inputs:\n    dry_run:\n").decode()}
            if method == "GET" and url == setup.CRON + "/jobs":
                return {"someFailed": False, "jobs": ([{"jobId": 7, "title": setup.TITLE,
                        "url": setup.job_spec("token")["url"]}] if existing else [])}
            if url.endswith("/dispatches"):
                self.assertTrue(data["inputs"]["dry_run"])
                return {"workflow_run_id": 1}
            if "/actions/runs/" in url:
                return {"status": "completed", "conclusion": "success"}
            if method in ("PUT", "PATCH"):
                self.saved.update(deepcopy(data["job"]))
                return {"jobId": 7}
            if url.endswith("/history"):
                return {"history": [{"date": 4102444800, "status": 4 if external_failure else 1,
                                     "httpStatus": 401 if external_failure else 200, "identifier": "test"}]}
            if url.endswith("/history/test"):
                return {"jobHistoryDetails": {"body": json.dumps({"workflow_run_id": 2})}}
            if url.endswith("/jobs/7"):
                return {"jobDetails": deepcopy(self.saved)}
            raise AssertionError((method, url))
        return api

    def test_production_is_enabled_only_after_external_dry_run_succeeds(self):
        with patch("setup_hosted_scheduler.api", side_effect=self.fake_api()):
            setup.install("cron-key", "github_pat_test")
        creations = [data for method, _, data in self.calls if method == "PUT"]
        self.assertEqual(len(creations), 1)
        self.assertTrue(json.loads(creations[0]["job"]["extendedData"]["body"])["inputs"]["dry_run"])
        self.assertFalse(json.loads(self.saved["extendedData"]["body"])["inputs"]["dry_run"])
        self.assertTrue(self.saved["enabled"])
        self.assertEqual(self.saved["schedule"]["minutes"], [25, 40, 55])
        self.assertEqual(self.saved["schedule"]["wdays"], [1, 2, 3, 4, 5])

    def test_existing_job_is_updated_without_creating_a_duplicate(self):
        with patch("setup_hosted_scheduler.api", side_effect=self.fake_api(existing=True)):
            setup.install("cron-key", "github_pat_test")
        self.assertNotIn("PUT", [method for method, _, _ in self.calls])
        self.assertTrue(self.saved["enabled"])

    def test_failed_external_test_leaves_job_disabled(self):
        with (patch("setup_hosted_scheduler.api", side_effect=self.fake_api(external_failure=True)),
              self.assertRaisesRegex(RuntimeError, "Hosted test failed")):
            setup.install("cron-key", "github_pat_test")
        self.assertFalse(self.saved["enabled"])
        self.assertTrue(json.loads(self.saved["extendedData"]["body"])["inputs"]["dry_run"])

    def test_temporary_test_schedule_handles_midnight_and_year_rollover(self):
        now = datetime(2026, 12, 31, 23, 59, 30, tzinfo=setup.BERLIN)
        schedule = setup.test_schedule(now)
        self.assertEqual(schedule["hours"], [0])
        self.assertEqual(schedule["minutes"], [1])
        self.assertEqual(schedule["months"], [1])
        self.assertEqual(schedule["mdays"], [1])
        self.assertEqual(schedule["expiresAt"], 20270101000600)


if __name__ == "__main__":
    unittest.main()
