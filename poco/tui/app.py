"""Main Textual application shell for the PoCo TUI."""

import json

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Input, Static

from .. import __version__
from ..config import config_ready, missing_required_config_paths
from ..providers import model_choices
from .resources import POCO_ICON, STRINGS, TUI_CSS
from .menus.config import (
    LANGUAGE_CHOICES,
    ConfigMenuController,
    ConfigPanelRenderer,
    ConfigScreenState,
    OptionMenuState,
)
from .menus import ROOT_MENU_OPTIONS, RootMenuController


class PoCoTui(App[None]):
    """Terminal UI shell for PoCo."""
    CSS = TUI_CSS

    BINDINGS = [
        Binding("q", "config_back", "Back"),
        Binding("up", "cursor_up", "Up"),
        Binding("down", "cursor_down", "Down"),
        Binding("enter", "activate", "Open"),
        Binding("escape", "config_back", "Back"),
        Binding("ctrl+r", "save_and_restart", "Save & Restart"),
    ]

    def __init__(self, service, *, focus_config: bool = False) -> None:
        """Initializes the TUI shell.

        Args:
            service: Runtime service facade used by the UI.
            focus_config: Whether to enter config mode immediately on startup.
        """
        super().__init__()
        self._service = service
        self._focus_config = focus_config
        self._view = "menu"
        self._root_selected = 0
        self._config_stack: list[ConfigScreenState] = []
        self._show_scroll = 0
        self._message_override = ""
        self._root_menu = RootMenuController(self)
        self._config_menu = ConfigMenuController(self)
        self._config_renderer = ConfigPanelRenderer(self)

    def _lang(self) -> str:
        """Returns the current UI language code."""
        config = self._service.load_config()
        lang = config.get("ui", {}).get("language", "en")
        return "zh" if lang == "zh" else "en"

    def _t(self, key: str, **kwargs) -> str:
        """Looks up and formats a translated UI string."""
        lang = self._lang()
        template = STRINGS[key][lang]
        return template.format(**kwargs)

    @property
    def _config_menu_active(self) -> bool:
        """Returns whether the config navigation stack is active."""
        return bool(self._config_stack)

    def _config_state(self) -> ConfigScreenState | None:
        """Returns the active config stack frame, if any."""
        return self._config_stack[-1] if self._config_stack else None

    def _push_config_state(self, state: ConfigScreenState) -> None:
        """Pushes a config screen state onto the navigation stack."""
        self._config_stack.append(state)

    def _pop_config_state(self) -> ConfigScreenState | None:
        """Pops one config screen state from the navigation stack."""
        return self._config_stack.pop() if self._config_stack else None

    def _current_config_section_name(self) -> str | None:
        """Returns the nearest selected config section in the stack."""
        for state in reversed(self._config_stack):
            if state.section:
                return state.section
        return None

    def _current_config_group_name(self) -> str | None:
        """Returns the nearest selected config group in the stack."""
        for state in reversed(self._config_stack):
            if state.group:
                return state.group
        return None

    def _current_claude_backend_name(self) -> str | None:
        """Returns the currently selected Claude backend name, if any."""
        for state in reversed(self._config_stack):
            if state.backend:
                return state.backend
        return None

    def _current_custom_draft(self) -> dict | None:
        """Returns the active in-memory draft for a custom backend."""
        for state in reversed(self._config_stack):
            if state.draft is not None:
                return state.draft
        return None

    def _claude_backend_entries(self, config: dict) -> list[tuple[str, str]]:
        """Returns visible Claude backend entries for the current config."""
        return self._config_menu.claude.backend_entries(config)

    def _claude_backend_field_defs(self, backend_name: str) -> list[tuple[str, str]]:
        """Returns editable field definitions for one Claude backend."""
        return self._config_menu.claude.backend_field_defs(backend_name)

    @property
    def _config_level(self) -> str:
        """Returns the active config screen kind."""
        state = self._config_state()
        return state.kind if state else "sections"

    @_config_level.setter
    def _config_level(self, value: str) -> None:
        """Sets the active config screen kind on the current stack frame."""
        state = self._config_state()
        if state is None:
            self._config_stack = [ConfigScreenState(kind=value)]
        else:
            state.kind = value

    @property
    def _config_selected(self) -> int:
        """Returns the active selection index for the current config screen."""
        state = self._config_state()
        return state.selected if state else 0

    @_config_selected.setter
    def _config_selected(self, value: int) -> None:
        """Updates the selection index for the current config screen."""
        state = self._config_state()
        if state is None:
            self._config_stack = [ConfigScreenState(kind="sections", selected=value)]
        else:
            state.selected = value

    _config_field_selected = _config_selected
    _config_choice_selected = _config_selected
    _claude_backend_selected = _config_selected
    _claude_backend_field_selected = _config_selected
    _claude_backend_model_selected = _config_selected
    _claude_backend_model_action_selected = _config_selected
    _extra_env_selected = _config_selected
    _extra_env_action_selected = _config_selected

    @property
    def _config_section(self) -> str | None:
        """Returns the selected config section name."""
        return self._current_config_section_name()

    @_config_section.setter
    def _config_section(self, value: str | None) -> None:
        """Stores the selected config section on the current stack frame."""
        state = self._config_state()
        if state is None:
            self._config_stack = [ConfigScreenState(kind="sections", section=value)]
        else:
            state.section = value

    @property
    def _config_group(self) -> str | None:
        """Returns the selected config group name."""
        return self._current_config_group_name()

    @_config_group.setter
    def _config_group(self, value: str | None) -> None:
        """Stores the selected config group on the current stack frame."""
        state = self._config_state()
        if state is None:
            self._config_stack = [ConfigScreenState(kind="sections", group=value)]
        else:
            state.group = value

    @property
    def _config_editing_path(self) -> str | None:
        """Returns the config path currently being edited."""
        state = self._config_state()
        return state.path if state else None

    @_config_editing_path.setter
    def _config_editing_path(self, value: str | None) -> None:
        """Stores the config path currently being edited."""
        state = self._config_state()
        if state is None:
            self._config_stack = [ConfigScreenState(kind="input", path=value)]
        else:
            state.path = value

    @property
    def _claude_backend_name(self) -> str | None:
        """Returns the selected Claude backend name."""
        return self._current_claude_backend_name()

    @_claude_backend_name.setter
    def _claude_backend_name(self, value: str | None) -> None:
        """Stores the selected Claude backend on the current stack frame."""
        state = self._config_state()
        if state is None:
            self._config_stack = [ConfigScreenState(kind="claude_backends", backend=value)]
        else:
            state.backend = value

    @property
    def _claude_backend_model_name(self) -> str | None:
        """Returns the selected Claude backend model name, if any."""
        for state in reversed(self._config_stack):
            if state.model:
                return state.model
        return None

    @_claude_backend_model_name.setter
    def _claude_backend_model_name(self, value: str | None) -> None:
        """Stores the selected Claude backend model on the current stack frame."""
        state = self._config_state()
        if state is None:
            self._config_stack = [ConfigScreenState(kind="claude_backend_models", model=value)]
        else:
            state.model = value

    @property
    def _extra_env_key(self) -> str | None:
        """Returns the selected extra-env key, if any."""
        for state in reversed(self._config_stack):
            if state.env_key:
                return state.env_key
        return None

    @_extra_env_key.setter
    def _extra_env_key(self, value: str | None) -> None:
        """Stores the selected extra-env key on the current stack frame."""
        state = self._config_state()
        if state is None:
            self._config_stack = [ConfigScreenState(kind="extra_env_list", env_key=value)]
        else:
            state.env_key = value

    @property
    def _input_mode(self) -> str | None:
        """Returns the active config input sub-mode, if any."""
        state = self._config_state()
        return state.input_mode if state else None

    @_input_mode.setter
    def _input_mode(self, value: str | None) -> None:
        """Stores the active config input sub-mode."""
        state = self._config_state()
        if state is None:
            self._config_stack = [ConfigScreenState(kind="input", input_mode=value)]
        else:
            state.input_mode = value

    def _current_option_menu(self) -> OptionMenuState | None:
        """Returns the option menu currently driven by arrow-key navigation."""
        state = self._config_state()
        if state is not None:
            return self._config_menu.current_option_menu()
        if self._view == "menu":
            return OptionMenuState("root", self._root_selected, len(ROOT_MENU_OPTIONS))
        return None

    def _set_current_option_selected(self, index: int) -> None:
        """Updates the highlighted option index for the active menu."""
        state = self._config_state()
        if state is not None:
            state.selected = index
            return
        if self._view == "menu":
            self._root_selected = index

    @staticmethod
    def _lookup_nested(config: dict, path: str) -> str:
        """Looks up a dotted config path and returns a display-safe string."""
        value = config
        for part in path.split("."):
            if not isinstance(value, dict):
                return ""
            value = value.get(part, "")
        return str(value or "")

    @staticmethod
    def _missing_config_field_name(path: str) -> str:
        """Returns a short human-readable field name for one required path."""
        mapping = {
            "feishu.app_id": "app_id",
            "feishu.app_secret": "app_secret",
        }
        return mapping.get(path, path)

    def _missing_config_fields_text(self, config: dict) -> str:
        """Returns a compact comma-separated summary of missing required fields."""
        return ", ".join(
            self._missing_config_field_name(path)
            for path in missing_required_config_paths(config)
        )

    def compose(self) -> ComposeResult:
        """Builds the Textual widget tree."""
        with Horizontal(id="main_panel"):
            with Container(id="left_card", classes="card"):
                yield Static("", id="left_text")
            with Container(id="right_card", classes="card"):
                yield Static("", id="right_text")
        with Container(id="command_panel"):
            yield Input(id="command_input", placeholder="")
        yield Static("", id="message_line")

    def on_mount(self) -> None:
        """Bootstraps the initial TUI state after mount."""
        self.title = "PoCo"
        self.sub_title = self._t("app_title")
        self._refresh_runtime()
        self.set_interval(1.0, self._refresh_runtime)
        self.call_after_refresh(self._boot)

    def _boot(self) -> None:
        """Starts the initial view and launches the relay when ready."""
        config = self._service.load_config()
        if self._focus_config or not config_ready(config):
            self._enter_config_mode()
            missing = self._missing_config_fields_text(config)
            if missing:
                self._set_message(self._t("config_missing", fields=missing))
            else:
                self._set_message(self._t("config_required"))
            return
        self._service.start_relay()
        self._set_message(self._t("relay_started"), transient=True)
        self._sync_input_state()

    def _refresh_runtime(self) -> None:
        """Refreshes both panels from current runtime state."""
        config = self._service.load_config()
        relay = self._service.relay_status()
        self.sub_title = self._t("app_title")
        self.query_one("#left_text", Static).update(self._left_panel_text(config, relay))
        self.query_one("#right_text", Static).update(self._right_panel_text(config, relay))
        self._refresh_message_line()
        self._sync_input_state()

    def _left_panel_text(self, config: dict, relay: dict) -> str:
        """Builds the left summary panel text."""
        relay_status = self._t("running") if relay["running"] else self._t("stopped")
        relay_style = "#3fb950" if relay["running"] else "#f85149"
        config_status = self._t("ready") if config_ready(config) else self._t("needs_config")
        config_style = "#3fb950" if config_ready(config) else "#f2cc60"
        lines = [
            f"[bold #fb923c]{POCO_ICON}[/]\n"
            f"[bold #fb923c]PoCo v{__version__}[/]\n"
            "\n"
            f"{self._t('relay')}: [bold {relay_style}]{relay_status}[/]\n"
            f"{self._t('settings')}: [bold {config_style}]{config_status}[/]"
        ]
        if not config_ready(config):
            missing = self._missing_config_fields_text(config)
            if missing:
                lines.append("")
                lines.append(f"[bold #f2cc60]{self._t('missing_label')}[/]: [#f2cc60]{missing}[/]")
        return "\n".join(lines)

    def _right_panel_text(self, config: dict, relay: dict) -> str:
        """Builds the right panel text for the current view."""
        if self._config_menu_active:
            return self._config_panel_text(config)
        return self._menu_text(relay)

    def _panel_prefix(
        self,
        title: str,
        *,
        breadcrumb_parts: list[str] | None = None,
        help_text: str | None = None,
        heading: str | None = None,
        extra_lines: list[str] | None = None,
    ) -> list[str]:
        """Builds a shared header block for right-panel screens."""
        lines = [f"[bold #fb923c]{title}[/]"]
        if breadcrumb_parts:
            lines.append(f"[#8b949e]{self._t('path')}: {' / '.join(breadcrumb_parts)}[/]")
        if help_text:
            lines.append(f"[#8b949e]{help_text}[/]")
        if heading:
            lines.append(f"[bold #fb923c]{heading}[/]")
        if extra_lines:
            lines.extend(extra_lines)
        return lines

    def _config_breadcrumb_parts(self) -> list[str]:
        """Returns breadcrumb parts for the active config view."""
        return self._config_renderer.breadcrumb_parts()

    def _menu_text(self, relay: dict) -> str:
        """Renders the root menu panel."""
        selected = ROOT_MENU_OPTIONS[self._root_selected]
        descriptions = {
            "agent": self._t("menu_agent_desc"),
            "bot": self._t("menu_bot_desc"),
            "poco": self._t("menu_poco_desc"),
            "language": self._t("menu_language_desc"),
            "quit": self._t("menu_quit_desc"),
        }
        prefix = self._panel_prefix(
            self._t("menu"),
            breadcrumb_parts=[self._t("menu"), self._menu_label(selected)],
        )
        entry_lines = []
        for index, option in enumerate(ROOT_MENU_OPTIONS):
            label = self._menu_label(option)
            if index == self._root_selected:
                entry_lines.append(f"[bold #0f1117 on #fb923c]  {label}  [/]")
            else:
                entry_lines.append(f"  {label}")
        suffix = [f"[#8b949e]{descriptions[selected]}[/]"]
        return self._render_windowed_options(entry_lines, self._root_selected, prefix_lines=prefix, suffix_lines=suffix)

    def _footer_hint_text(self) -> str:
        """Builds the footer hint text for the current navigation state."""
        hint_key = "nav_hint_config" if self._config_menu_active else "nav_hint_menu"
        return self._t(hint_key)

    def _config_panel_text(self, config: dict) -> str:
        """Delegates config rendering to the config menu renderer."""
        return self._config_menu.render(config)

    def _config_menu_text(self, config: dict) -> str:
        """Renders the top-level config section list."""
        return self._config_renderer.render_menu(config)

    def _config_group_text(self, config: dict) -> str:
        """Renders the active config group list."""
        return self._config_renderer.render_group(config)

    def _config_fields_text(self, config: dict) -> str:
        """Renders fields for the currently selected config section."""
        return self._config_renderer.render_fields(config)

    def _claude_backends_text(self, config: dict) -> str:
        """Renders the Claude backend list."""
        return self._config_renderer.render_claude_backends(config)

    def _claude_custom_fields_text(self) -> str:
        """Renders fields for the in-progress custom Claude backend draft."""
        return self._config_renderer.render_claude_custom_fields()

    def _claude_backend_fields_text(self, config: dict) -> str:
        """Renders editable fields for the selected Claude backend."""
        return self._config_renderer.render_claude_backend_fields(config)

    def _claude_backend_models_text(self, config: dict) -> str:
        """Renders selectable models for the selected Claude backend."""
        return self._config_renderer.render_claude_backend_models(config)

    def _claude_backend_model_actions_text(self, config: dict) -> str:
        """Renders actions for the currently selected Claude model."""
        return self._config_renderer.render_claude_backend_model_actions(config)

    def _extra_env_payload(self, config: dict) -> dict[str, str]:
        """Returns the normalized extra-env mapping for the active backend."""
        return self._config_renderer.extra_env_payload(config)

    def _extra_env_entries(self, config: dict) -> list[tuple[str, str]]:
        """Returns visible extra-env menu entries for the active backend."""
        return self._config_renderer.extra_env_entries(config)

    def _extra_env_list_text(self, config: dict) -> str:
        """Renders the extra-env key list."""
        return self._config_renderer.render_extra_env_list(config)

    def _extra_env_actions_text(self, config: dict) -> str:
        """Renders actions for the selected extra-env item."""
        return self._config_renderer.render_extra_env_actions(config)

    def _config_choices_text(self, config: dict) -> str:
        """Renders a generic config choice list."""
        return self._config_renderer.render_choices(config)

    def _config_input_text(self, config: dict) -> str:
        """Renders the generic config text-input screen."""
        return self._config_renderer.render_input(config)

    def _menu_label(self, option: str) -> str:
        """Returns the user-facing label for a root menu option."""
        if option == "language":
            config = self._service.load_config()
            current = config.get("ui", {}).get("language", "en")
            return f"{self._t('language')} ({current})"
        labels = {
            "agent": self._t("agent"),
            "bot": self._t("bot"),
            "poco": self._t("poco"),
            "quit": "Quit",
            "show": "show",
            "menu": self._t("dashboard"),
        }
        return labels.get(option, option)

    def _show_lines(self, config: dict | None = None) -> list[str]:
        """Returns formatted lines for the scrollable config view."""
        try:
            payload = config if config is not None else self._service.masked_config()
            config_text = json.dumps(payload, ensure_ascii=False, indent=2)
        except Exception as exc:
            return [self._t("current_config"), "", f"Failed to render config: {exc}"]
        return [self._t("current_config"), ""] + config_text.splitlines()

    def _show_window_height(self) -> int:
        """Estimates the available line budget for right-panel scrolling."""
        try:
            height = self.query_one("#right_text", Static).size.height or self.query_one("#right_card", Container).size.height
        except Exception:
            height = 0
        return max(10, height - 2 if height else 24)

    def _render_windowed_options(
        self,
        entries: list[str],
        selected: int,
        *,
        prefix_lines: list[str],
        suffix_lines: list[str] | None = None,
    ) -> str:
        """Renders a scrollable option list around the selected row."""
        suffix = suffix_lines or []
        window_height = self._show_window_height()
        available = max(1, window_height - len(prefix_lines) - len(suffix))
        start = max(0, min(selected - (available // 2), max(0, len(entries) - available)))
        end = min(len(entries), start + available)
        visible = entries[start:end]
        lines = list(prefix_lines)
        if start > 0:
            lines.append("[#8b949e]  ...[/]")
        lines.extend(visible)
        if end < len(entries):
            lines.append("[#8b949e]  ...[/]")
        lines.extend(suffix)
        return "\n".join(lines)

    def _show_max_scroll(self, config: dict | None = None) -> int:
        """Returns the maximum scroll offset for the config-file view."""
        lines = self._show_lines(config)
        return max(0, len(lines) - self._show_window_height())

    def _show_text(self, config: dict | None = None) -> str:
        """Renders the scrollable config file view."""
        lines = self._show_lines(config)
        max_scroll = self._show_max_scroll(config)
        self._show_scroll = max(0, min(self._show_scroll, max_scroll))
        start = self._show_scroll
        end = min(len(lines), start + self._show_window_height())
        visible = lines[start:end]
        rendered = []
        for index, line in enumerate(visible):
            if start + index == 0:
                rendered.append(f"[bold #fb923c]{line}[/]")
            else:
                rendered.append(line)
        status = self._t("scroll_status", start=start + 1 if lines else 0, end=end, total=len(lines))
        rendered.extend(["", f"[#8b949e]{self._t('show_scroll')}[/]", f"[#8b949e]{status}[/]"])
        return "\n".join(rendered)

    def _setting_option_label(self, option: str) -> str:
        """Returns the display label for a config setting option."""
        return self._config_renderer.setting_option_label(option)

    def _config_menu_option_label(self, config: dict, option: str) -> str:
        """Returns the display label for one top-level config menu option."""
        return self._config_renderer.menu_option_label(config, option)

    def _language_label(self, code: str) -> str:
        """Returns the display label for a language code."""
        return self._config_renderer.language_label(code)

    def _display_config_value(self, config: dict, path: str) -> str:
        """Formats one config value for display in menus and forms."""
        return self._config_renderer.display_config_value(config, path)

    def _display_claude_backend_value(self, backend_payload: dict, field_key: str) -> str:
        """Formats one Claude backend field for display."""
        return self._config_renderer.display_claude_backend_value(backend_payload, field_key)

    @staticmethod
    def _model_choices(provider_name: str, backend_name: str | None = None) -> list[str]:
        """Returns predefined model choices for one provider/backend pair."""
        return model_choices(provider_name, backend_name)

    def _choices_for_path(self, path: str) -> list[tuple[str, str]]:
        """Returns predefined menu choices for a config path."""
        if path == "ui.language":
            return LANGUAGE_CHOICES
        if path == "codex.model":
            return [(item, item) for item in self._model_choices("codex")]
        if path == "codex.reasoning_effort":
            return [
                ("none", "none"),
                ("minimal", "minimal"),
                ("low", "low"),
                ("medium", "medium"),
                ("high", "high"),
                ("xhigh", "xhigh"),
            ]
        if path == "feishu.allow_all_users":
            return [("true", "true"), ("false", "false")]
        return []

    def _save_extra_env_payload(self, payload: dict[str, str]) -> None:
        """Saves extra environment variables for the active Claude backend."""
        assert self._claude_backend_name is not None
        self._service.set_config_value(
            f"claude.backends.{self._claude_backend_name}.extra_env",
            json.dumps(payload, ensure_ascii=False),
        )

    def _is_sensitive_input(self) -> bool:
        """Returns whether the active input field should be masked."""
        path = self._config_editing_path or ""
        lowered_path = path.lower()
        if "secret" in lowered_path or "token" in lowered_path:
            return True
        if self._input_mode == "extra_env_value" and self._extra_env_key:
            key = self._extra_env_key.lower()
            sensitive_markers = ("token", "secret", "key", "password", "auth")
            return any(marker in key for marker in sensitive_markers)
        return False

    def action_save_and_restart(self) -> None:
        """Restarts the application process."""
        self.exit("restart")

    def action_quit(self) -> None:
        """Routes the ``q`` key to one-level-back navigation."""
        self.action_config_back()

    def action_activate(self) -> None:
        """Activates the currently selected menu entry."""
        self._clear_message()
        if self._config_menu_active:
            self._config_menu.activate()
            return
        if self._view == "menu":
            self._root_menu.activate()

    def action_config_back(self) -> None:
        """Moves back one level in the current navigation flow."""
        if not self._config_menu_active:
            return
        self._clear_message()
        self._config_menu.back()

    def action_cursor_up(self) -> None:
        """Moves the active selection up."""
        self._clear_message()
        menu = self._current_option_menu()
        if menu is not None:
            if menu.count > 0:
                self._set_current_option_selected((menu.selected - 1) % menu.count)
                self._refresh_runtime()
            return
        if self._config_menu_active and self._config_level == "show":
            self._show_scroll = max(0, self._show_scroll - 1)
            self._refresh_runtime()
            return

    def action_cursor_down(self) -> None:
        """Moves the active selection down."""
        self._clear_message()
        menu = self._current_option_menu()
        if menu is not None:
            if menu.count > 0:
                self._set_current_option_selected((menu.selected + 1) % menu.count)
                self._refresh_runtime()
            return
        if self._config_menu_active and self._config_level == "show":
            self._show_scroll = min(self._show_max_scroll(), self._show_scroll + 1)
            self._refresh_runtime()
            return

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Processes text submitted through the bottom input field."""
        if event.input.id != "command_input":
            return
        command = event.value.strip()
        if self._config_menu_active:
            event.input.value = ""
            if self._config_level == "input":
                if not command:
                    self._set_message(self._t("enter_value_or_quit"))
                else:
                    if self._input_mode == "extra_env_key":
                        config = self._service.load_config()
                        payload = self._extra_env_payload(config)
                        key = command.strip()
                        if not key:
                            self._set_message(self._t("enter_value_or_quit"))
                            return
                        if key in payload:
                            self._set_message(self._t("env_key_exists"))
                            return
                        self._extra_env_key = key
                        self._config_editing_path = f"claude.backends.{self._claude_backend_name}.extra_env.{key}"
                        self._input_mode = "extra_env_value"
                        self._refresh_runtime()
                        self._set_message(self._t("env_key_saved", key=key))
                        return
                    if self._input_mode == "extra_env_value":
                        config = self._service.load_config()
                        payload = self._extra_env_payload(config)
                        assert self._extra_env_key is not None
                        payload[self._extra_env_key] = command
                        self._save_extra_env_payload(payload)
                        key = self._extra_env_key
                        self._pop_config_state()
                        if self._config_level == "input":
                            self._pop_config_state()
                        self._refresh_runtime()
                        self._set_message(self._t("env_saved", key=key))
                        return
                    if self._input_mode == "claude_custom_field":
                        draft = self._current_custom_draft()
                        field = (self._config_editing_path or "").split(".")[-1]
                        if draft is not None and field:
                            draft[field] = command.strip()
                        self._pop_config_state()
                        self._refresh_runtime()
                        self._set_message(self._t("value_saved", field=field))
                        return
                    assert self._config_editing_path is not None
                    field = self._config_editing_path
                    self._service.set_config_value(field, command)
                    self._pop_config_state()
                    self._refresh_runtime()
                    self._set_message(f"{self._t('value_saved', field=field)} {self._t('restart_required')}")
                return
            self._set_message(self._t("input_disabled"))
            return
        event.input.value = ""
        self._set_message(self._t("input_disabled"))

    def _enter_config_mode(self) -> None:
        """Enters config mode programmatically."""
        self._root_selected = 0
        self._root_menu.activate()

    def _exit_config_mode(self) -> None:
        """Leaves config mode programmatically."""
        self._config_menu.exit()

    def _sync_input_state(self) -> None:
        """Synchronizes input state, masking, and focus with the active screen."""
        input_widget = self.query_one("#command_input", Input)
        editable = self._config_menu_active and self._config_level == "input"
        input_widget.disabled = not editable
        input_widget.placeholder = ""
        input_widget.password = editable and self._is_sensitive_input()
        if editable:
            input_widget.focus()
        else:
            input_widget.value = ""

    def _set_message(self, message: str, *, transient: bool = False) -> None:
        """Updates the footer status line."""
        self._message_override = message
        self._refresh_message_line()
        if transient:
            self.set_timer(2.0, self._clear_message)

    def _clear_message(self) -> None:
        """Clears any temporary footer message and restores hints."""
        self._message_override = ""
        self._refresh_message_line()

    def _refresh_message_line(self) -> None:
        """Refreshes the footer line with either status or contextual hints."""
        text = self._message_override or self._footer_hint_text()
        self.query_one("#message_line", Static).update(text)
