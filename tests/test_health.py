from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from poco.main import create_app


class HealthEndpointTest(unittest.TestCase):
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

    def test_health_reports_local_mode_readiness(self) -> None:
        app = create_app()
        client = TestClient(app)

        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["status"], "ok")
        self.assertIn(payload["mode"], {"local", "feishu"})
        self.assertIn(payload["feishu_delivery_mode"], {"webhook", "longconn"})
        self.assertIn("agent_backend", payload)
        self.assertIn("agent_ready", payload)
        self.assertIn("feishu_listener_ready", payload)
        self.assertIn("feishu_listener_detail", payload)
        self.assertIn(payload["state_backend"], {"memory", "sqlite"})
        self.assertIn("warnings", payload)
        self.assertIn("missing", payload)


if __name__ == "__main__":
    unittest.main()
