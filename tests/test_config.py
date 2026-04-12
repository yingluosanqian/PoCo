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


if __name__ == "__main__":
    unittest.main()
