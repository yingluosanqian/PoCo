"""Top-level config router and panel renderer."""

from __future__ import annotations

from .claude import ClaudeConfigController, ClaudeConfigRenderer
from .render_base import BaseConfigRenderer
from .render_forms import FormConfigRenderer
from .sections import (
    AgentConfigController,
    BotConfigController,
    LanguageSectionController,
    PocoConfigController,
    SectionConfigRenderer,
)
from .types import BUILTIN_CLAUDE_BACKENDS, CONFIG_GROUP_SECTIONS, CONFIG_MENU_OPTIONS, ConfigScreenState, OptionMenuState


class ConfigMenuController:
    """Routes config navigation to section and Claude-specific controllers."""

    def __init__(self, app) -> None:
        """Initializes config routing state."""
        self.app = app
        self.language = LanguageSectionController(app)
        self.bot = BotConfigController(app)
        self.agent = AgentConfigController(app)
        self.poco = PocoConfigController(app)
        self.claude = ClaudeConfigController(app)
        self._section_controllers = {"bot": self.bot, "agent": self.agent, "poco": self.poco}
        self._renderers = {
            "sections": self.app._config_menu_text,
            "group_sections": self.app._config_group_text,
            "fields": self.app._config_fields_text,
            "claude_backends": self.app._claude_backends_text,
            "claude_custom_fields": lambda config: self.app._claude_custom_fields_text(),
            "claude_backend_fields": self.app._claude_backend_fields_text,
            "claude_backend_models": self.app._claude_backend_models_text,
            "claude_backend_model_actions": self.app._claude_backend_model_actions_text,
            "extra_env_list": self.app._extra_env_list_text,
            "extra_env_actions": self.app._extra_env_actions_text,
            "choices": self.app._config_choices_text,
            "input": self.app._config_input_text,
            "show": lambda config: self.app._show_text(config),
        }
        self._option_handlers = {
            "sections": self._option_sections,
            "group_sections": self._option_group_sections,
            "fields": self._option_fields,
            "choices": self._option_choices,
        }
        self._activate_handlers = {
            "sections": self._activate_sections,
            "group_sections": self._activate_group_sections,
            "fields": self._activate_fields,
            "choices": self._activate_choices,
        }

    def enter(self) -> None:
        """Enters config mode at the top-level section list."""
        self.app._config_stack = [ConfigScreenState(kind="sections", selected=0)]
        self.app._refresh_runtime()

    def exit(self) -> None:
        """Leaves config mode and returns to the root menu."""
        self.app._config_stack = []
        self.app._view = "menu"

    def render(self, config: dict) -> str:
        """Renders the current config screen."""
        renderer = self._renderers.get(self.app._config_level, self.app._config_menu_text)
        return renderer(config)

    def current_option_menu(self) -> OptionMenuState | None:
        """Returns the currently active option menu, if any."""
        state = self.app._config_state()
        if state is None:
            return None
        if self.claude.handles(state.kind):
            return self.claude.current_option_menu(state.kind)
        handler = self._option_handlers.get(state.kind)
        return handler() if handler else None

    def back(self) -> None:
        """Moves back one config level, repairing Claude fallback paths when needed."""
        if len(self.app._config_stack) <= 1:
            self.exit()
            self.app._set_message(self.app._t("back_dashboard"))
            self.app._refresh_runtime()
            return
        popped = self.app._pop_config_state()
        if popped and popped.kind == "claude_backend_fields":
            parent = self.app._config_state()
            if parent is None or parent.kind != "claude_backends":
                self.app._config_stack = [
                    ConfigScreenState(kind="sections", selected=CONFIG_MENU_OPTIONS.index("agent")),
                    ConfigScreenState(kind="group_sections", group="agent", selected=CONFIG_GROUP_SECTIONS["agent"].index("claude")),
                    ConfigScreenState(kind="claude_backends", group="agent", section="claude", selected=self.claude.select_backend_entry(popped.backend or BUILTIN_CLAUDE_BACKENDS[0])),
                ]
        elif popped and popped.kind == "claude_custom_fields":
            parent = self.app._config_state()
            if parent is None or parent.kind != "claude_backends":
                self.app._config_stack = [
                    ConfigScreenState(kind="sections", selected=CONFIG_MENU_OPTIONS.index("agent")),
                    ConfigScreenState(kind="group_sections", group="agent", selected=CONFIG_GROUP_SECTIONS["agent"].index("claude")),
                    ConfigScreenState(kind="claude_backends", group="agent", section="claude"),
                ]
        if popped and popped.kind == "show":
            self.app._show_scroll = 0
        self.app._refresh_runtime()
        if self.app._config_level == "sections":
            self.app._set_message(self.app._t("back_config_section"))
        else:
            self.app._set_message(self.app._t("back_config_fields"))

    def activate(self) -> None:
        """Handles Enter for the current config screen."""
        level = self.app._config_level
        if self.claude.handles(level):
            self.claude.activate(level)
            return
        handler = self._activate_handlers.get(level)
        if handler:
            handler()

    def _option_sections(self) -> OptionMenuState:
        return OptionMenuState("sections", self.app._config_selected, len(CONFIG_MENU_OPTIONS))

    def _option_group_sections(self) -> OptionMenuState | None:
        group = self.app._current_config_group_name()
        if group is None:
            return None
        controller = self._section_controllers.get(group)
        if controller is None:
            return None
        return controller.option_menu()

    def _option_fields(self) -> OptionMenuState | None:
        group = self.app._current_config_group_name()
        if group is None:
            return None
        controller = self._section_controllers.get(group)
        if controller is None:
            return None
        return controller.option_fields()

    def _option_choices(self) -> OptionMenuState | None:
        path = self.app._config_editing_path
        if not path:
            return None
        return OptionMenuState("choices", self.app._config_choice_selected, len(self.app._choices_for_path(path)))

    def _activate_sections(self) -> None:
        group = CONFIG_MENU_OPTIONS[self.app._config_selected]
        if group == "language":
            self.language.activate()
            return
        self.app._push_config_state(ConfigScreenState(kind="group_sections", group=group))
        self.app._refresh_runtime()

    def _activate_group_sections(self) -> None:
        group = self.app._config_group
        assert group is not None
        self._section_controllers[group].activate_group_selection()

    def _activate_fields(self) -> None:
        group = self.app._config_group
        assert group is not None
        self._section_controllers[group].activate_field_selection()

    def _activate_choices(self) -> None:
        path = self.app._config_editing_path
        assert path is not None
        _display, actual = self.app._choices_for_path(path)[self.app._config_choice_selected]
        self.app._service.set_config_value(path, actual)
        self.app._pop_config_state()
        self.app._refresh_runtime()
        if path == "ui.language":
            self.app._set_message(self.app._t("language_done"))
        else:
            self.app._set_message(f"{self.app._t('value_saved', field=path)} {self.app._t('restart_required')}")


