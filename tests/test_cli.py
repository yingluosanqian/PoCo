from __future__ import annotations

import json
import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock, patch

from poco import cli
from poco.config import load_file_config


class PocoCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.runtime_dir = Path(self.tempdir.name)
        self.config_path = self.runtime_dir / "poco.config.json"
        self.pid_path = self.runtime_dir / "poco.pid"
        self.log_path = self.runtime_dir / "poco.log"
        load_file_config.cache_clear()

    def tearDown(self) -> None:
        load_file_config.cache_clear()

    def test_config_command_writes_feishu_credentials(self) -> None:
        with (
            patch.object(cli, "DEFAULT_RUNTIME_DIR", str(self.runtime_dir)),
            patch.object(cli, "PID_PATH", self.pid_path),
            patch.object(cli, "LOG_PATH", self.log_path),
            patch.dict(os.environ, {"POCO_CONFIG_PATH": str(self.config_path)}, clear=False),
            patch("builtins.input", return_value="cli_new_app"),
            patch("poco.cli.getpass", return_value="new_secret"),
        ):
            exit_code = cli.command_config(Namespace())

        self.assertEqual(exit_code, 0)
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["POCO_FEISHU_APP_ID"], "cli_new_app")
        self.assertEqual(saved["POCO_FEISHU_APP_SECRET"], "new_secret")

    def test_start_command_spawns_background_process_and_writes_pid(self) -> None:
        process = Mock(pid=43210)
        process.poll.return_value = None
        with (
            patch.object(cli, "DEFAULT_RUNTIME_DIR", str(self.runtime_dir)),
            patch.object(cli, "PID_PATH", self.pid_path),
            patch.object(cli, "LOG_PATH", self.log_path),
            patch("poco.cli.subprocess.Popen", return_value=process) as popen,
        ):
            exit_code = cli.command_start(Namespace(host="127.0.0.1", port=8000))

        self.assertEqual(exit_code, 0)
        self.assertEqual(self.pid_path.read_text(encoding="utf-8").strip(), "43210")
        popen.assert_called_once()

    def test_shutdown_removes_stale_pid_file(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.pid_path.write_text("54321\n", encoding="utf-8")
        with (
            patch.object(cli, "DEFAULT_RUNTIME_DIR", str(self.runtime_dir)),
            patch.object(cli, "PID_PATH", self.pid_path),
            patch.object(cli, "LOG_PATH", self.log_path),
            patch("poco.cli._is_running", return_value=False),
        ):
            exit_code = cli.command_shutdown(Namespace())

        self.assertEqual(exit_code, 0)
        self.assertFalse(self.pid_path.exists())


if __name__ == "__main__":
    unittest.main()
