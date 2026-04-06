from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from poco.main import create_app


class HealthEndpointTest(unittest.TestCase):
    def test_health_reports_local_mode_readiness(self) -> None:
        app = create_app()
        client = TestClient(app)

        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["status"], "ok")
        self.assertIn(payload["mode"], {"local", "feishu"})
        self.assertIn("agent_backend", payload)
        self.assertIn("agent_ready", payload)
        self.assertIn("warnings", payload)
        self.assertIn("missing", payload)


if __name__ == "__main__":
    unittest.main()
