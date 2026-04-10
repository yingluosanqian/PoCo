from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class WorkspaceContext:
    project_id: str
    active_workdir: str | None = None
    workdir_source: str = "unset"
    updated_at: datetime = field(default_factory=utc_now)

    def set_active_workdir(self, workdir: str | None, *, source: str) -> None:
        self.active_workdir = workdir
        self.workdir_source = source
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "active_workdir": self.active_workdir,
            "workdir_source": self.workdir_source,
            "updated_at": self.updated_at.isoformat(),
        }
