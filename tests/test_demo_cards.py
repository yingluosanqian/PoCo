from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from poco.main import create_app


class DemoCardApiTest(unittest.TestCase):
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

    def test_demo_dm_project_list_card(self) -> None:
        response = self.client.get("/demo/cards/dm/projects")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "demo")
        self.assertEqual(payload["instruction"]["template_key"], "project_home")
        self.assertEqual(payload["card"]["schema"], "2.0")
        self.assertEqual(
            payload["card"]["body"]["elements"][1]["behaviors"][0]["value"]["intent_key"],
            "project.new",
        )

    def test_demo_card_action_creates_project(self) -> None:
        response = self.client.post(
            "/demo/card-actions",
            json={
                "event": {
                    "operator": {"open_id": "ou_demo_user"},
                    "context": {"open_message_id": "om_demo_card"},
                    "action": {
                        "value": {
                            "intent_key": "project.create",
                            "surface": "dm",
                            "request_id": "req_demo_project_create_1",
                        },
                        "form_value": {
                            "name": "PoCo",
                            "backend": "codex",
                        },
                    },
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "demo")
        self.assertEqual(payload["instruction"]["template_key"], "project_home")
        self.assertEqual(payload["card"]["data"]["schema"], "2.0")
        self.assertEqual(payload["card"]["data"]["header"]["title"]["content"], "PoCo Projects")


if __name__ == "__main__":
    unittest.main()
