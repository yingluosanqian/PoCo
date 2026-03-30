"""Shared menu constants and state dataclasses for the TUI."""

from __future__ import annotations

from dataclasses import dataclass


ROOT_MENU_OPTIONS = ["agent", "bot", "poco", "language", "quit"]
CONFIG_MENU_OPTIONS = ["language", "bot", "agent", "poco"]
CONFIG_GROUP_SECTIONS = {
    "bot": ["feishu"],
    "agent": ["codex", "claude"],
    "poco": ["bridge", "show"],
}
BUILTIN_CLAUDE_BACKENDS = ["anthropic", "deepseek", "kimi", "minimax"]
ADD_CUSTOM_BACKEND = "__add_custom__"
CLAUDE_BACKEND_FIELDS = [
    ("set_as_default", "set_as_default"),
    ("base_url", "base_url"),
    ("auth_token", "auth_token"),
    ("model", "model"),
    ("extra_env", "extra_env"),
]
CUSTOM_CLAUDE_BACKEND_FIELDS = [
    ("set_as_default", "set_as_default"),
    ("base_url", "base_url"),
    ("auth_token", "auth_token"),
    ("model", "model"),
    ("extra_env", "extra_env"),
    ("delete", "delete"),
]
CLAUDE_CUSTOM_ADD_FIELDS = [
    ("name", "name"),
    ("base_url", "base_url"),
    ("auth_token", "auth_token"),
    ("model", "model"),
    ("confirm", "confirm"),
]
CLAUDE_MODEL_ACTIONS = [("set_as_default", "set_as_default")]
EXTRA_ENV_ACTIONS = [("edit_value", "edit_value"), ("remove", "remove")]
LANGUAGE_CHOICES = [("English", "en"), ("中文", "zh")]
CONFIG_FIELDS = {
    "language": [("ui.language", "language")],
    "feishu": [
        ("feishu.app_id", "app_id"),
        ("feishu.app_secret", "app_secret"),
        ("feishu.encrypt_key", "encrypt_key"),
        ("feishu.verification_token", "verification_token"),
        ("feishu.card_test_template_id", "card_test_template_id"),
        ("feishu.allowed_open_ids", "allowed_open_ids"),
        ("feishu.allow_all_users", "allow_all_users"),
    ],
    "codex": [
        ("codex.bin", "bin"),
        ("codex.app_server_args", "app_server_args"),
        ("codex.model", "model"),
        ("codex.reasoning_effort", "reasoning_effort"),
        ("codex.approval_policy", "approval_policy"),
        ("codex.sandbox", "sandbox"),
    ],
    "claude": [
        ("claude.bin", "bin"),
        ("claude.app_server_args", "app_server_args"),
        ("claude.approval_policy", "approval_policy"),
        ("claude.sandbox", "sandbox"),
    ],
    "bridge": [
        ("bridge.message_limit", "message_limit"),
        ("bridge.live_update_initial_seconds", "live_update_initial_seconds"),
        ("bridge.live_update_max_seconds", "live_update_max_seconds"),
        ("bridge.max_message_edits", "max_message_edits"),
    ],
}


@dataclass
class ConfigScreenState:
    """Represents one level in the config navigation stack.

    Attributes:
        kind: Logical screen kind, such as ``sections`` or ``fields``.
        selected: Zero-based selected index within the current menu.
        group: Top-level config group, such as ``bot`` or ``agent``.
        section: Concrete config section, such as ``feishu`` or ``claude``.
        backend: Claude backend name when navigating Claude backend menus.
        model: Selected model name when navigating model actions.
        env_key: Selected extra-env key when navigating env actions.
        path: Concrete config path when editing a value.
        input_mode: Specialized input mode for multi-step edits.
        draft: Temporary payload for in-progress custom backend creation.
    """

    kind: str
    selected: int = 0
    group: str | None = None
    section: str | None = None
    backend: str | None = None
    model: str | None = None
    env_key: str | None = None
    path: str | None = None
    input_mode: str | None = None
    draft: dict | None = None


@dataclass
class OptionMenuState:
    """Describes a selectable menu and its current cursor position.

    Attributes:
        kind: Logical menu kind.
        selected: Zero-based selected index.
        count: Total number of available options.
    """

    kind: str
    selected: int
    count: int
