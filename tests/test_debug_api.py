from __future__ import annotations

import json
import unittest

from fastapi.testclient import TestClient

from poco.main import create_app


class DebugApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_debug_endpoint_returns_snapshot(self) -> None:
        response = self.client.get("/debug/feishu")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("inbound_events", payload)
        self.assertIn("outbound_attempts", payload)
        self.assertIn("errors", payload)

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


if __name__ == "__main__":
    unittest.main()
