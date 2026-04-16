from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from poco.config import Settings, load_file_config


class SettingsConfigFileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        load_file_config.cache_clear()

    def tearDown(self) -> None:
        load_file_config.cache_clear()

    def test_settings_read_feishu_credentials_from_config_file(self) -> None:
        config_path = os.path.join(self.tempdir.name, "poco.config.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "POCO_FEISHU_APP_ID": "cli_test_app",
                    "POCO_FEISHU_APP_SECRET": "secret_test_value",
                },
                handle,
            )
        with patch.dict(os.environ, {"POCO_CONFIG_PATH": config_path}, clear=False):
            load_file_config.cache_clear()
            settings = Settings()

        self.assertEqual(settings.feishu_app_id, "cli_test_app")
        self.assertEqual(settings.feishu_app_secret, "secret_test_value")
        self.assertEqual(settings.feishu_delivery_mode, "longconn")

    def test_codex_transport_idle_seconds_has_thirty_minute_default(self) -> None:
        with patch.dict(
            os.environ,
            {"POCO_CONFIG_PATH": os.path.join(self.tempdir.name, "absent.json")},
            clear=False,
        ):
            load_file_config.cache_clear()
            settings = Settings()

        self.assertEqual(settings.codex_transport_idle_seconds, 1800)

    def test_codex_transport_idle_seconds_respects_env_override(self) -> None:
        with patch.dict(
            os.environ,
            {
                "POCO_CONFIG_PATH": os.path.join(self.tempdir.name, "absent.json"),
                "POCO_CODEX_TRANSPORT_IDLE_SECONDS": "60",
            },
            clear=False,
        ):
            load_file_config.cache_clear()
            settings = Settings()

        self.assertEqual(settings.codex_transport_idle_seconds, 60)

    def test_env_still_overrides_config_file(self) -> None:
        config_path = os.path.join(self.tempdir.name, "poco.config.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump({"POCO_FEISHU_APP_ID": "cli_from_file"}, handle)
        with patch.dict(
            os.environ,
            {
                "POCO_CONFIG_PATH": config_path,
                "POCO_FEISHU_APP_ID": "cli_from_env",
            },
            clear=False,
        ):
            load_file_config.cache_clear()
            settings = Settings()

        self.assertEqual(settings.feishu_app_id, "cli_from_env")

    def test_sectioned_config_file_supplies_feishu_and_slack_settings(self) -> None:
        config_path = os.path.join(self.tempdir.name, "poco.config.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "feishu": {
                        "app_id": "cli_feishu_section",
                        "app_secret": "secret_feishu_section",
                    },
                    "slack": {
                        "bot_token": "xoxb-test",
                        "signing_secret": "sigsec-test",
                        "app_token": "xapp-test",
                    },
                },
                handle,
            )
        with patch.dict(os.environ, {"POCO_CONFIG_PATH": config_path}, clear=False):
            load_file_config.cache_clear()
            settings = Settings()

        self.assertEqual(settings.feishu_app_id, "cli_feishu_section")
        self.assertEqual(settings.feishu_app_secret, "secret_feishu_section")
        self.assertEqual(settings.slack_bot_token, "xoxb-test")
        self.assertEqual(settings.slack_signing_secret, "sigsec-test")
        self.assertEqual(settings.slack_app_token, "xapp-test")
        self.assertTrue(settings.feishu_enabled)
        self.assertTrue(settings.slack_enabled)
        self.assertEqual(settings.runtime_mode, "feishu+slack")

    def test_flat_legacy_keys_take_precedence_over_sectioned_values(self) -> None:
        config_path = os.path.join(self.tempdir.name, "poco.config.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "POCO_FEISHU_APP_ID": "flat_wins",
                    "feishu": {"app_id": "section_loses"},
                },
                handle,
            )
        with patch.dict(os.environ, {"POCO_CONFIG_PATH": config_path}, clear=False):
            load_file_config.cache_clear()
            settings = Settings()

        self.assertEqual(settings.feishu_app_id, "flat_wins")

    def test_slack_socket_mode_requires_app_token(self) -> None:
        config_path = os.path.join(self.tempdir.name, "poco.config.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "slack": {
                        "bot_token": "xoxb-test",
                        "signing_secret": "sigsec-test",
                    },
                },
                handle,
            )
        with patch.dict(os.environ, {"POCO_CONFIG_PATH": config_path}, clear=False):
            load_file_config.cache_clear()
            settings = Settings()

        self.assertTrue(settings.slack_socket_mode_enabled)
        self.assertFalse(settings.slack_enabled)


if __name__ == "__main__":
    unittest.main()
