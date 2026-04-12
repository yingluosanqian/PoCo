from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def utc_now() -> datetime:
    return datetime.now(UTC)


class TaskStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class TaskEvent:
    kind: str
    message: str
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(slots=True)
class Task:
    id: str
    source: str
    requester_id: str
    prompt: str
    agent_backend: str = "unknown"
    effective_model: str | None = None
    effective_sandbox: str | None = None
    backend_session_id: str | None = None
    project_id: str | None = None
    session_id: str | None = None
    effective_workdir: str | None = None
    notification_message_id: str | None = None
    reply_receive_id: str | None = None
    reply_receive_id_type: str | None = None
    status: TaskStatus = TaskStatus.CREATED
    events: list[TaskEvent] = field(default_factory=list)
    awaiting_confirmation_reason: str | None = None
    live_output: str | None = None
    raw_result: str | None = None
    result_summary: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def add_event(self, kind: str, message: str) -> None:
        self.events.append(TaskEvent(kind=kind, message=message))
        self.updated_at = utc_now()

    def set_status(self, status: TaskStatus) -> None:
        self.status = status
        self.updated_at = utc_now()

    def set_notification_message_id(self, message_id: str | None) -> None:
        self.notification_message_id = message_id
        self.updated_at = utc_now()

    def set_execution_context(
        self,
        *,
        effective_model: str | None = None,
        effective_sandbox: str | None = None,
        effective_workdir: str | None = None,
        backend_session_id: str | None = None,
    ) -> None:
        self.effective_model = effective_model
        self.effective_sandbox = effective_sandbox
        self.effective_workdir = effective_workdir
        if backend_session_id is not None:
            self.backend_session_id = backend_session_id
        self.updated_at = utc_now()

    def set_result(self, raw_result: str | None) -> None:
        self.raw_result = raw_result
        self.result_summary = _result_preview(raw_result)
        self.updated_at = utc_now()

    def append_live_output(self, chunk: str, *, limit: int = 200000) -> None:
        if not chunk:
            return
        combined = f"{self.live_output or ''}{chunk}"
        if len(combined) > limit:
            combined = combined[-limit:]
        self.live_output = combined
        self.updated_at = utc_now()

    def clear_live_output(self) -> None:
        self.live_output = None
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "source": self.source,
            "requester_id": self.requester_id,
            "prompt": self.prompt,
            "agent_backend": self.agent_backend,
            "effective_model": self.effective_model,
            "effective_sandbox": self.effective_sandbox,
            "backend_session_id": self.backend_session_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "effective_workdir": self.effective_workdir,
            "notification_message_id": self.notification_message_id,
            "reply_receive_id": self.reply_receive_id,
            "reply_receive_id_type": self.reply_receive_id_type,
            "status": self.status.value,
            "awaiting_confirmation_reason": self.awaiting_confirmation_reason,
            "live_output": self.live_output,
            "raw_result": self.raw_result,
            "result_summary": self.result_summary,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "events": [event.to_dict() for event in self.events],
        }


def _result_preview(raw_result: str | None, *, limit: int = 240) -> str | None:
    if not raw_result:
        return None
    if len(raw_result) <= limit:
        return raw_result
    return f"{raw_result[: limit - 3]}..."
