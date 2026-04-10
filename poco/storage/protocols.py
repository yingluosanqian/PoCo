from __future__ import annotations

from typing import Protocol

from poco.project.models import Project
from poco.session.models import Session
from poco.task.models import Task
from poco.workspace.models import WorkspaceContext


class TaskStore(Protocol):
    def save(self, task: Task) -> Task:
        ...

    def get(self, task_id: str) -> Task | None:
        ...

    def list_all(self) -> list[Task]:
        ...


class ProjectStore(Protocol):
    def save(self, project: Project) -> Project:
        ...

    def get(self, project_id: str) -> Project | None:
        ...

    def list_all(self) -> list[Project]:
        ...

    def delete(self, project_id: str) -> None:
        ...


class WorkspaceContextStore(Protocol):
    def save(self, context: WorkspaceContext) -> WorkspaceContext:
        ...

    def get(self, project_id: str) -> WorkspaceContext | None:
        ...


class SessionStore(Protocol):
    def save(self, session: Session) -> Session:
        ...

    def get(self, session_id: str) -> Session | None:
        ...

    def list_all(self) -> list[Session]:
        ...
