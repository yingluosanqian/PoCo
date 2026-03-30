"""Section-level config controllers and renderers."""

from __future__ import annotations

from .render_base import BaseConfigRenderer
from .types import CONFIG_FIELDS, CONFIG_GROUP_SECTIONS, CONFIG_MENU_OPTIONS, ConfigScreenState, OptionMenuState


class BaseSectionController:
    """Base controller for simple config sections.

    Subclasses provide a fixed ``group`` and ``sections`` tuple. The base
    implementation handles list navigation, field entry, and simple open logic.
    """

    group: str = ""
    sections: tuple[str, ...] = ()

    def __init__(self, app) -> None:
        """Initializes the controller.

        Args:
            app: The owning ``PoCoTui`` instance.
        """
        self.app = app

    def option_menu(self) -> OptionMenuState:
        """Returns the current section list state."""
        return OptionMenuState("group_sections", self.app._config_selected, len(self.sections))

    def activate_group_selection(self) -> None:
        """Opens the currently selected section."""
        self.open_section(self.sections[self.app._config_selected])

    def option_fields(self) -> OptionMenuState | None:
        """Returns field selection state for the current section."""
        section = self.current_section()
        if section is None:
            return None
        return OptionMenuState("fields", self.app._config_field_selected, len(CONFIG_FIELDS[section]))

    def activate_field_selection(self) -> None:
        """Opens the selected field for direct input or choice selection."""
        section = self.current_section()
        assert section is not None
        path, _label = CONFIG_FIELDS[section][self.app._config_field_selected]
        choices = self.app._choices_for_path(path)
        next_kind = "choices" if choices else "input"
        self.app._push_config_state(
            ConfigScreenState(kind=next_kind, group=self.group, section=section, path=path)
        )
        self.app._refresh_runtime()

    def open_section(self, section: str) -> None:
        """Pushes the next config state for the given section."""
        if section == "show":
            self.app._push_config_state(ConfigScreenState(kind="show", group=self.group, section=section))
            self.app._show_scroll = 0
        elif section == "language":
            self.app._push_config_state(
                ConfigScreenState(kind="choices", group=self.group, section=section, path="ui.language")
            )
        else:
            self.app._push_config_state(ConfigScreenState(kind="fields", group=self.group, section=section))
        self.app._refresh_runtime()

    def current_section(self) -> str | None:
        """Returns the active section for this controller, if any."""
        section = self.app._current_config_section_name()
        if section in self.sections:
            return section
        return None


class LanguageSectionController:
    """Controller for the standalone language selector."""

    def __init__(self, app) -> None:
        """Initializes the controller.

        Args:
            app: The owning ``PoCoTui`` instance.
        """
        self.app = app

    def activate(self) -> None:
        """Opens the language choice screen."""
        self.app._push_config_state(ConfigScreenState(kind="choices", section="language", path="ui.language"))
        self.app._refresh_runtime()


class BotConfigController(BaseSectionController):
    """Controller for bot-level settings."""

    group = "bot"
    sections = ("feishu",)


class AgentConfigController(BaseSectionController):
    """Controller for agent and model related settings."""

    group = "agent"
    sections = ("codex", "claude")

    def open_section(self, section: str) -> None:
        """Opens an agent section, with special handling for Claude."""
        if section == "claude":
            self.app._push_config_state(ConfigScreenState(kind="claude_backends", group=self.group, section=section))
            self.app._refresh_runtime()
            return
        super().open_section(section)


class PocoConfigController(BaseSectionController):
    """Controller for PoCo runtime settings."""

    group = "poco"
    sections = ("bridge", "show")


class SectionConfigRenderer(BaseConfigRenderer):
    """Renders config section lists and field lists."""

    def render_menu(self, config: dict) -> str:
        """Renders the top-level config section menu."""
        section = CONFIG_MENU_OPTIONS[self.app._config_selected]
        if section == "language":
            current_body = f"{self.language_label(config.get('ui', {}).get('language', 'en'))} is currently active."
        elif section == "bot":
            current_body = "Configure Feishu bot access and credentials."
        elif section == "agent":
            current_body = "Configure agent providers and built-in model backends such as Codex, Claude, and Kimi."
        elif section == "poco":
            current_body = "Configure PoCo runtime behavior and local preferences."
        else:
            current_body = "Open this section to inspect and update its settings."
        prefix = self.app._panel_prefix(
            self.app._t("config_mode"),
            breadcrumb_parts=self.breadcrumb_parts(),
            heading=self.app._t("pick_section"),
        )
        entry_lines = []
        for index, option in enumerate(CONFIG_MENU_OPTIONS):
            label = self.menu_option_label(config, option)
            if index == self.app._config_selected:
                entry_lines.append(f"[bold #0f1117 on #fb923c]  {label}  [/]")
            else:
                entry_lines.append(f"  {label}")
        suffix = ["", f"[#8b949e]{current_body}[/]"]
        return self.app._render_windowed_options(
            entry_lines,
            self.app._config_selected,
            prefix_lines=prefix,
            suffix_lines=suffix,
        )

    def render_group(self, config: dict) -> str:
        """Renders the list of sections within the current config group."""
        assert self.app._config_group is not None
        options = CONFIG_GROUP_SECTIONS[self.app._config_group]
        extra_lines = self.app._workspace_binding_lines(config) if self.app._config_group == "bot" else None
        prefix = self.app._panel_prefix(
            self.app._t("config_mode"),
            breadcrumb_parts=self.breadcrumb_parts(),
            extra_lines=extra_lines,
            heading=self.app._t("pick_section"),
        )
        entry_lines = []
        for index, option in enumerate(options):
            label = self.menu_option_label(config, option)
            if index == self.app._config_selected:
                entry_lines.append(f"[bold #0f1117 on #fb923c]  {label}  [/]")
            else:
                entry_lines.append(f"  {label}")
        return self.app._render_windowed_options(entry_lines, self.app._config_selected, prefix_lines=prefix)

    def render_fields(self, config: dict) -> str:
        """Renders the editable field list for the current section."""
        assert self.app._config_section is not None
        section = self.app._config_section
        fields = CONFIG_FIELDS[section]
        extra_lines = [f"[#8b949e]{self.app._t('section')}: {self.setting_option_label(section)}[/]"]
        if section == "feishu":
            extra_lines.extend(self.app._workspace_binding_lines(config))
        prefix = self.app._panel_prefix(
            self.app._t("config_mode"),
            breadcrumb_parts=self.breadcrumb_parts(),
            extra_lines=extra_lines,
            heading=self.app._t("field"),
        )
        entry_lines = []
        for index, (path, label) in enumerate(fields):
            current = self.display_config_value(config, path)
            text = f"{label}: {current}"
            if index == self.app._config_field_selected:
                entry_lines.append(f"[bold #0f1117 on #fb923c]  {text}  [/]")
            else:
                entry_lines.append(f"  {text}")
        return self.app._render_windowed_options(entry_lines, self.app._config_field_selected, prefix_lines=prefix)
