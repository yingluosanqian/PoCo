"""Root menu controller for the TUI."""

from __future__ import annotations

from .config.types import ConfigScreenState, ROOT_MENU_OPTIONS


class RootMenuController:
    """Handles top-level menu selection and navigation."""

    def __init__(self, app) -> None:
        """Initializes the controller.

        Args:
            app: The owning ``PoCoTui`` instance.
        """
        self.app = app

    def activate(self) -> None:
        """Activates the currently selected root menu entry."""
        choice = ROOT_MENU_OPTIONS[self.app._root_selected]
        if choice == "language":
            self.app._config_menu.language.activate()
            self.app._set_message(self.app._t("config_pick"))
            return
        if choice in {"agent", "bot", "poco"}:
            self.app._config_stack = [
                ConfigScreenState(kind="group_sections", group=choice, selected=0)
            ]
            self.app._refresh_runtime()
            self.app._set_message(self.app._t("config_pick"))
            return
        if choice == "quit":
            self.app.exit()
