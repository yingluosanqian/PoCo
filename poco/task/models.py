from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def utc_now() -> datetime:
    return datetime.now(UTC)


class TaskStatus(StrEnum):
    CREATED = "created"
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
    status: TaskStatus = TaskStatus.CREATED
    events: list[TaskEvent] = field(default_factory=list)
    awaiting_confirmation_reason: str | None = None
    result_summary: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def add_event(self, kind: str, message: str) -> None:
        self.events.append(TaskEvent(kind=kind, message=message))
        self.updated_at = utc_now()

    def set_status(self, status: TaskStatus) -> None:
        self.status = status
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "source": self.source,
            "requester_id": self.requester_id,
            "prompt": self.prompt,
            "status": self.status.value,
            "awaiting_confirmation_reason": self.awaiting_confirmation_reason,
            "result_summary": self.result_summary,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "events": [event.to_dict() for event in self.events],
        }