class ConfigPanelRenderer(BaseConfigRenderer):
    """Routes config rendering to section, Claude, or form renderers."""

    def __init__(self, app) -> None:
        """Initializes child renderers."""
        super().__init__(app)
        self.sections = SectionConfigRenderer(app)
        self.claude = ClaudeConfigRenderer(app)
        self.forms = FormConfigRenderer(app)

    def render_menu(self, config: dict) -> str:
        return self.sections.render_menu(config)

    def render_group(self, config: dict) -> str:
        return self.sections.render_group(config)

    def render_fields(self, config: dict) -> str:
        return self.sections.render_fields(config)

    def render_claude_backends(self, config: dict) -> str:
        return self.claude.render_claude_backends(config)

    def render_claude_custom_fields(self) -> str:
        return self.claude.render_claude_custom_fields()

    def render_claude_backend_fields(self, config: dict) -> str:
        return self.claude.render_claude_backend_fields(config)

    def render_claude_backend_models(self, config: dict) -> str:
        return self.claude.render_claude_backend_models(config)

    def render_claude_backend_model_actions(self, config: dict) -> str:
        return self.claude.render_claude_backend_model_actions(config)

    def extra_env_payload(self, config: dict) -> dict[str, str]:
        return self.claude.extra_env_payload(config)

    def extra_env_entries(self, config: dict) -> list[tuple[str, str]]:
        return self.claude.extra_env_entries(config)

    def render_extra_env_list(self, config: dict) -> str:
        return self.claude.render_extra_env_list(config)

    def render_extra_env_actions(self, config: dict) -> str:
        return self.claude.render_extra_env_actions(config)

    def render_choices(self, config: dict) -> str:
        return self.forms.render_choices(config)

    def render_input(self, config: dict) -> str:
        return self.forms.render_input(config)
