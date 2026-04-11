from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def utc_now() -> datetime:
    return datetime.now(UTC)


class SessionStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


@dataclass(slots=True)
class Session:
    id: str
    project_id: str
    created_by: str
    status: SessionStatus = SessionStatus.ACTIVE
    backend_session_id: str | None = None
    latest_task_id: str | None = None
    latest_prompt: str | None = None
    latest_result_preview: str | None = None
    latest_task_status: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def update_from_task(
        self,
        *,
        task_id: str,
        prompt: str,
        status: str,
        result_preview: str | None,
        backend_session_id: str | None = None,
    ) -> None:
        if backend_session_id:
            self.backend_session_id = backend_session_id
        self.latest_task_id = task_id
        self.latest_prompt = prompt
        self.latest_task_status = status
        self.latest_result_preview = result_preview
        self.updated_at = utc_now()

    def summary_text(self) -> str:
        lines = [f"`{self.id}` · `{self.status.value}`"]
        if self.latest_prompt:
            lines.append(f"last prompt: `{self.latest_prompt[:80]}`")
        if self.latest_task_status:
            lines.append(f"last task: `{self.latest_task_status}`")
        if self.latest_result_preview:
            lines.append(f"last result: `{self.latest_result_preview[:120]}`")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "created_by": self.created_by,
            "status": self.status.value,
            "backend_session_id": self.backend_session_id,
            "latest_task_id": self.latest_task_id,
            "latest_prompt": self.latest_prompt,
            "latest_result_preview": self.latest_result_preview,
            "latest_task_status": self.latest_task_status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
