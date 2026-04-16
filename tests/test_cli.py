from __future__ import annotations

import json
import os
import tempfile
import unittest
from io import StringIO
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
            os.environ.pop("POCO_FEISHU_APP_ID", None)
            os.environ.pop("POCO_FEISHU_APP_SECRET", None)
            exit_code = cli.command_config(Namespace())

        self.assertEqual(exit_code, 0)
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["POCO_FEISHU_APP_ID"], "cli_new_app")
        self.assertEqual(saved["POCO_FEISHU_APP_SECRET"], "new_secret")

    def test_config_command_skips_prompts_when_both_env_vars_set(self) -> None:
        input_mock = Mock(side_effect=AssertionError("input must not be called"))
        getpass_mock = Mock(side_effect=AssertionError("getpass must not be called"))
        with (
            patch.object(cli, "DEFAULT_RUNTIME_DIR", str(self.runtime_dir)),
            patch.object(cli, "PID_PATH", self.pid_path),
            patch.object(cli, "LOG_PATH", self.log_path),
            patch.dict(
                os.environ,
                {
                    "POCO_CONFIG_PATH": str(self.config_path),
                    "POCO_FEISHU_APP_ID": "env_app_id",
                    "POCO_FEISHU_APP_SECRET": "env_app_secret",
                },
                clear=False,
            ),
            patch("builtins.input", input_mock),
            patch("poco.cli.getpass", getpass_mock),
        ):
            exit_code = cli.command_config(Namespace())

        self.assertEqual(exit_code, 0)
        input_mock.assert_not_called()
        getpass_mock.assert_not_called()
        self.assertFalse(self.config_path.exists())

    def test_config_command_only_prompts_missing_env_var(self) -> None:
        getpass_mock = Mock(side_effect=AssertionError("getpass must not be called"))
        with (
            patch.object(cli, "DEFAULT_RUNTIME_DIR", str(self.runtime_dir)),
            patch.object(cli, "PID_PATH", self.pid_path),
            patch.object(cli, "LOG_PATH", self.log_path),
            patch.dict(
                os.environ,
                {
                    "POCO_CONFIG_PATH": str(self.config_path),
                    "POCO_FEISHU_APP_SECRET": "env_app_secret",
                },
                clear=False,
            ),
            patch("builtins.input", return_value="prompted_app_id"),
            patch("poco.cli.getpass", getpass_mock),
        ):
            os.environ.pop("POCO_FEISHU_APP_ID", None)
            exit_code = cli.command_config(Namespace())

        self.assertEqual(exit_code, 0)
        getpass_mock.assert_not_called()
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["POCO_FEISHU_APP_ID"], "prompted_app_id")
        self.assertNotIn("POCO_FEISHU_APP_SECRET", saved)

    def test_config_command_ignores_blank_env_var(self) -> None:
        with (
            patch.object(cli, "DEFAULT_RUNTIME_DIR", str(self.runtime_dir)),
            patch.object(cli, "PID_PATH", self.pid_path),
            patch.object(cli, "LOG_PATH", self.log_path),
            patch.dict(
                os.environ,
                {
                    "POCO_CONFIG_PATH": str(self.config_path),
                    "POCO_FEISHU_APP_ID": "   ",
                    "POCO_FEISHU_APP_SECRET": "   ",
                },
                clear=False,
            ),
            patch("builtins.input", return_value="prompted_app_id"),
            patch("poco.cli.getpass", return_value="prompted_secret"),
        ):
            exit_code = cli.command_config(Namespace())

        self.assertEqual(exit_code, 0)
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["POCO_FEISHU_APP_ID"], "prompted_app_id")
        self.assertEqual(saved["POCO_FEISHU_APP_SECRET"], "prompted_secret")

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

    def test_status_reports_stopped_when_no_pid_exists(self) -> None:
        with (
            patch.object(cli, "DEFAULT_RUNTIME_DIR", str(self.runtime_dir)),
            patch.object(cli, "PID_PATH", self.pid_path),
            patch.object(cli, "LOG_PATH", self.log_path),
            patch.dict(os.environ, {"POCO_CONFIG_PATH": str(self.config_path)}, clear=False),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            exit_code = cli.command_status(Namespace(host="127.0.0.1", port=8000))

        self.assertEqual(exit_code, 0)
        self.assertIn("PoCo status: stopped", stdout.getvalue())

    def test_status_reports_health_for_running_process(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.pid_path.write_text("43210\n", encoding="utf-8")
        self.config_path.write_text(
            json.dumps({"POCO_FEISHU_APP_ID": "cli_status_app"}),
            encoding="utf-8",
        )
        with (
            patch.object(cli, "DEFAULT_RUNTIME_DIR", str(self.runtime_dir)),
            patch.object(cli, "PID_PATH", self.pid_path),
            patch.object(cli, "LOG_PATH", self.log_path),
            patch.dict(os.environ, {"POCO_CONFIG_PATH": str(self.config_path)}, clear=False),
            patch("poco.cli._is_running", return_value=True),
            patch(
                "poco.cli._fetch_health",
                return_value={
                    "mode": "feishu",
                    "feishu_delivery_mode": "longconn",
                    "feishu_listener_ready": True,
                    "agent_backend": "codex",
                    "agent_ready": True,
                },
            ),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            exit_code = cli.command_status(Namespace(host="127.0.0.1", port=8000))

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("PoCo status: running", output)
        self.assertIn("delivery=longconn", output)
        self.assertIn("agent=codex", output)


if __name__ == "__main__":
    unittest.main()
