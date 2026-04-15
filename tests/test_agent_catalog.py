from __future__ import annotations

import unittest
from unittest.mock import patch

from poco.agent.catalog import (
    _discover_coco_model_options,
    _discover_codex_model_options,
    get_backend_descriptor,
    get_backend_model_options,
)


class AgentCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        _discover_coco_model_options.cache_clear()
        _discover_codex_model_options.cache_clear()

    def test_cursor_descriptor_defaults_to_auto_model(self) -> None:
        descriptor = get_backend_descriptor("cursor_agent")
        self.assertEqual(descriptor.default_config["model"], "auto")

    def test_codex_model_options_are_discovered_from_app_server(self) -> None:
        with (
            patch("poco.agent.catalog.shutil.which", return_value="/opt/homebrew/bin/codex"),
            patch(
                "poco.agent.catalog._request_codex_model_list",
                return_value={
                    "data": [
                        {"id": "gpt-5.4", "displayName": "gpt-5.4"},
                        {"id": "gpt-5.4-mini", "displayName": "GPT-5.4-Mini"},
                        {"id": "gpt-5.3-codex", "displayName": "gpt-5.3-codex"},
                    ]
                },
            ),
        ):
            options = get_backend_model_options("codex")

        self.assertEqual(
            options,
            (
                ("gpt-5.4", "gpt-5.4"),
                ("GPT-5.4-Mini", "gpt-5.4-mini"),
                ("gpt-5.3-codex", "gpt-5.3-codex"),
            ),
        )

    def test_codex_model_options_do_not_fallback_when_codex_is_missing(self) -> None:
        with patch("poco.agent.catalog.shutil.which", return_value=None):
            options = get_backend_model_options("codex")

        self.assertEqual(options, ())

    def test_codex_model_options_do_not_fallback_when_discovery_fails(self) -> None:
        with (
            patch("poco.agent.catalog.shutil.which", return_value="/opt/homebrew/bin/codex"),
            patch(
                "poco.agent.catalog._request_codex_model_list",
                side_effect=RuntimeError("boom"),
            ),
        ):
            options = get_backend_model_options("codex")

        self.assertEqual(options, ())

    def test_cursor_model_options_are_discovered_from_cli(self) -> None:
        sample_output = """
\x1b[2K\x1b[GAvailable models

auto - Auto
composer-2-fast - Composer 2 Fast  (current, default)
gpt-5.4-medium - GPT-5.4 1M
claude-4.5-sonnet - Sonnet 4.5 1M

Tip: use --model <id> to switch.
"""
        with (
            patch("poco.agent.catalog.shutil.which", return_value="/Users/yihanc/.local/bin/cursor-agent"),
            patch(
                "poco.agent.catalog.subprocess.run",
                return_value=type(
                    "Completed",
                    (),
                    {"stdout": sample_output, "stderr": "", "returncode": 0},
                )(),
            ),
        ):
            options = get_backend_model_options("cursor_agent")

        self.assertEqual(
            options,
            (
                ("Auto", "auto"),
                ("Composer 2 Fast", "composer-2-fast"),
                ("GPT-5.4 1M", "gpt-5.4-medium"),
                ("Sonnet 4.5 1M", "claude-4.5-sonnet"),
            ),
        )

    def test_coco_model_options_include_local_configured_model(self) -> None:
        with (
            patch("poco.agent.catalog._request_coco_model_list", return_value=(("GPT-5.2", "GPT-5.2"), ("GPT-5.4", "GPT-5.4"))),
            patch("poco.agent.catalog.Path.read_text", return_value="model:\n    name: GPT-5.4\n"),
            patch("poco.agent.catalog.shutil.which", return_value="/Users/bytedance/.local/bin/traecli"),
        ):
            options = get_backend_model_options("coco")

        self.assertEqual(
            options,
            (
                ("GPT-5.4", "GPT-5.4"),
                ("GPT-5.2", "GPT-5.2"),
            ),
        )

    def test_coco_model_options_are_discovered_from_acp(self) -> None:
        with (
            patch(
                "poco.agent.catalog._request_coco_model_list",
                return_value=(("GPT-5.2", "GPT-5.2"), ("GPT-5.4", "GPT-5.4")),
            ),
            patch("poco.agent.catalog._read_coco_configured_model", return_value=None),
            patch("poco.agent.catalog.shutil.which", return_value="/Users/bytedance/.local/bin/traecli"),
        ):
            options = get_backend_model_options("coco")

        self.assertEqual(
            options,
            (
                ("GPT-5.2", "GPT-5.2"),
                ("GPT-5.4", "GPT-5.4"),
            ),
        )
