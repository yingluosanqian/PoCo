from __future__ import annotations

import os
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from poco.main import create_app


class DemoApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "POCO_STATE_BACKEND": "sqlite",
                "POCO_STATE_DB_PATH": os.path.join(self.tempdir.name, "poco.db"),
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tempdir.cleanup)
        self.client = TestClient(create_app())

    def test_demo_help_returns_immediate_response(self) -> None:
        response = self.client.post("/demo/command", json={"text": "/help"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "demo")
        self.assertIn("/run <prompt>", payload["response_text"])
        self.assertIsNone(payload["task_id"])

    def test_demo_run_creates_background_task(self) -> None:
        response = self.client.post(
            "/demo/command",
            json={"text": "/run Reply with exactly: DEMO_OK"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["dispatch_action"], "start")
        task_id = payload["task_id"]
        self.assertIsNotNone(task_id)

        for _ in range(90):
            task_response = self.client.get(f"/tasks/{task_id}")
            self.assertEqual(task_response.status_code, 200)
            task = task_response.json()
            if task["status"] in {"completed", "failed"}:
                self.assertEqual(task["status"], "completed")
                self.assertIn("DEMO_OK", task["result_summary"])
                break
            time.sleep(0.5)
        else:
            self.fail("demo task did not finish in time")

    def test_demo_approve_resumes_waiting_task(self) -> None:
        response = self.client.post(
            "/demo/command",
            json={"text": "/run confirm: Reply with exactly: APPROVED_DEMO"},
        )
        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]
        self.assertIsNotNone(task_id)

        for _ in range(40):
            task = self.client.get(f"/tasks/{task_id}").json()
            if task["status"] == "waiting_for_confirmation":
                break
            time.sleep(0.25)
        else:
            self.fail("task did not enter waiting_for_confirmation")

        approve = self.client.post(f"/demo/tasks/{task_id}/approve")
        self.assertEqual(approve.status_code, 200)

        for _ in range(90):
            task = self.client.get(f"/tasks/{task_id}").json()
            if task["status"] in {"completed", "failed"}:
                self.assertEqual(task["status"], "completed")
                self.assertIn("APPROVED_DEMO", task["result_summary"])
                break
            time.sleep(0.5)
        else:
            self.fail("approved task did not finish in time")


if __name__ == "__main__":
    unittest.main()
