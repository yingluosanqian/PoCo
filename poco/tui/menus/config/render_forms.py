"""Renderers for generic choice and input forms."""

from __future__ import annotations

from .render_base import BaseConfigRenderer


class FormConfigRenderer(BaseConfigRenderer):
    """Renders generic config choice and text-input screens."""

    def render_choices(self, config: dict) -> str:
        """Renders a choice list for the active config path."""
        assert self.app._config_editing_path is not None
        path = self.app._config_editing_path
        choices = self.app._choices_for_path(path)
        prefix = self.app._panel_prefix(
            self.app._t("config_mode"),
            breadcrumb_parts=self.breadcrumb_parts(),
            extra_lines=[
                f"[#8b949e]{self.app._t('editing_field', field=path)}[/]",
                "",
                f"[bold #fb923c]{self.app._t('current_value')}[/]",
                self.display_config_value(config, path),
            ],
        )
        entry_lines = []
        for index, (display, _actual) in enumerate(choices):
            if index == self.app._config_choice_selected:
                entry_lines.append(f"[bold #0f1117 on #fb923c]  {display}  [/]")
            else:
                entry_lines.append(f"  {display}")
        return self.app._render_windowed_options(entry_lines, self.app._config_choice_selected, prefix_lines=prefix)

    def render_input(self, config: dict) -> str:
        """Renders the active text-input form."""
        assert self.app._config_editing_path is not None
        path = self.app._config_editing_path
        prompt = self.app._t("type_value")
        if self.app._input_mode == "extra_env_key":
            prompt = self.app._t("env_key_prompt")
        elif self.app._input_mode == "extra_env_value":
            prompt = self.app._t("env_value_prompt")
        lines = self.app._panel_prefix(
            self.app._t("config_mode"),
            breadcrumb_parts=self.breadcrumb_parts(),
            extra_lines=[
                f"[#8b949e]{self.app._t('editing_field', field=path)}[/]",
                "",
                f"[bold #fb923c]{self.app._t('current_value')}[/]",
                self.display_config_value(config, path),
                "",
                f"[#8b949e]{prompt}[/]",
                f"[#8b949e]{self.app._t('input_placeholder')}[/]",
            ],
        )
        return "\n".join(lines)
