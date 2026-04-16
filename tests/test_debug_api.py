from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from poco.main import create_app


class DebugApiTest(unittest.TestCase):
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

    def test_debug_endpoint_returns_snapshot(self) -> None:
        response = self.client.get("/debug/feishu")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("inbound_events", payload)
        self.assertIn("outbound_attempts", payload)
        self.assertIn("errors", payload)
        self.assertIn("listener", payload)

    def test_inbound_event_appears_in_debug_snapshot(self) -> None:
        payload = {
            "event": {
                "sender": {"sender_id": {"open_id": "ou_demo_user"}},
                "message": {
                    "chat_type": "p2p",
                    "content": json.dumps({"text": "/help"}),
                },
            }
        }
        self.client.post("/platform/feishu/events", json=payload)
        snapshot = self.client.get("/debug/feishu").json()
        self.assertGreaterEqual(len(snapshot["inbound_events"]), 1)
        self.assertEqual(snapshot["inbound_events"][0]["user_id"], "ou_demo_user")

    def test_card_action_event_appears_in_debug_snapshot(self) -> None:
        payload = {
            "event_id": "evt_demo_card_debug_1",
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_demo_card_debug"},
                "action": {
                    "value": {
                        "intent_key": "project.create",
                        "surface": "dm",
                    },
                },
            },
        }
        self.client.post("/platform/feishu/card-actions", json=payload)
        snapshot = self.client.get("/debug/feishu").json()
        self.assertGreaterEqual(len(snapshot["inbound_events"]), 1)
        self.assertEqual(snapshot["inbound_events"][0]["text"], "project.create")


class EnvInventoryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.secret_value = "super-secret-anthropic-key-xxxx"
        self.env = patch.dict(
            os.environ,
            {
                "POCO_STATE_BACKEND": "sqlite",
                "POCO_STATE_DB_PATH": os.path.join(self.tempdir.name, "poco.db"),
                "ANTHROPIC_API_KEY": self.secret_value,
                "HTTP_PROXY": "http://proxy.example:8080",
                "POCO_CLAUDE_MODEL": "sonnet",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(create_app())

    def _find_variable(self, payload: dict, category_name: str, key: str) -> dict:
        for category in payload["categories"]:
            if category["name"] == category_name:
                for variable in category["variables"]:
                    if variable["key"] == key:
                        return variable
        self.fail(f"variable {category_name}.{key} not found in payload")

    def test_env_endpoint_reports_present_and_length(self) -> None:
        response = self.client.get("/debug/env")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("note", payload)
        self.assertIn("categories", payload)

        anthropic = self._find_variable(payload, "claude_code", "ANTHROPIC_API_KEY")
        self.assertTrue(anthropic["present"])
        self.assertEqual(anthropic["length"], len(self.secret_value))

        proxy = self._find_variable(payload, "proxy", "HTTP_PROXY")
        self.assertTrue(proxy["present"])
        self.assertEqual(proxy["length"], len("http://proxy.example:8080"))

        claude_model = self._find_variable(payload, "claude_code", "POCO_CLAUDE_MODEL")
        self.assertTrue(claude_model["present"])

    def test_env_endpoint_marks_missing_keys_absent(self) -> None:
        payload = self.client.get("/debug/env").json()
        # OPENAI_API_KEY is not set in this test environment.
        openai = self._find_variable(payload, "codex", "OPENAI_API_KEY")
        self.assertFalse(openai["present"])
        self.assertEqual(openai["length"], 0)

    def test_env_endpoint_never_leaks_values(self) -> None:
        response = self.client.get("/debug/env")
        body = response.text
        self.assertNotIn(self.secret_value, body)
        self.assertNotIn("proxy.example", body)
        self.assertNotIn("sonnet", body)

    def test_env_endpoint_only_contains_whitelisted_keys(self) -> None:
        from poco.env_inventory import whitelisted_keys

        allowed = set(whitelisted_keys())
        payload = self.client.get("/debug/env").json()
        reported = {
            variable["key"]
            for category in payload["categories"]
            for variable in category["variables"]
        }
        self.assertEqual(reported, allowed)

    def test_health_warnings_mention_env_debug_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        warnings = response.json().get("warnings", [])
        self.assertTrue(
            any("/debug/env" in w for w in warnings),
            f"expected /debug/env hint in warnings, got: {warnings}",
        )


if __name__ == "__main__":
    unittest.main()
