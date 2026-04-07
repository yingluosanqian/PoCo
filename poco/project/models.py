from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Project:
    id: str
    name: str
    created_by: str
    backend: str = "codex"
    repo: str | None = None
    workdir: str | None = None
    group_chat_id: str | None = None
    archived: bool = False
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def bind_group(self, group_chat_id: str) -> None:
        self.group_chat_id = group_chat_id
        self.updated_at = utc_now()

    def archive(self) -> None:
        self.archived = True
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "created_by": self.created_by,
            "backend": self.backend,
            "repo": self.repo,
            "workdir": self.workdir,
            "group_chat_id": self.group_chat_id,
            "archived": self.archived,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

