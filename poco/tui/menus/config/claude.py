"""Claude-specific config controller and renderer."""

from __future__ import annotations

from ....providers import model_choices
from .render_base import BaseConfigRenderer
from .types import (
    ADD_CUSTOM_BACKEND,
    BUILTIN_CLAUDE_BACKENDS,
    CLAUDE_BACKEND_FIELDS,
    CLAUDE_CUSTOM_ADD_FIELDS,
    CLAUDE_MODEL_ACTIONS,
    CUSTOM_CLAUDE_BACKEND_FIELDS,
    EXTRA_ENV_ACTIONS,
    ConfigScreenState,
    OptionMenuState,
)


class ClaudeConfigController:
    """Controls Claude backend, model, and extra-env submenus."""

    SUPPORTED_KINDS = {
        "claude_backends",
        "claude_custom_fields",
        "claude_backend_fields",
        "claude_backend_models",
        "claude_backend_model_actions",
        "extra_env_list",
        "extra_env_actions",
    }

    def __init__(self, app) -> None:
        """Initializes the controller."""
        self.app = app
        self._option_handlers = {
            "claude_backends": self._option_claude_backends,
            "claude_custom_fields": self._option_claude_custom_fields,
            "claude_backend_fields": self._option_claude_backend_fields,
            "claude_backend_models": self._option_claude_backend_models,
            "claude_backend_model_actions": self._option_claude_backend_model_actions,
            "extra_env_list": self._option_extra_env_list,
            "extra_env_actions": self._option_extra_env_actions,
        }
        self._activate_handlers = {
            "claude_backends": self._activate_claude_backends,
            "claude_custom_fields": self._activate_claude_custom_fields,
            "claude_backend_fields": self._activate_claude_backend_fields,
            "claude_backend_models": self._activate_claude_backend_models,
            "claude_backend_model_actions": self._activate_claude_backend_model_actions,
            "extra_env_list": self._activate_extra_env_list,
            "extra_env_actions": self._activate_extra_env_actions,
        }

    def handles(self, kind: str) -> bool:
        """Returns whether this controller owns the given screen kind."""
        return kind in self.SUPPORTED_KINDS

    def backend_entries(self, config: dict) -> list[tuple[str, str]]:
        """Builds visible Claude backend menu entries."""
        claude = config.get("claude", {}) or {}
        backends = claude.get("backends", {}) or {}
        default_backend = str(claude.get("default_backend", BUILTIN_CLAUDE_BACKENDS[0])).strip() or BUILTIN_CLAUDE_BACKENDS[0]
        entries: list[tuple[str, str]] = []
        for backend in BUILTIN_CLAUDE_BACKENDS:
            label = f"{backend} (default)" if backend == default_backend else backend
            entries.append((backend, label))
        custom_names = sorted(name for name in backends.keys() if name not in BUILTIN_CLAUDE_BACKENDS and name != "custom")
        for backend in custom_names:
            label = f"{backend} (default)" if backend == default_backend else backend
            entries.append((backend, label))
        entries.append((ADD_CUSTOM_BACKEND, self.app._t("add_custom_backend")))
        return entries

    def backend_field_defs(self, backend_name: str) -> list[tuple[str, str]]:
        """Returns field definitions for a backend detail screen."""
        if backend_name in BUILTIN_CLAUDE_BACKENDS:
            return CLAUDE_BACKEND_FIELDS
        return CUSTOM_CLAUDE_BACKEND_FIELDS

    @staticmethod
    def is_valid_custom_backend_name(name: str) -> bool:
        """Validates a custom backend identifier."""
        return bool(name) and all(char.isalnum() or char in {"-", "_"} for char in name)

    @staticmethod
    def new_custom_backend_draft() -> dict:
        """Creates an empty draft for a new custom backend."""
        return {"name": "", "base_url": "", "auth_token": "", "model": ""}

    def select_backend_entry(self, backend_name: str) -> int:
        """Finds the visible index for a backend name."""
        entries = self.backend_entries(self.app._service.load_config())
        for index, (candidate, _label) in enumerate(entries):
            if candidate == backend_name:
                return index
        return 0

    def save_custom_backend(self, draft: dict) -> str:
        """Persists a custom backend draft into config storage."""
        name = str(draft.get("name", "")).strip()
        config = self.app._service.load_config()
        claude = config.setdefault("claude", {})
        backends = claude.setdefault("backends", {})
        backends[name] = {
            "base_url": str(draft.get("base_url", "")).strip(),
            "auth_token": str(draft.get("auth_token", "")).strip(),
            "default_model": str(draft.get("model", "")).strip(),
            "extra_env": {},
        }
        self.app._service.save_config(config)
        return name

    def current_option_menu(self, kind: str) -> OptionMenuState | None:
        """Returns the current option state for a Claude submenu."""
        handler = self._option_handlers.get(kind)
        return handler() if handler else None

    def activate(self, kind: str) -> None:
        """Dispatches Enter behavior for a Claude submenu."""
        handler = self._activate_handlers.get(kind)
        if handler:
            handler()

    def _option_claude_backends(self) -> OptionMenuState:
        count = len(self.backend_entries(self.app._service.load_config()))
        return OptionMenuState("claude_backends", self.app._claude_backend_selected, count)

    def _option_claude_custom_fields(self) -> OptionMenuState:
        return OptionMenuState("claude_custom_fields", self.app._config_selected, len(CLAUDE_CUSTOM_ADD_FIELDS))

    def _option_claude_backend_fields(self) -> OptionMenuState:
        backend_name = self.app._current_claude_backend_name() or BUILTIN_CLAUDE_BACKENDS[0]
        count = len(self.backend_field_defs(backend_name))
        return OptionMenuState("claude_backend_fields", self.app._claude_backend_field_selected, count)

    def _option_claude_backend_models(self) -> OptionMenuState:
        backend_name = self.app._current_claude_backend_name() or ""
        count = len(self.app._model_choices("claude", backend_name))
        return OptionMenuState("claude_backend_models", self.app._claude_backend_model_selected, count)

    def _option_claude_backend_model_actions(self) -> OptionMenuState:
        return OptionMenuState("claude_backend_model_actions", self.app._claude_backend_model_action_selected, len(CLAUDE_MODEL_ACTIONS))

    def _option_extra_env_list(self) -> OptionMenuState:
        count = len(self.app._extra_env_entries(self.app._service.load_config()))
        return OptionMenuState("extra_env_list", self.app._extra_env_selected, count)

    def _option_extra_env_actions(self) -> OptionMenuState:
        return OptionMenuState("extra_env_actions", self.app._extra_env_action_selected, len(EXTRA_ENV_ACTIONS))

    def _activate_claude_backends(self) -> None:
        config = self.app._service.load_config()
        backend_name, _label = self.backend_entries(config)[self.app._claude_backend_selected]
        if backend_name == ADD_CUSTOM_BACKEND:
            self.app._push_config_state(
                ConfigScreenState(kind="claude_custom_fields", group=self.app._config_group, section="claude", draft=self.new_custom_backend_draft())
            )
        else:
            self.app._push_config_state(
                ConfigScreenState(kind="claude_backend_fields", group=self.app._config_group, section="claude", backend=backend_name)
            )
        self.app._refresh_runtime()

    def _activate_claude_custom_fields(self) -> None:
        draft = self.app._current_custom_draft() or self.new_custom_backend_draft()
        field_key, _label = CLAUDE_CUSTOM_ADD_FIELDS[self.app._config_selected]
        if field_key == "confirm":
            name = str(draft.get("name", "")).strip()
            base_url = str(draft.get("base_url", "")).strip()
            auth_token = str(draft.get("auth_token", "")).strip()
            model = str(draft.get("model", "")).strip()
            if not all([name, base_url, auth_token, model]):
                self.app._set_message(self.app._t("claude_custom_required"))
                return
            if not self.is_valid_custom_backend_name(name):
                self.app._set_message(self.app._t("claude_custom_name_invalid"))
                return
            config = self.app._service.load_config()
            backends = ((config.get("claude", {}) or {}).get("backends", {}) or {})
            if name in backends:
                self.app._set_message(self.app._t("claude_custom_exists"))
                return
            saved_name = self.save_custom_backend(draft)
            self.app._pop_config_state()
            parent = self.app._config_state()
            if parent is not None and parent.kind == "claude_backends":
                parent.selected = self.select_backend_entry(saved_name)
            self.app._refresh_runtime()
            self.app._set_message(self.app._t("claude_custom_added", backend=saved_name))
            return

        self.app._push_config_state(
            ConfigScreenState(kind="input", group=self.app._config_group, section="claude", path=f"claude.custom.{field_key}", input_mode="claude_custom_field")
        )
        self.app._refresh_runtime()

    def _activate_claude_backend_fields(self) -> None:
        backend_name = self.app._claude_backend_name
        assert backend_name is not None
        field_defs = self.backend_field_defs(backend_name)
        field_key, _label = field_defs[self.app._claude_backend_field_selected]

        if field_key == "set_as_default":
            self.app._service.set_config_value("claude.default_backend", backend_name)
            self.app._refresh_runtime()
            self.app._set_message(self.app._t("set_default_done", backend=backend_name))
            return

        if field_key == "delete":
            config = self.app._service.load_config()
            claude = config.setdefault("claude", {})
            backends = claude.setdefault("backends", {})
            backends.pop(backend_name, None)
            if str(claude.get("default_backend", BUILTIN_CLAUDE_BACKENDS[0])).strip() == backend_name:
                claude["default_backend"] = BUILTIN_CLAUDE_BACKENDS[0]
            self.app._service.save_config(config)
            self.app._pop_config_state()
            parent = self.app._config_state()
            if parent is not None and parent.kind == "claude_backends":
                parent.selected = 0
            self.app._refresh_runtime()
            self.app._set_message(self.app._t("claude_backend_deleted", backend=backend_name))
            return

        if field_key == "model":
            choices = self.app._model_choices("claude", backend_name)
            if not choices:
                self.app._set_message(self.app._t("empty"))
                return
            self.app._push_config_state(
                ConfigScreenState(
                    kind="claude_backend_models",
                    group=self.app._config_group,
                    section="claude",
                    backend=backend_name,
                )
            )
            self.app._refresh_runtime()
            return

        if field_key == "extra_env":
            self.app._push_config_state(
                ConfigScreenState(
                    kind="extra_env_list",
                    group=self.app._config_group,
                    section="claude",
                    backend=backend_name,
                )
            )
            self.app._refresh_runtime()
            return

        self.app._push_config_state(
            ConfigScreenState(
                kind="input",
                group=self.app._config_group,
                section="claude",
                backend=backend_name,
                path=f"claude.backends.{backend_name}.{field_key}",
            )
        )
        self.app._refresh_runtime()

    def _activate_claude_backend_models(self) -> None:
        backend_name = self.app._claude_backend_name
        assert backend_name is not None
        choices = self.app._model_choices("claude", backend_name)
        if not choices:
            self.app._set_message(self.app._t("empty"))
            return
        model_name = choices[self.app._claude_backend_model_selected]
        self.app._push_config_state(
            ConfigScreenState(kind="claude_backend_model_actions", backend=backend_name, model=model_name)
        )
        self.app._refresh_runtime()

    def _activate_claude_backend_model_actions(self) -> None:
        backend_name = self.app._claude_backend_name
        model_name = self.app._claude_backend_model_name
        assert backend_name is not None and model_name is not None
        self.app._service.set_config_value(f"claude.backends.{backend_name}.default_model", model_name)
        self.app._pop_config_state()
        self.app._refresh_runtime()
        self.app._set_message(self.app._t("set_default_model_done", backend=backend_name, model=model_name))

    def _activate_extra_env_list(self) -> None:
        config = self.app._service.load_config()
        entries = self.app._extra_env_entries(config)
        key, _label = entries[self.app._extra_env_selected]
        if key == "__add__":
            self.app._push_config_state(ConfigScreenState(kind="input", input_mode="extra_env_key"))
            self.app._refresh_runtime()
            return
        self.app._push_config_state(ConfigScreenState(kind="extra_env_actions", env_key=key))
        self.app._refresh_runtime()

    def _activate_extra_env_actions(self) -> None:
        action, _label = EXTRA_ENV_ACTIONS[self.app._extra_env_action_selected]
        if action == "edit_value":
            self.app._push_config_state(ConfigScreenState(kind="input", input_mode="extra_env_value"))
            self.app._refresh_runtime()
            return

        config = self.app._service.load_config()
        payload = self.app._extra_env_payload(config)
        key = self.app._extra_env_key
        assert key is not None
        payload.pop(key, None)
        self.app._save_extra_env_payload(payload)
        self.app._pop_config_state()
        self.app._refresh_runtime()
        self.app._set_message(self.app._t("env_removed", key=key))


