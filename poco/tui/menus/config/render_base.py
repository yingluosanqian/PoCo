"""Base helpers shared by config renderers."""

from __future__ import annotations


class BaseConfigRenderer:
    """Provides common formatting helpers for config views."""

    def __init__(self, app) -> None:
        """Initializes the renderer.

        Args:
            app: The owning ``PoCoTui`` instance.
        """
        self.app = app

    def breadcrumb_parts(self) -> list[str]:
        """Builds the breadcrumb path for the current config screen."""
        if self.app._config_level == "sections":
            return []
        if self.app._config_group:
            parts = [self.setting_option_label(self.app._config_group)]
        elif self.app._config_section == "language" or self.app._config_editing_path == "ui.language":
            parts = [self.setting_option_label("language")]
        else:
            parts = []
        if self.app._config_group:
            if self.app._config_level == "group_sections":
                return parts
        if self.app._config_level == "group_sections":
            return parts
        if self.app._config_level == "show":
            return parts + ["show"]
        if self.app._config_section:
            section_label = self.setting_option_label(self.app._config_section)
            if not parts or parts[-1] != section_label:
                parts.append(section_label)
        if self.app._config_level == "fields":
            return parts
        if self.app._config_level == "claude_backends":
            return parts
        if self.app._config_level == "claude_custom_fields":
            parts.append(self.app._t("add_custom_backend"))
            return parts
        if self.app._claude_backend_name:
            parts.append(self.app._claude_backend_name)
        if self.app._config_level == "claude_backend_fields":
            return parts
        if self.app._config_level in {"claude_backend_models", "claude_backend_model_actions"}:
            parts.append(self.app._t("model"))
        if self.app._config_level in {"extra_env_list", "extra_env_actions"}:
            parts.append(self.app._t("extra_env"))
        if self.app._config_level == "extra_env_actions" and self.app._extra_env_key:
            parts.append(self.app._extra_env_key)
        if self.app._config_level in {"choices", "input"} and self.app._config_editing_path:
            parts.append(self.app._config_editing_path.split(".")[-1])
        return parts

    def setting_option_label(self, option: str) -> str:
        """Maps an internal option key to a user-facing label."""
        labels = {
            "language": self.app._t("language"),
            "bot": self.app._t("bot"),
            "agent": self.app._t("agent"),
            "poco": self.app._t("poco"),
            "show": "show",
            "feishu": "feishu",
            "codex": "codex",
            "claude": "claude",
            "bridge": self.app._t("relay"),
        }
        return labels.get(option, option)

    def menu_option_label(self, config: dict, option: str) -> str:
        """Formats a top-level config menu entry with summary state."""
        label = self.setting_option_label(option)
        if option in {"bot", "agent", "poco"}:
            return label
        if option == "language":
            code = str(config.get("ui", {}).get("language", "en")).strip() or "en"
            return f"{label} ({code})"
        if option == "codex":
            model = str((config.get("codex", {}) or {}).get("model", "")).strip()
            return f"{label} (default: {model})" if model else f"{label} (default: unset)"
        if option != "claude":
            return label
        claude = config.get("claude", {}) or {}
        default_backend = str(claude.get("default_backend", "anthropic"))
        backends = claude.get("backends", {}) or {}
        backend_payload = backends.get(default_backend, {}) or {}
        default_model = str(backend_payload.get("default_model", "")).strip()
        return f"{label} (default: {default_model})" if default_model else f"{label} (default: unset)"

    @staticmethod
    def language_label(code: str) -> str:
        """Maps a language code to a display label."""
        return "中文" if code == "zh" else "English"

    def display_config_value(self, config: dict, path: str) -> str:
        """Formats a config value for safe on-screen display."""
        current = self.app._lookup_nested(config, path)
        if not current:
            return self.app._t("empty")
        if "secret" in path or "token" in path:
            return self.app._t("secret_value")
        return current

    def display_claude_backend_value(self, backend_payload: dict, field_key: str) -> str:
        """Formats a Claude backend field value for display."""
        value = backend_payload.get(field_key, "")
        if not value:
            return self.app._t("empty")
        if field_key == "auth_token":
            return self.app._t("secret_value")
        if field_key == "extra_env":
            if isinstance(value, dict):
                return f"{len(value)} item(s)"
            return self.app._t("empty")
        return str(value)
