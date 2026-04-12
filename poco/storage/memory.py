from __future__ import annotations

from threading import RLock

from poco.project.models import Project
from poco.session.models import Session
from poco.task.models import Task
from poco.workspace.models import WorkspaceContext


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock = RLock()

    def save(self, task: Task) -> Task:
        with self._lock:
            self._tasks[task.id] = task
            return task

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_all(self) -> list[Task]:
        with self._lock:
            return list(self._tasks.values())

    def delete_by_project_id(self, project_id: str) -> None:
        with self._lock:
            task_ids = [
                task_id
                for task_id, task in self._tasks.items()
                if task.project_id == project_id
            ]
            for task_id in task_ids:
                self._tasks.pop(task_id, None)


class InMemoryProjectStore:
    def __init__(self) -> None:
        self._projects: dict[str, Project] = {}
        self._lock = RLock()

    def save(self, project: Project) -> Project:
        with self._lock:
            self._projects[project.id] = project
            return project

    def get(self, project_id: str) -> Project | None:
        with self._lock:
            return self._projects.get(project_id)

    def list_all(self) -> list[Project]:
        with self._lock:
            return list(self._projects.values())

    def delete(self, project_id: str) -> None:
        with self._lock:
            self._projects.pop(project_id, None)


class InMemoryWorkspaceContextStore:
    def __init__(self) -> None:
        self._contexts: dict[str, WorkspaceContext] = {}
        self._lock = RLock()

    def save(self, context: WorkspaceContext) -> WorkspaceContext:
        with self._lock:
            self._contexts[context.project_id] = context
            return context

    def get(self, project_id: str) -> WorkspaceContext | None:
        with self._lock:
            return self._contexts.get(project_id)

    def delete(self, project_id: str) -> None:
        with self._lock:
            self._contexts.pop(project_id, None)


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = RLock()

    def save(self, session: Session) -> Session:
        with self._lock:
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_all(self) -> list[Session]:
        with self._lock:
            return list(self._sessions.values())

    def delete_by_project_id(self, project_id: str) -> None:
        with self._lock:
            session_ids = [
                session_id
                for session_id, session in self._sessions.items()
                if session.project_id == project_id
            ]
            for session_id in session_ids:
                self._sessions.pop(session_id, None)
