from __future__ import annotations

from threading import RLock

from poco.project.models import Project
from poco.task.models import Task


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
