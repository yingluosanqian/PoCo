"""Workspace section schemas for the refactored PoCo TUI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from ..config import get_nested, mask_secret
from ..providers import model_choices
from .state import SubviewId, WorkspaceSection

Validator = Callable[[str], str | None]


@dataclass(frozen=True)
class TextInput:
    secret: bool = False
    validator: Validator | None = None
    placeholder: str = ""


@dataclass(frozen=True)
class ChoiceSelect:
    choices: list[tuple[str, str]]


@dataclass(frozen=True)
class ActionTrigger:
    label: str


@dataclass(frozen=True)
class SubviewOpen:
    subview_id: SubviewId


@dataclass(frozen=True)
class ReadOnly:
    pass


FieldInteraction = TextInput | ChoiceSelect | ActionTrigger | SubviewOpen | ReadOnly


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    interaction: FieldInteraction


SECTION_ORDER = [
    WorkspaceSection.AGENT,
    WorkspaceSection.BOT,
    WorkspaceSection.POCO,
    WorkspaceSection.LANGUAGE,
]


def bot_display_name(config: dict) -> str:
    feishu = config.get("feishu", {})
    return (
        str(feishu.get("alias", "")).strip()
        or str(feishu.get("app_name", "")).strip()
        or str(feishu.get("app_id", "")).strip()
        or "unbound"
    )


def display_config_value(config: dict, path: str) -> str:
    lowered = path.lower()
    try:
        value = get_nested(config, path)
    except Exception:
        if "token" in lowered or "secret" in lowered or lowered.endswith("encrypt_key"):
            return "[#e5534b]—[/]"
        return "[#8b949e]—[/]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "[#8b949e]—[/]"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False) if value else "[#8b949e]—[/]"
    text = str(value or "").strip()
    if not text:
        if "token" in lowered or "secret" in lowered or lowered.endswith("encrypt_key"):
            return "[#e5534b]—[/]"
        return "[#8b949e]—[/]"
    if "secret" in lowered or "token" in lowered:
        return mask_secret(text)
    return text


def _non_empty_choice_labels(values: list[str], current: str = "") -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value in [current, *values]:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        options.append((item, item))
    return options


def _backend_names(config: dict) -> list[str]:
    claude = config.get("claude", {})
    backends = claude.get("backends", {})
    if not isinstance(backends, dict):
        return []
    return sorted(str(name) for name in backends.keys() if str(name).strip() and str(name).strip() != "custom")


def current_claude_backend(config: dict) -> str:
    claude = config.get("claude", {})
    backend = str(claude.get("default_backend", "anthropic")).strip() or "anthropic"
    return backend


def bot_advanced_fields(config: dict) -> list[FieldDef]:
    return [
        FieldDef("feishu.encrypt_key", "Encrypt Key", TextInput(secret=True)),
        FieldDef("feishu.verification_token", "Verification Token", TextInput(secret=True)),
        FieldDef("feishu.card_test_template_id", "Card Template ID", TextInput()),
    ]


def claude_backend_setting_fields(config: dict) -> list[FieldDef]:
    claude = config.get("claude", {})
    default_backend = current_claude_backend(config)
    backend_payload = claude.get("backends", {}).get(default_backend, {}) if isinstance(claude.get("backends", {}), dict) else {}
    claude_model = str(backend_payload.get("default_model", "")).strip()
    fields = [
        FieldDef("claude.default_backend", "Backend", ReadOnly()),
        FieldDef(f"claude.backends.{default_backend}.base_url", "Base URL", TextInput()),
        FieldDef(f"claude.backends.{default_backend}.auth_token", "Auth Token", TextInput(secret=True)),
        FieldDef(
            f"claude.backends.{default_backend}.default_model",
            "Model",
            ChoiceSelect(_non_empty_choice_labels(model_choices("claude", default_backend), claude_model)),
        ),
        FieldDef(
            f"claude.backends.{default_backend}.extra_env",
            "Extra Env",
            TextInput(placeholder='JSON object, e.g. {"KEY":"VALUE"}'),
        ),
    ]
    if default_backend not in {"anthropic", "deepseek", "kimi", "minimax"}:
        fields.append(FieldDef("claude.delete_current_backend", "Delete Current Backend", ActionTrigger("delete_current_claude_backend")))
    return fields


def section_fields(config: dict, section: WorkspaceSection) -> list[FieldDef]:
    if section == WorkspaceSection.BOT:
        fields = [
            FieldDef("feishu.app_id", "APP ID", TextInput()),
            FieldDef("feishu.app_secret", "APP Secret", TextInput(secret=True)),
            FieldDef("feishu.app_name", "App Name", ReadOnly()),
            FieldDef("feishu.alias", "Alias", TextInput(placeholder="optional local display name")),
            FieldDef("feishu.allow_all_users", "Allow All Users", ChoiceSelect([("true", "true"), ("false", "false")])),
        ]
        if not bool(config.get("feishu", {}).get("allow_all_users", True)):
            fields.append(FieldDef("feishu.allowed_open_ids", "Allowed Open IDs", TextInput(placeholder="comma separated open_ids")))
        fields.append(FieldDef("feishu.advanced", "Advanced", SubviewOpen(SubviewId.BOT_ADVANCED)))
        return fields

    if section == WorkspaceSection.POCO:
        return [
            FieldDef("bridge.message_limit", "Message Limit", TextInput()),
            FieldDef("bridge.live_update_initial_seconds", "Initial Update Seconds", TextInput()),
            FieldDef("bridge.live_update_max_seconds", "Max Update Seconds", TextInput()),
            FieldDef("bridge.max_message_edits", "Max Message Edits", TextInput()),
            FieldDef("poco.show_config", "Show Config", SubviewOpen(SubviewId.SHOW_CONFIG)),
            FieldDef("poco.restart_relay", "Restart Relay", ActionTrigger("restart_relay")),
        ]

    if section == WorkspaceSection.LANGUAGE:
        current = str(config.get("ui", {}).get("language", "en")).strip() or "en"
        return [
            FieldDef(
                "ui.language",
                "Language",
                ChoiceSelect(_non_empty_choice_labels(["en", "zh"], current)),
            ),
        ]

    if section == WorkspaceSection.AGENT:
        codex_model = str(config.get("codex", {}).get("model", "")).strip()
        fields = [
            FieldDef("group.codex", "Codex", ReadOnly()),
            FieldDef("codex.bin", "Bin", TextInput()),
            FieldDef("codex.app_server_args", "App Server Args", TextInput()),
            FieldDef("codex.model", "Model", ChoiceSelect(_non_empty_choice_labels(model_choices("codex"), codex_model))),
            FieldDef(
                "codex.reasoning_effort",
                "Reasoning",
                ChoiceSelect(_non_empty_choice_labels(["minimal", "low", "medium", "high", "xhigh"], str(config.get("codex", {}).get("reasoning_effort", "")).strip())),
            ),
            FieldDef("codex.approval_policy", "Approval Policy", TextInput()),
            FieldDef("codex.sandbox", "Sandbox", TextInput()),
            FieldDef("group.claude", "Claude", ReadOnly()),
            FieldDef("claude.bin", "Bin", TextInput()),
            FieldDef("claude.app_server_args", "App Server Args", TextInput()),
            FieldDef("claude.approval_policy", "Approval Policy", TextInput()),
            FieldDef("claude.sandbox", "Sandbox", TextInput()),
            FieldDef("claude.manage_backends", "Manage Backends", SubviewOpen(SubviewId.CLAUDE_BACKENDS)),
            FieldDef("claude.backend_settings", "Backend Settings", SubviewOpen(SubviewId.CLAUDE_BACKEND_SETTINGS)),
        ]
        return fields

    return []
