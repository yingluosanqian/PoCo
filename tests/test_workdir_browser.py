from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from poco.main import create_app


class WorkdirBrowserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tempdir.name)
        (self.project_root / "api").mkdir()
        (self.project_root / "web").mkdir()
        self.env = patch.dict(
            os.environ,
            {
                "POCO_STATE_BACKEND": "sqlite",
                "POCO_STATE_DB_PATH": os.path.join(self.tempdir.name, "poco.db"),
                "POCO_APP_BASE_URL": "https://poco.test",
                "POCO_CODEX_WORKDIR": self.tempdir.name,
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tempdir.cleanup)
        self.app = create_app()
        self.client = TestClient(self.app)
        self.project = self.app.state.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )

    def test_workdir_browser_page_supports_manual_input_and_browse(self) -> None:
        response = self.client.get(
            "/ui/workdir",
            params={"project_id": self.project.id, "path": str(self.project_root)},
        )

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Browse Folders", html)
        self.assertIn("Enter Path Manually", html)
        self.assertIn("Option 1. Browse like open-folder", html)
        self.assertIn("api", html)
        self.assertIn("web", html)
        self.assertIn(str(self.project_root), html)

    def test_apply_project_workdir_updates_context(self) -> None:
        response = self.client.post(
            f"/api/projects/{self.project.id}/workdir",
            json={"workdir": str(self.project_root / 'api')},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["workdir"], str((self.project_root / "api").resolve()))
        context = self.app.state.workspace_controller.get_context(self.project)
        self.assertEqual(context.active_workdir, str((self.project_root / "api").resolve()))
        self.assertEqual(context.workdir_source, "manual")


if __name__ == "__main__":
    unittest.main()
