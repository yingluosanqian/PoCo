"""State models for the refactored PoCo TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ScreenKind(str, Enum):
    BIND_BOT = "bind_bot"
    WORKSPACE = "workspace"


class Platform(str, Enum):
    FEISHU = "feishu"
    SLACK = "slack"
    DISCORD = "discord"


class BindBotStep(str, Enum):
    PLATFORM = "platform"
    ACCOUNT = "account"
    APP_ID = "app_id"
    APP_SECRET = "app_secret"


class WorkspaceSection(str, Enum):
    AGENT = "agent"
    BOT = "bot"
    POCO = "poco"
    LANGUAGE = "language"


class SubviewId(str, Enum):
    SHOW_CONFIG = "show_config"
    CLAUDE_BACKENDS = "claude_backends"
    CLAUDE_BACKEND_SETTINGS = "claude_backend_settings"
    BOT_ADVANCED = "bot_advanced"


@dataclass(frozen=True)
class BotAccount:
    app_id: str
    app_name: str = ""
    alias: str = ""

    @property
    def display_name(self) -> str:
        return self.alias or self.app_name or self.app_id


@dataclass
class BindBotDraft:
    app_id: str = ""
    app_secret: str = ""


@dataclass
class BindBotState:
    step: BindBotStep = BindBotStep.PLATFORM
    selected_index: int = 0
    platform: Platform | None = None
    saved_bots: list[BotAccount] = field(default_factory=list)
    draft: BindBotDraft | None = None
    notice: str = ""


@dataclass
class SectionState:
    selected_index: int = 0
    scroll: int = 0
    subview: SubviewId | None = None


@dataclass
class InputState:
    field_key: str
    label: str
    secret: bool = False
    placeholder: str = ""
    value: str = ""
    steps: list[str] = field(default_factory=lambda: ["value"])
    current: int = 0
    draft: dict[str, str] = field(default_factory=dict)


@dataclass
class ChoiceState:
    field_key: str
    label: str
    options: list[tuple[str, str]]
    selected_index: int = 0


@dataclass
class RuntimeState:
    relay_running: bool = False
    relay_error: str = ""


@dataclass
class WorkspaceState:
    active_section: WorkspaceSection = WorkspaceSection.AGENT
    sections: dict[WorkspaceSection, SectionState] = field(
        default_factory=lambda: {
            WorkspaceSection.AGENT: SectionState(),
            WorkspaceSection.BOT: SectionState(),
            WorkspaceSection.POCO: SectionState(),
            WorkspaceSection.LANGUAGE: SectionState(),
        }
    )
    input_state: InputState | None = None
    choice_state: ChoiceState | None = None


@dataclass
class AppState:
    screen: ScreenKind = ScreenKind.BIND_BOT
    bind_bot: BindBotState = field(default_factory=BindBotState)
    workspace: WorkspaceState = field(default_factory=WorkspaceState)
    runtime: RuntimeState = field(default_factory=RuntimeState)
