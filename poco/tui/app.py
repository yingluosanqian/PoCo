"""Main Textual application shell for the refactored PoCo TUI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import lark_oapi as lark
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Input, Static

from .. import __version__
from ..config import (
    ConfigStore,
    bind_workspace,
    build_paths,
    config_ready,
    ensure_dirs,
    missing_required_config_paths,
    saved_feishu_bots,
)
from .resources import POCO_ICON, STRINGS, TUI_CSS
from .sections import (
    ActionTrigger,
    ChoiceSelect,
    ReadOnly,
    SubviewOpen,
    TextInput,
    bot_advanced_fields,
    bot_display_name,
    claude_backend_setting_fields,
    current_claude_backend,
    display_config_value,
    section_fields,
)
from .state import (
    AppState,
    BindBotDraft,
    BindBotStep,
    BotAccount,
    ChoiceState,
    Platform,
    ScreenKind,
    SubviewId,
    WorkspaceSection,
)


class PoCoTui(App[None]):
    """Terminal UI shell for PoCo."""

    CSS = TUI_CSS

    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("up", "cursor_up", "Up"),
        Binding("down", "cursor_down", "Down"),
        Binding("left", "section_left", "Left"),
        Binding("right", "section_right", "Right"),
        Binding("enter", "activate", "Open"),
        Binding("escape", "back", "Back"),
        Binding("ctrl+r", "save_and_restart", "Save & Restart"),
    ]

    def __init__(self, service, *, service_factory: Callable[[str], object], focus_config: bool = False) -> None:
        super().__init__()
        self._service = service
        self._service_factory = service_factory
        self._focus_config = focus_config
        self._state = AppState()

    def compose(self) -> ComposeResult:
        with Horizontal(id="main_panel"):
            with Container(id="left_card", classes="card"):
                yield Static("", id="left_text")
            with Container(id="right_card", classes="card"):
                yield Static("", id="right_text")
        with Container(id="command_panel"):
            yield Input(id="command_input", placeholder="")
        yield Static("", id="message_line")

    def on_mount(self) -> None:
        self.title = "PoCo"
        self.sub_title = self._t("app_title")
        self._refresh_runtime_state()
        self.set_interval(1.0, self._tick)
        self.call_after_refresh(self._boot)

    def _tick(self) -> None:
        self._refresh_runtime_state()
        self._refresh_view()

    def _boot(self) -> None:
        config = self._service.load_config()
        self._enter_bind_bot(config)

    def _refresh_runtime_state(self) -> None:
        relay = self._service.relay_status()
        self._state.runtime.relay_running = bool(relay["running"])
        self._state.runtime.relay_error = str(relay.get("last_error", "") or "")

    def _refresh_view(self) -> None:
        config = self._service.load_config()
        self.query_one("#left_text", Static).update(self._left_panel_text(config))
        self.query_one("#right_text", Static).update(self._right_panel_text(config))
        self.query_one("#message_line", Static).update(self._footer_hint_text())
        self._sync_input_state()

    def _lang(self) -> str:
        config = self._service.load_config()
        lang = config.get("ui", {}).get("language", "en")
        return "zh" if lang == "zh" else "en"

    def _t(self, key: str, **kwargs) -> str:
        template = STRINGS[key][self._lang()]
        return template.format(**kwargs)

    def _active_binding_id(self, config: dict | None = None) -> str:
        payload = config if config is not None else self._service.load_config()
        configured_app_id = str(payload.get("feishu", {}).get("app_id", "")).strip()
        bound_bot = self._service.paths.instance if self._service.paths.instance != "default" else configured_app_id
        return bound_bot or ""

    @staticmethod
    def _truncate_bot_id(value: str) -> str:
        text = str(value or "").strip()
        if len(text) <= 16:
            return text
        return f"{text[:8]}…{text[-4:]}"

    def _bot_display_text(self, config: dict) -> str:
        display = bot_display_name(config)
        binding_id = self._active_binding_id(config)
        if not display:
            return self._t("unbound")
        if display == binding_id and binding_id:
            return self._truncate_bot_id(binding_id)
        if binding_id:
            return f"{display} · {self._truncate_bot_id(binding_id)}"
        return display

    def _bot_primary_text(self, config: dict) -> str:
        feishu = config.get("feishu", {})
        alias = str(feishu.get("alias", "")).strip()
        app_name = str(feishu.get("app_name", "")).strip()
        binding_id = self._active_binding_id(config)
        return alias or app_name or self._truncate_bot_id(binding_id) or self._t("unbound")

    def _saved_bot_accounts(self) -> list[BotAccount]:
        return [
            BotAccount(app_id=item.app_id, app_name=item.app_name, alias=item.alias)
            for item in saved_feishu_bots()
        ]

    def _current_workspace_section(self) -> WorkspaceSection:
        return self._state.workspace.active_section

    def _current_section_state(self):
        return self._state.workspace.sections[self._current_workspace_section()]

    def _current_fields(self, config: dict) -> list:
        return section_fields(config, self._current_workspace_section())

    @staticmethod
    def _is_group_field(field) -> bool:
        return field.key.startswith("group.")

    @staticmethod
    def _is_selectable_field(field) -> bool:
        return not field.key.startswith("group.") and not isinstance(field.interaction, ReadOnly)

    def _selectable_indices(self, fields: list) -> list[int]:
        return [index for index, field in enumerate(fields) if self._is_selectable_field(field)]

    def _first_selectable_index(self, config: dict, section: WorkspaceSection | None = None) -> int:
        target_section = section or self._current_workspace_section()
        fields = section_fields(config, target_section)
        selectable = self._selectable_indices(fields)
        return selectable[0] if selectable else 0

    def _current_group_label(self, config: dict) -> str:
        fields = self._current_fields(config)
        if not fields:
            return ""
        state = self._current_section_state()
        state.selected_index = max(0, min(state.selected_index, len(fields) - 1))
        current = ""
        for index, field in enumerate(fields):
            if self._is_group_field(field):
                current = field.label
            if index >= state.selected_index:
                break
        return current

    def _current_field(self, config: dict):
        fields = self._current_fields(config)
        if not fields:
            return None
        state = self._current_section_state()
        selectable = self._selectable_indices(fields)
        if not selectable:
            return None
        state.selected_index = max(0, min(state.selected_index, len(fields) - 1))
        if self._is_group_field(fields[state.selected_index]):
            state.selected_index = selectable[0]
        return fields[state.selected_index]

    def _section_label(self, section: WorkspaceSection) -> str:
        if section == WorkspaceSection.BOT:
            return self._t("bot_binding")
        return self._t(section.value)

    def _section_summary_label(self, section: WorkspaceSection) -> str:
        if section == WorkspaceSection.AGENT:
            return self._t("agent_summary")
        return self._section_label(section)

    def _enter_bind_bot(self, config: dict) -> None:
        self._state.screen = ScreenKind.BIND_BOT
        self._state.bind_bot.step = BindBotStep.PLATFORM
        self._state.bind_bot.selected_index = 0
        self._state.bind_bot.platform = None
        self._state.bind_bot.saved_bots = self._saved_bot_accounts()
        self._state.bind_bot.draft = None
        self._state.bind_bot.notice = ""
        self._refresh_view()

    def _enter_workspace(self, config: dict, *, section: WorkspaceSection | None = None) -> None:
        self._state.screen = ScreenKind.WORKSPACE
        if section is not None:
            self._state.workspace.active_section = section
        self._state.workspace.choice_state = None
        self._state.workspace.input_state = None
        section_state = self._current_section_state()
        section_state.subview = None
        section_state.scroll = 0
        section_state.selected_index = self._first_selectable_index(config)
        if config_ready(config):
            try:
                self._service.start_relay()
            except ValueError:
                pass
            except RuntimeError:
                pass
        self._refresh_view()

    def _left_panel_text(self, config: dict) -> str:
        relay_status = self._t("running") if self._state.runtime.relay_running else self._t("stopped")
        relay_style = "#3fb950" if self._state.runtime.relay_running else "#f85149"
        config_status = self._t("ready") if config_ready(config) else self._t("needs_config")
        config_style = "#3fb950" if config_ready(config) else "#f2cc60"
        bound = self._bot_primary_text(config) if self._active_binding_id(config) else self._t("unbound")
        section = self._section_summary_label(self._current_workspace_section()) if self._state.screen == ScreenKind.WORKSPACE else self._t("login_title")
        lines = [
            *self._left_panel_brand_lines(),
            "",
            *self._left_panel_status_lines(bound, section, relay_status, relay_style, config_status, config_style),
            *self._left_panel_decor_lines(),
        ]
        missing = self._missing_config_fields_text(config)
        if missing:
            lines.extend(["", f"[bold #f2cc60]{self._t('missing_label')}[/]: [#f2cc60]{missing}[/]"])
        return "\n".join(lines)

    def _left_panel_brand_lines(self) -> list[str]:
        return [
            f"[bold #fb923c]{POCO_ICON}[/]",
            f"[bold #fb923c]v{__version__}[/]",
        ]

    def _left_panel_status_lines(
        self,
        bound: str,
        section: str,
        relay_status: str,
        relay_style: str,
        config_status: str,
        config_style: str,
    ) -> list[str]:
        return [
            f"{self._t('bot')}: [bold #fb923c]{bound}[/]",
            f"{self._t('section')}: [bold #e6edf3]{section}[/]",
            f"{self._t('relay')}: [bold {relay_style}]{relay_status}[/]",
            f"{self._t('poco')}: [bold {config_style}]{config_status}[/]",
        ]

    def _left_panel_decor_lines(self) -> list[str]:
        relay_on = self._state.runtime.relay_running
        relay_label = "relay on" if relay_on else "relay off"
        relay_color = "#fb923c" if relay_on else "#8b949e"
        accent_color = "#fb923c" if relay_on else "#6e7681"
        dot_color = "#f2cc60" if relay_on else "#6e7681"
        return [
            "",
            f"[{accent_color}]/̴/̴_̴p̴o̴c̴o̴_̴/̴/̴[/]",
            f"[{dot_color}]  ░▒▓ · · ▓▒░[/]",
            f"[{relay_color}]  \\[̲̅$̲̅\\] {relay_label}[/]",
        ]

    def _missing_config_field_name(self, path: str) -> str:
        mapping = {"feishu.app_id": "app_id", "feishu.app_secret": "app_secret"}
        return mapping.get(path, path)

    def _missing_config_fields_text(self, config: dict) -> str:
        return ", ".join(self._missing_config_field_name(path) for path in missing_required_config_paths(config))

    def _right_panel_text(self, config: dict) -> str:
        if self._state.screen == ScreenKind.BIND_BOT:
            return self._bind_bot_text()
        return self._workspace_text(config)

    def _panel_prefix(self, title: str, *, extra_lines: list[str] | None = None) -> list[str]:
        lines = [f"[bold #fb923c]{title}[/]"]
        if extra_lines:
            lines.extend(extra_lines)
        return lines

    def _selected_entry(self, text: str) -> str:
        return f"[bold #fb923c]▌ {text}[/]"

    def _bind_bot_text(self) -> str:
        state = self._state.bind_bot
        prefix = self._panel_prefix(self._t("login_title"))
        if state.step == BindBotStep.PLATFORM:
            options = [Platform.FEISHU, Platform.SLACK, Platform.DISCORD]
            lines = prefix + ["", f"[bold #fb923c]{self._t('select_platform')}[/]"]
            entries = []
            for index, option in enumerate(options):
                label = self._t(f"login_{option.value}")
                if index == state.selected_index:
                    entries.append(self._selected_entry(label))
                else:
                    entries.append(f"  {label}")
            suffix = ["", f"[#8b949e]{self._t('login_platform_desc')}[/]"]
            if state.notice:
                suffix.extend(["", f"[#f2cc60]{state.notice}[/]"])
            return self._render_windowed_options(entries, state.selected_index, prefix_lines=lines, suffix_lines=suffix)

        if state.step == BindBotStep.ACCOUNT:
            entries = []
            options = list(state.saved_bots) + [BotAccount(app_id="__new__", app_name=self._t("login_new_bot"))]
            current = self._active_binding_id()
            lines = prefix + ["", f"[bold #fb923c]{self._t('select_saved_bot')}[/]"]
            for index, option in enumerate(options):
                if option.app_id == "__new__":
                    label = self._t("login_new_bot")
                else:
                    label = option.display_name
                    if option.app_id == current:
                        label = f"{label} ({self._t('login_current_bot')})"
                    if option.display_name != option.app_id:
                        label = f"{label} · {option.app_id}"
                if index == state.selected_index:
                    entries.append(self._selected_entry(label))
                else:
                    entries.append(f"  {label}")
            suffix = ["", f"[#8b949e]{self._t('login_saved_bots_desc')}[/]"]
            if state.notice:
                suffix.extend(["", f"[#f2cc60]{state.notice}[/]"])
            return self._render_windowed_options(entries, state.selected_index, prefix_lines=lines, suffix_lines=suffix)

        if state.step == BindBotStep.APP_ID:
            return "\n".join(
                prefix
                + ["", f"[bold #fb923c]{self._t('login_app_id')}[/]", f"[#8b949e]{self._t('login_enter_app_id')}[/]"]
            )

        return "\n".join(
            prefix
            + [
                "",
                f"[bold #fb923c]{self._t('login_app_secret')}[/]",
                f"[#8b949e]{self._t('login_enter_app_secret')}[/]",
                "",
                f"[#8b949e]{self._t('login_app_id')}: {state.draft.app_id if state.draft else ''}[/]",
            ]
        )

    def _workspace_text(self, config: dict) -> str:
        state = self._state.workspace
        prefix = self._panel_prefix(
            self._t("workspace_title"),
            extra_lines=[
                "",
                self._workspace_tabs_line(),
                f"[#8b949e]{self._t('workspace_help')}[/]",
                "",
            ],
        )
        if state.choice_state is not None:
            return self._choice_editor_text(prefix, config)
        if self._current_section_state().subview == SubviewId.CLAUDE_BACKENDS:
            return self._claude_backends_text(prefix, config)
        if self._current_section_state().subview == SubviewId.CLAUDE_BACKEND_SETTINGS:
            return self._claude_backend_settings_text(prefix, config)
        if self._current_section_state().subview == SubviewId.BOT_ADVANCED:
            return self._bot_advanced_text(prefix, config)
        if self._current_section_state().subview == SubviewId.SHOW_CONFIG:
            return self._show_config_text(prefix, config)
        return self._section_fields_text(prefix, config)

    def _workspace_tabs_line(self) -> str:
        labels = []
        for section in WorkspaceSection:
            label = self._section_label(section)
            if section == self._current_workspace_section():
                labels.append(f"[bold #0f1117 on #fb923c] {label} [/]")
            else:
                labels.append(f"[bold #fb923c]{label}[/]")
        return "  ".join(labels)

    def _section_fields_text(self, prefix: list[str], config: dict) -> str:
        fields = self._current_fields(config)
        entry_lines = []
        self._current_field(config)
        selected = self._current_section_state().selected_index
        for index, field in enumerate(fields):
            if field.key.startswith("group."):
                if entry_lines:
                    entry_lines.extend(["", ""])
                entry_lines.append(f"[bold #fb923c]{field.label.upper()}[/]")
                continue
            if index == selected:
                entry_lines.append(self._selected_field_entry(config, field))
            else:
                entry_lines.append(self._field_entry(config, field))
        return self._render_windowed_options(entry_lines, selected, prefix_lines=prefix)

    def _field_value_text(self, config: dict, field) -> str:
        interaction = field.interaction
        if isinstance(interaction, ReadOnly):
            return display_config_value(config, field.key)
        if isinstance(interaction, ActionTrigger):
            return interaction.label
        if isinstance(interaction, SubviewOpen):
            return "→"
        return display_config_value(config, field.key)

    def _field_entry(self, config: dict, field) -> str:
        interaction = field.interaction
        if isinstance(interaction, SubviewOpen):
            summary = self._subview_summary_text(config, field)
            if summary:
                return f"  {field.label}: {summary} →"
            return f"  {field.label} →"
        if isinstance(interaction, ActionTrigger):
            return f"  {field.label} →"
        value = self._field_value_text(config, field)
        if value == "[#8b949e]—[/]" or value == "[#8b949e]{}[/]":
            return f"  [#8b949e]{field.label}:[/] {value}"
        return f"  {field.label}: {value}"

    def _selected_field_entry(self, config: dict, field) -> str:
        interaction = field.interaction
        if isinstance(interaction, SubviewOpen):
            summary = self._subview_summary_text(config, field)
            if summary:
                return f"[bold #fb923c][ {field.label}: {summary} → ][/]"
            return f"[bold #fb923c][ {field.label} → ][/]"
        if isinstance(interaction, ActionTrigger):
            return f"[bold #fb923c][ {field.label} → ][/]"
        value = self._field_value_text(config, field)
        return f"[bold #fb923c]▌[/] {field.label}: [bold #fb923c]{value}[/]"

    def _subview_summary_text(self, config: dict, field) -> str:
        if field.key == "claude.manage_backends":
            return current_claude_backend(config)
        if field.key == "claude.backend_settings":
            backend = current_claude_backend(config)
            payload = config.get("claude", {}).get("backends", {}).get(backend, {})
            if isinstance(payload, dict):
                model = str(payload.get("default_model", "")).strip()
                if model:
                    return f"{backend} · {model}"
            return backend
        return ""

    def _choice_editor_text(self, prefix: list[str], config: dict) -> str:
        choice = self._state.workspace.choice_state
        assert choice is not None
        lines = prefix + [f"[bold #fb923c]{choice.label}[/]"]
        entries = []
        for index, (_value, label) in enumerate(choice.options):
            if index == choice.selected_index:
                entries.append(self._selected_entry(label))
            else:
                entries.append(f"  {label}")
        current = display_config_value(config, choice.field_key)
        return self._render_windowed_options(
            entries,
            choice.selected_index,
            prefix_lines=lines,
            suffix_lines=["", f"[#8b949e]{self._t('current_value')}: {current}[/]"],
        )

    def _claude_backend_entries(self, config: dict) -> list[tuple[str, str]]:
        claude = config.get("claude", {})
        backends = claude.get("backends", {}) if isinstance(claude.get("backends", {}), dict) else {}
        default_backend = current_claude_backend(config)
        entries: list[tuple[str, str]] = []
        for name in sorted(backends.keys()):
            if str(name).strip() == "custom":
                continue
            label = str(name)
            if label == default_backend:
                label = f"{label} ({self._t('current_value')})"
            entries.append((str(name), label))
        entries.append(("__add__", "New Custom Backend"))
        return entries

    def _claude_backends_text(self, prefix: list[str], config: dict) -> str:
        section_state = self._current_section_state()
        entries = self._claude_backend_entries(config)
        lines = prefix + [f"[bold #fb923c]Claude Backends[/]"]
        rendered = []
        for index, (_name, label) in enumerate(entries):
            if index == section_state.selected_index:
                rendered.append(self._selected_entry(label))
            else:
                rendered.append(f"  {label}")
        return self._render_windowed_options(rendered, section_state.selected_index, prefix_lines=lines)

    def _claude_backend_settings_text(self, prefix: list[str], config: dict) -> str:
        fields = claude_backend_setting_fields(config)
        backend = current_claude_backend(config)
        lines = prefix + [f"[bold #fb923c]Backend Settings · {backend}[/]", ""]
        selected = self._current_section_state().selected_index
        entries = []
        for index, field in enumerate(fields):
            if index == selected:
                entries.append(self._selected_field_entry(config, field))
            else:
                entries.append(self._field_entry(config, field))
        return self._render_windowed_options(entries, selected, prefix_lines=lines)

    def _bot_advanced_text(self, prefix: list[str], config: dict) -> str:
        fields = bot_advanced_fields(config)
        lines = prefix + [f"[bold #fb923c]Advanced[/]", ""]
        selected = self._current_section_state().selected_index
        entries = []
        for index, field in enumerate(fields):
            if index == selected:
                entries.append(self._selected_field_entry(config, field))
            else:
                entries.append(self._field_entry(config, field))
        return self._render_windowed_options(entries, selected, prefix_lines=lines)

    def _show_lines(self, config: dict) -> list[str]:
        config_text = json.dumps(self._service.masked_config(), ensure_ascii=False, indent=2)
        return [self._t("current_config"), ""] + config_text.splitlines()

    def _show_window_height(self) -> int:
        try:
            height = self.query_one("#right_text", Static).size.height or self.query_one("#right_card", Container).size.height
        except Exception:
            height = 0
        return max(10, height - 2 if height else 24)

    def _show_config_text(self, prefix: list[str], config: dict) -> str:
        section_state = self._current_section_state()
        lines = self._show_lines(config)
        max_scroll = max(0, len(lines) - self._show_window_height())
        section_state.scroll = max(0, min(section_state.scroll, max_scroll))
        start = section_state.scroll
        end = min(len(lines), start + self._show_window_height())
        visible = lines[start:end]
        rendered = prefix.copy()
        for index, line in enumerate(visible):
            if start + index == 0:
                rendered.append(f"[bold #fb923c]{line}[/]")
            else:
                rendered.append(line)
        status = self._t("scroll_status", start=start + 1 if lines else 0, end=end, total=len(lines))
        rendered.extend(["", f"[#8b949e]{self._t('show_scroll')}[/]", f"[#8b949e]{status}[/]"])
        return "\n".join(rendered)

    def _render_windowed_options(
        self,
        entries: list[str],
        selected: int,
        *,
        prefix_lines: list[str],
        suffix_lines: list[str] | None = None,
    ) -> str:
        suffix = suffix_lines or []
        window_height = self._show_window_height()
        available = max(1, window_height - len(prefix_lines) - len(suffix))
        start = max(0, min(selected - (available // 2), max(0, len(entries) - available)))
        end = min(len(entries), start + available)
        visible = entries[start:end]
        lines = list(prefix_lines)
        if start > 0:
            lines.append(f"[#8b949e]  ↑ {start} more fields[/]")
        lines.extend(visible)
        if end < len(entries):
            lines.append(f"[#8b949e]  ↓ {len(entries) - end} more fields[/]")
        lines.extend(suffix)
        return "\n".join(lines)

    def _footer_hint_text(self) -> str:
        if self._state.screen == ScreenKind.BIND_BOT:
            if self._state.bind_bot.step == BindBotStep.PLATFORM:
                return self._t("nav_hint_bind_platform")
            if self._state.bind_bot.step == BindBotStep.ACCOUNT:
                return self._t("nav_hint_bind_account")
            return self._t("nav_hint_input")
        workspace = self._state.workspace
        if workspace.input_state is not None:
            return self._t("nav_hint_input")
        if workspace.choice_state is not None:
            return self._t("nav_hint_choice")
        section_state = self._current_section_state()
        if section_state.subview == SubviewId.SHOW_CONFIG:
            return self._t("nav_hint_show_config")
        if section_state.subview is not None:
            return self._t("nav_hint_subview")
        field = self._current_field(self._service.load_config())
        if field is None or isinstance(field.interaction, ReadOnly):
            return self._t("nav_hint_workspace_view")
        return self._t("nav_hint_workspace_editable")

    def _sync_input_state(self) -> None:
        input_widget = self.query_one("#command_input", Input)
        if self._state.screen == ScreenKind.BIND_BOT and self._state.bind_bot.step in {BindBotStep.APP_ID, BindBotStep.APP_SECRET}:
            input_widget.disabled = False
            input_widget.password = self._state.bind_bot.step == BindBotStep.APP_SECRET
            input_widget.placeholder = self._t("login_app_id") if self._state.bind_bot.step == BindBotStep.APP_ID else self._t("login_app_secret")
            if not input_widget.has_focus:
                input_widget.value = self._state.bind_bot.draft.app_id if self._state.bind_bot.step == BindBotStep.APP_ID and self._state.bind_bot.draft else ""
            input_widget.focus()
            return
        if self._state.screen == ScreenKind.WORKSPACE and self._state.workspace.input_state is not None:
            state = self._state.workspace.input_state
            input_widget.disabled = False
            input_widget.password = state.secret
            input_widget.placeholder = state.placeholder
            if not input_widget.has_focus:
                input_widget.value = state.value
            input_widget.focus()
            return
        input_widget.disabled = True
        input_widget.password = False
        input_widget.placeholder = ""
        input_widget.value = ""

    def action_save_and_restart(self) -> None:
        self.exit("restart")

    def action_back(self) -> None:
        if self._state.screen == ScreenKind.BIND_BOT:
            if self._state.bind_bot.step == BindBotStep.PLATFORM:
                self.exit()
                return
            self._back_bind_bot()
            return
        workspace = self._state.workspace
        if workspace.input_state is not None:
            workspace.input_state = None
            self._refresh_view()
            return
        if workspace.choice_state is not None:
            workspace.choice_state = None
            self._refresh_view()
            return
        section_state = self._current_section_state()
        if section_state.subview is not None:
            section_state.subview = None
            section_state.scroll = 0
            self._refresh_view()
            return
        self.exit()

    def _back_bind_bot(self) -> None:
        state = self._state.bind_bot
        if state.step == BindBotStep.PLATFORM:
            return
        if state.step == BindBotStep.ACCOUNT:
            state.step = BindBotStep.PLATFORM
        elif state.step == BindBotStep.APP_ID:
            state.step = BindBotStep.ACCOUNT
        else:
            state.step = BindBotStep.APP_ID
        self._refresh_view()

    def action_cursor_up(self) -> None:
        if self._state.screen == ScreenKind.BIND_BOT:
            self._bind_cursor(-1)
            return
        self._workspace_cursor(-1)

    def action_cursor_down(self) -> None:
        if self._state.screen == ScreenKind.BIND_BOT:
            self._bind_cursor(1)
            return
        self._workspace_cursor(1)

    def _bind_cursor(self, delta: int) -> None:
        state = self._state.bind_bot
        if state.step == BindBotStep.PLATFORM:
            count = 3
        elif state.step == BindBotStep.ACCOUNT:
            count = len(state.saved_bots) + 1
        else:
            return
        if count <= 0:
            return
        state.selected_index = (state.selected_index + delta) % count
        self._refresh_view()

    def _workspace_cursor(self, delta: int) -> None:
        workspace = self._state.workspace
        if workspace.input_state is not None:
            return
        if workspace.choice_state is not None:
            count = len(workspace.choice_state.options)
            if count > 0:
                workspace.choice_state.selected_index = (workspace.choice_state.selected_index + delta) % count
                self._refresh_view()
            return
        section_state = self._current_section_state()
        if section_state.subview == SubviewId.CLAUDE_BACKENDS:
            entries = self._claude_backend_entries(self._service.load_config())
            if entries:
                section_state.selected_index = (section_state.selected_index + delta) % len(entries)
                self._refresh_view()
            return
        if section_state.subview == SubviewId.CLAUDE_BACKEND_SETTINGS:
            fields = claude_backend_setting_fields(self._service.load_config())
            if fields:
                section_state.selected_index = (section_state.selected_index + delta) % len(fields)
                self._refresh_view()
            return
        if section_state.subview == SubviewId.BOT_ADVANCED:
            fields = bot_advanced_fields(self._service.load_config())
            if fields:
                section_state.selected_index = (section_state.selected_index + delta) % len(fields)
                self._refresh_view()
            return
        if section_state.subview == SubviewId.SHOW_CONFIG:
            max_scroll = max(0, len(self._show_lines(self._service.load_config())) - self._show_window_height())
            section_state.scroll = max(0, min(max_scroll, section_state.scroll + delta))
            self._refresh_view()
            return
        fields = self._current_fields(self._service.load_config())
        selectable = self._selectable_indices(fields)
        if not selectable:
            return
        if section_state.selected_index not in selectable:
            section_state.selected_index = selectable[0]
            self._refresh_view()
            return
        current = selectable.index(section_state.selected_index)
        section_state.selected_index = selectable[(current + delta) % len(selectable)]
        self._refresh_view()

    def action_section_left(self) -> None:
        self._switch_section(-1)

    def action_section_right(self) -> None:
        self._switch_section(1)

    def _switch_section(self, delta: int) -> None:
        if self._state.screen != ScreenKind.WORKSPACE:
            return
        workspace = self._state.workspace
        if workspace.input_state is not None or workspace.choice_state is not None or self._current_section_state().subview is not None:
            return
        sections = list(WorkspaceSection)
        current = sections.index(workspace.active_section)
        workspace.active_section = sections[(current + delta) % len(sections)]
        config = self._service.load_config()
        section_state = self._current_section_state()
        section_state.subview = None
        section_state.scroll = 0
        section_state.selected_index = self._first_selectable_index(config)
        self._refresh_view()

    def action_activate(self) -> None:
        if self._state.screen == ScreenKind.BIND_BOT:
            self._activate_bind_bot()
            return
        self._activate_workspace()

    def _activate_bind_bot(self) -> None:
        state = self._state.bind_bot
        if state.step == BindBotStep.PLATFORM:
            platform = [Platform.FEISHU, Platform.SLACK, Platform.DISCORD][state.selected_index]
            if platform != Platform.FEISHU:
                state.notice = self._t("not_implemented", name=self._t(f"login_{platform.value}"))
                self._refresh_view()
                return
            state.platform = platform
            state.step = BindBotStep.ACCOUNT
            state.selected_index = 0
            state.notice = ""
            self._refresh_view()
            return
        if state.step == BindBotStep.ACCOUNT:
            if state.selected_index >= len(state.saved_bots):
                state.step = BindBotStep.APP_ID
                state.draft = BindBotDraft()
                self._refresh_view()
                return
            self._bind_existing_bot(state.saved_bots[state.selected_index].app_id)
            return

    def _bind_existing_bot(self, app_id: str) -> None:
        bind_workspace(Path.cwd(), app_id)
        self._service = self._service_factory(app_id)
        config = self._service.load_config()
        initial_section = WorkspaceSection.BOT if self._focus_config or not config_ready(config) else WorkspaceSection.AGENT
        self._enter_workspace(config, section=initial_section)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "command_input":
            return
        raw_value = event.value
        event.input.value = ""
        if self._state.screen == ScreenKind.BIND_BOT:
            self._submit_bind_input(raw_value.strip())
            return
        self._submit_workspace_input(raw_value)

    def _submit_bind_input(self, value: str) -> None:
        state = self._state.bind_bot
        if state.step == BindBotStep.APP_ID:
            if not value:
                return
            state.draft = BindBotDraft(app_id=value)
            state.step = BindBotStep.APP_SECRET
            self._refresh_view()
            return
        if state.step == BindBotStep.APP_SECRET:
            if not value or state.draft is None:
                return
            self._finish_new_bot_binding(state.draft.app_id, value)

    def _finish_new_bot_binding(self, app_id: str, app_secret: str) -> None:
        bind_workspace(Path.cwd(), app_id)
        paths = build_paths(app_id)
        ensure_dirs(paths)
        store = ConfigStore(paths.config_path, paths)
        config = store.load()
        config.setdefault("feishu", {})
        config["feishu"]["app_id"] = app_id.strip()
        config["feishu"]["app_secret"] = app_secret.strip()
        app_name = self._fetch_feishu_app_name(app_id, app_secret)
        if app_name:
            config["feishu"]["app_name"] = app_name
        store.save(config)
        self._service = self._service_factory(app_id)
        config = self._service.load_config()
        initial_section = WorkspaceSection.BOT if self._focus_config or not config_ready(config) else WorkspaceSection.AGENT
        self._enter_workspace(config, section=initial_section)

    @staticmethod
    def _fetch_feishu_app_name(app_id: str, app_secret: str) -> str:
        try:
            client = (
                lark.Client.builder()
                .app_id(app_id)
                .app_secret(app_secret)
                .log_level(lark.LogLevel.ERROR)
                .build()
            )
            request = (
                lark.api.application.v6.GetApplicationRequest.builder()
                .app_id(app_id)
                .lang("en_us")
                .build()
            )
            response = client.application.v6.application.get(request)
            if response.code != 0 or response.data is None or response.data.app is None:
                return ""
            return str(getattr(response.data.app, "app_name", "") or "").strip()
        except Exception:
            return ""

    def _submit_workspace_input(self, value: str) -> None:
        input_state = self._state.workspace.input_state
        if input_state is None:
            return
        if input_state.field_key == "claude.new_backend":
            if not value.strip():
                return
            self._submit_new_claude_backend(value, input_state)
            return
        try:
            self._service.set_config_value(input_state.field_key, value)
        except Exception:
            return
        self._state.workspace.input_state = None
        self._refresh_view()

    def _activate_workspace(self) -> None:
        workspace = self._state.workspace
        if workspace.choice_state is not None:
            value, _label = workspace.choice_state.options[workspace.choice_state.selected_index]
            try:
                self._service.set_config_value(workspace.choice_state.field_key, value)
            except Exception:
                return
            workspace.choice_state = None
            self._refresh_view()
            return
        if workspace.input_state is not None:
            return
        if self._current_section_state().subview == SubviewId.CLAUDE_BACKENDS:
            self._activate_claude_backends_subview()
            return
        if self._current_section_state().subview == SubviewId.CLAUDE_BACKEND_SETTINGS:
            self._activate_claude_backend_settings_subview()
            return
        if self._current_section_state().subview == SubviewId.BOT_ADVANCED:
            self._activate_bot_advanced_subview()
            return
        field = self._current_field(self._service.load_config())
        if field is None:
            return
        interaction = field.interaction
        if isinstance(interaction, ReadOnly):
            return
        if isinstance(interaction, SubviewOpen):
            self._current_section_state().subview = interaction.subview_id
            self._current_section_state().scroll = 0
            self._refresh_view()
            return
        if isinstance(interaction, ActionTrigger):
            if interaction.label == "delete_current_claude_backend":
                self._delete_current_claude_backend()
                return
            if interaction.label == "restart_relay":
                self.exit("restart")
            return
        if isinstance(interaction, ChoiceSelect):
            current = display_config_value(self._service.load_config(), field.key)
            selected_index = 0
            for index, (value, _label) in enumerate(interaction.choices):
                if value == current:
                    selected_index = index
                    break
            workspace.choice_state = ChoiceState(
                field_key=field.key,
                label=field.label,
                options=interaction.choices,
                selected_index=selected_index,
            )
            self._refresh_view()
            return
        if isinstance(interaction, TextInput):
            workspace.input_state = self._build_input_state(field.key, field.label, interaction)
            self._refresh_view()

    def _activate_claude_backends_subview(self) -> None:
        config = self._service.load_config()
        entries = self._claude_backend_entries(config)
        if not entries:
            return
        selected_name = entries[self._current_section_state().selected_index][0]
        if selected_name == "__add__":
            from .state import InputState

            self._state.workspace.input_state = InputState(
                field_key="claude.new_backend",
                label="New Claude Backend",
                placeholder="backend name",
                steps=["name", "base_url", "auth_token", "default_model"],
                current=0,
                draft={},
            )
            self._refresh_view()
            return
        try:
            self._service.set_config_value("claude.default_backend", selected_name)
        except Exception:
            return
        self._current_section_state().subview = None
        self._current_section_state().selected_index = 0
        self._refresh_view()

    def _activate_claude_backend_settings_subview(self) -> None:
        fields = claude_backend_setting_fields(self._service.load_config())
        if not fields:
            return
        section_state = self._current_section_state()
        section_state.selected_index = max(0, min(section_state.selected_index, len(fields) - 1))
        field = fields[section_state.selected_index]
        interaction = field.interaction
        if isinstance(interaction, ReadOnly):
            return
        if isinstance(interaction, ActionTrigger):
            if interaction.label == "delete_current_claude_backend":
                self._delete_current_claude_backend()
            return
        if isinstance(interaction, ChoiceSelect):
            current = display_config_value(self._service.load_config(), field.key)
            selected_index = 0
            for index, (value, _label) in enumerate(interaction.choices):
                if value == current:
                    selected_index = index
                    break
            self._state.workspace.choice_state = ChoiceState(
                field_key=field.key,
                label=field.label,
                options=interaction.choices,
                selected_index=selected_index,
            )
            self._refresh_view()
            return
        if isinstance(interaction, TextInput):
            self._state.workspace.input_state = self._build_input_state(field.key, field.label, interaction)
            self._refresh_view()

    def _activate_bot_advanced_subview(self) -> None:
        fields = bot_advanced_fields(self._service.load_config())
        if not fields:
            return
        section_state = self._current_section_state()
        section_state.selected_index = max(0, min(section_state.selected_index, len(fields) - 1))
        field = fields[section_state.selected_index]
        interaction = field.interaction
        if isinstance(interaction, ChoiceSelect):
            return
        if isinstance(interaction, TextInput):
            self._state.workspace.input_state = self._build_input_state(field.key, field.label, interaction)
            self._refresh_view()

    def _delete_current_claude_backend(self) -> None:
        config = self._service.load_config()
        backend_name = current_claude_backend(config)
        if backend_name in {"anthropic", "deepseek", "kimi", "minimax"}:
            return
        claude = config.setdefault("claude", {})
        backends = claude.setdefault("backends", {})
        if backend_name not in backends:
            return
        backends.pop(backend_name, None)
        claude["default_backend"] = "anthropic"
        self._service.save_config(config)
        self._refresh_view()

    def _build_input_state(self, field_key: str, label: str, interaction: TextInput):
        current = self._service.load_config()
        raw_value = ""
        try:
            value = self._lookup_nested(current, field_key)
            if isinstance(value, list):
                raw_value = ", ".join(str(item) for item in value)
            elif isinstance(value, dict):
                raw_value = json.dumps(value, ensure_ascii=False)
            else:
                raw_value = str(value or "")
        except Exception:
            raw_value = ""
        from .state import InputState

        return InputState(
            field_key=field_key,
            label=label,
            secret=interaction.secret,
            placeholder=interaction.placeholder or label,
            value=raw_value,
        )

    def _submit_new_claude_backend(self, value: str, input_state) -> None:
        step_key = input_state.steps[input_state.current]
        input_state.draft[step_key] = value.strip()
        if input_state.current < len(input_state.steps) - 1:
            input_state.current += 1
            next_step = input_state.steps[input_state.current]
            input_state.placeholder = next_step.replace("_", " ")
            input_state.secret = next_step == "auth_token"
            input_state.value = ""
            self._refresh_view()
            return
        name = str(input_state.draft.get("name", "")).strip()
        if not name or not all(ch.isalnum() or ch in {"-", "_"} for ch in name):
            return
        config = self._service.load_config()
        claude = config.setdefault("claude", {})
        backends = claude.setdefault("backends", {})
        if name in backends:
            return
        backends[name] = {
            "base_url": str(input_state.draft.get("base_url", "")).strip(),
            "auth_token": str(input_state.draft.get("auth_token", "")).strip(),
            "default_model": str(input_state.draft.get("default_model", "")).strip(),
            "extra_env": {},
        }
        claude["default_backend"] = name
        self._service.save_config(config)
        self._state.workspace.input_state = None
        self._current_section_state().subview = None
        self._current_section_state().selected_index = 0
        self._refresh_view()

    @staticmethod
    def _lookup_nested(config: dict, path: str):
        value = config
        for part in path.split("."):
            if not isinstance(value, dict):
                return ""
            value = value.get(part, "")
        return value
