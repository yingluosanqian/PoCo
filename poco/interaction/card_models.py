from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Surface(StrEnum):
    DM = "dm"
    GROUP = "group"


class DispatchStatus(StrEnum):
    OK = "ok"
    REJECTED = "rejected"
    ERROR = "error"


class RefreshMode(StrEnum):
    REPLACE_CURRENT = "replace_current"
    APPEND_NEW = "append_new"
    ACK_ONLY = "ack_only"


class RenderTarget(StrEnum):
    CURRENT_CARD = "current_card"
    NEW_MESSAGE = "new_message"
    ACK = "ack"


WRITE_INTENT_KEYS = {
    "project.create",
    "project.delete",
    "project.bind_group",
    "project.archive",
    "project.add_dir_preset",
    "workspace.use_default_dir",
    "workspace.apply_preset_dir",
    "workspace.apply_entered_path",
    "workspace.apply_model",
    "workspace.apply_agent",
    "task.submit",
    "task.stop",
    "task.approve",
    "task.reject",
}


@dataclass(frozen=True, slots=True)
class ResourceRefs:
    project_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None


@dataclass(frozen=True, slots=True)
class ViewModel:
    view_type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActionIntent:
    intent_key: str
    surface: Surface
    actor_id: str
    source_message_id: str
    request_id: str
    project_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def resource_refs(self) -> ResourceRefs:
        return ResourceRefs(
            project_id=self.project_id,
            session_id=self.session_id,
            task_id=self.task_id,
        )

    @property
    def is_write(self) -> bool:
        return self.intent_key in WRITE_INTENT_KEYS


@dataclass(frozen=True, slots=True)
class IntentDispatchResult:
    status: DispatchStatus
    intent_key: str
    resource_refs: ResourceRefs
    view_model: ViewModel | None
    refresh_mode: RefreshMode
    message: str | None = None


@dataclass(frozen=True, slots=True)
class PlatformRenderInstruction:
    surface: Surface
    render_target: RenderTarget
    template_key: str | None
    template_data: dict[str, Any]
    refresh_mode: RefreshMode
    message: str | None = None