class ClaudeConfigRenderer(BaseConfigRenderer):
    """Renders all Claude-specific config screens."""

    def render_claude_backends(self, config: dict) -> str:
        """Renders the Claude backend list."""
        prefix = self.app._panel_prefix(
            self.app._t("config_mode"),
            breadcrumb_parts=self.breadcrumb_parts(),
            heading=self.app._t("backend"),
        )
        entry_lines = []
        for index, (_option, label) in enumerate(self.app._claude_backend_entries(config)):
            if index == self.app._claude_backend_selected:
                entry_lines.append(f"[bold #0f1117 on #fb923c]  {label}  [/]")
            else:
                entry_lines.append(f"  {label}")
        return self.app._render_windowed_options(entry_lines, self.app._claude_backend_selected, prefix_lines=prefix)

    def render_claude_custom_fields(self) -> str:
        """Renders the custom backend draft editor."""
        draft = self.app._current_custom_draft() or self.app._config_menu.claude.new_custom_backend_draft()
        prefix = self.app._panel_prefix(
            self.app._t("config_mode"),
            breadcrumb_parts=self.breadcrumb_parts(),
            heading=self.app._t("field"),
        )
        entry_lines = []
        for index, (field_key, label) in enumerate(CLAUDE_CUSTOM_ADD_FIELDS):
            if field_key == "confirm":
                text = self.app._t("confirm")
            else:
                current = str(draft.get(field_key, "")).strip() or self.app._t("empty")
                if field_key == "auth_token" and current != self.app._t("empty"):
                    current = self.app._t("secret_value")
                text = f"{label}: {current}"
            if index == self.app._config_selected:
                entry_lines.append(f"[bold #0f1117 on #fb923c]  {text}  [/]")
            else:
                entry_lines.append(f"  {text}")
        return self.app._render_windowed_options(entry_lines, self.app._config_selected, prefix_lines=prefix)

    def render_claude_backend_fields(self, config: dict) -> str:
        """Renders fields for a selected Claude backend."""
        assert self.app._claude_backend_name is not None
        backend_name = self.app._claude_backend_name
        backend_payload = (((config.get("claude", {}) or {}).get("backends", {}) or {}).get(backend_name, {}) or {})
        default_backend = str(config.get("claude", {}).get("default_backend", "anthropic"))
        field_defs = self.app._claude_backend_field_defs(backend_name)
        prefix = self.app._panel_prefix(
            self.app._t("config_mode"),
            breadcrumb_parts=self.breadcrumb_parts(),
            extra_lines=[f"[#8b949e]{self.app._t('backend')}: {backend_name}[/]"],
            heading=self.app._t("field"),
        )
        entry_lines = []
        for index, (field_key, label) in enumerate(field_defs):
            if field_key == "set_as_default":
                current = self.app._t("true") if backend_name == default_backend else self.app._t("false")
            elif field_key == "model":
                current = str(backend_payload.get("default_model", "")).strip() or self.app._t("empty")
            elif field_key == "delete":
                current = ""
            else:
                current = self.display_claude_backend_value(backend_payload, field_key)
            text = self.app._t("delete") if field_key == "delete" else f"{label}: {current}"
            if index == self.app._claude_backend_field_selected:
                entry_lines.append(f"[bold #0f1117 on #fb923c]  {text}  [/]")
            else:
                entry_lines.append(f"  {text}")
        suffix = []
        if backend_name == default_backend:
            suffix.extend(["", f"[#8b949e]{self.app._t('default_backend')}: {backend_name}[/]"])
        return self.app._render_windowed_options(
            entry_lines,
            self.app._claude_backend_field_selected,
            prefix_lines=prefix,
            suffix_lines=suffix,
        )

    def render_claude_backend_models(self, config: dict) -> str:
        """Renders the model list for the active Claude backend."""
        assert self.app._claude_backend_name is not None
        backend_name = self.app._claude_backend_name
        backend_payload = (((config.get("claude", {}) or {}).get("backends", {}) or {}).get(backend_name, {}) or {})
        current = str(backend_payload.get("default_model", "")).strip()
        choices = model_choices("claude", backend_name)
        prefix = self.app._panel_prefix(
            self.app._t("config_mode"),
            breadcrumb_parts=self.breadcrumb_parts(),
            extra_lines=[f"[#8b949e]{self.app._t('backend')}: {backend_name}[/]"],
            heading=self.app._t("model"),
        )
        entry_lines = []
        for index, item in enumerate(choices):
            label = f"{item} (default)" if item == current else item
            if index == self.app._claude_backend_model_selected:
                entry_lines.append(f"[bold #0f1117 on #fb923c]  {label}  [/]")
            else:
                entry_lines.append(f"  {label}")
        return self.app._render_windowed_options(
            entry_lines if entry_lines else ["[#8b949e]-[/]"],
            self.app._claude_backend_model_selected if entry_lines else 0,
            prefix_lines=prefix,
        )

    def render_claude_backend_model_actions(self, config: dict) -> str:
        """Renders actions for a specific Claude model."""
        assert self.app._claude_backend_name is not None
        assert self.app._claude_backend_model_name is not None
        backend_name = self.app._claude_backend_name
        model_name = self.app._claude_backend_model_name
        current = self.app._lookup_nested(config, f"claude.backends.{backend_name}.default_model")
        is_default = current == model_name
        prefix = self.app._panel_prefix(
            self.app._t("config_mode"),
            breadcrumb_parts=self.breadcrumb_parts() + ([model_name] if model_name else []),
            extra_lines=[
                f"[#8b949e]{self.app._t('backend')}: {backend_name}[/]",
                f"[#8b949e]{self.app._t('current_value')}: {current or self.app._t('empty')}[/]",
                "",
                f"[bold #fb923c]{self.app._t('model')}[/]",
                model_name,
            ],
            heading=self.app._t("commands"),
        )
        entry_lines = []
        for index, (_action_key, label) in enumerate(CLAUDE_MODEL_ACTIONS):
            text = f"{label}: {self.app._t('true') if is_default else self.app._t('false')}"
            if index == self.app._claude_backend_model_action_selected:
                entry_lines.append(f"[bold #0f1117 on #fb923c]  {text}  [/]")
            else:
                entry_lines.append(f"  {text}")
        return self.app._render_windowed_options(
            entry_lines,
            self.app._claude_backend_model_action_selected,
            prefix_lines=prefix,
        )

    def extra_env_payload(self, config: dict) -> dict[str, str]:
        """Returns normalized extra-env values for the active backend."""
        assert self.app._claude_backend_name is not None
        backend_payload = (((config.get("claude", {}) or {}).get("backends", {}) or {}).get(self.app._claude_backend_name, {}) or {})
        payload = backend_payload.get("extra_env", {}) or {}
        return {str(k): str(v) for k, v in payload.items()}

    def extra_env_entries(self, config: dict) -> list[tuple[str, str]]:
        """Builds visible extra-env list entries for the active backend."""
        payload = self.extra_env_payload(config)
        entries = [("__add__", self.app._t("add_env"))]
        for key in sorted(payload.keys()):
            entries.append((key, f"{key} = {payload[key]}"))
        return entries

    def render_extra_env_list(self, config: dict) -> str:
        """Renders the extra-env entry list."""
        assert self.app._claude_backend_name is not None
        entries = self.extra_env_entries(config)
        prefix = self.app._panel_prefix(
            self.app._t("config_mode"),
            breadcrumb_parts=self.breadcrumb_parts(),
            extra_lines=[f"[#8b949e]{self.app._t('backend')}: {self.app._claude_backend_name}[/]"],
            heading=self.app._t("extra_env"),
        )
        entry_lines = []
        for index, (_key, label) in enumerate(entries):
            if index == self.app._extra_env_selected:
                entry_lines.append(f"[bold #0f1117 on #fb923c]  {label}  [/]")
            else:
                entry_lines.append(f"  {label}")
        suffix = []
        if len(entries) == 1:
            suffix.extend(["", f"[#8b949e]{self.app._t('extra_env_empty')}[/]"])
        return self.app._render_windowed_options(
            entry_lines,
            self.app._extra_env_selected,
            prefix_lines=prefix,
            suffix_lines=suffix,
        )

    def render_extra_env_actions(self, config: dict) -> str:
        """Renders actions for the selected extra-env entry."""
        assert self.app._extra_env_key is not None
        payload = self.extra_env_payload(config)
        current = payload.get(self.app._extra_env_key, "")
        prefix = self.app._panel_prefix(
            self.app._t("config_mode"),
            breadcrumb_parts=self.breadcrumb_parts(),
            extra_lines=[f"[bold #fb923c]{self.app._extra_env_key}[/]", current],
            heading=self.app._t("commands"),
        )
        entry_lines = []
        for index, (_action, label_key) in enumerate(EXTRA_ENV_ACTIONS):
            label = self.app._t(label_key)
            if index == self.app._extra_env_action_selected:
                entry_lines.append(f"[bold #0f1117 on #fb923c]  {label}  [/]")
            else:
                entry_lines.append(f"  {label}")
        return self.app._render_windowed_options(entry_lines, self.app._extra_env_action_selected, prefix_lines=prefix)
