from __future__ import annotations

from threading import RLock
from uuid import uuid4

from poco.project.models import Project
from poco.storage.protocols import ProjectStore


class ProjectNotFoundError(ValueError):
    pass


class ProjectConfigError(ValueError):
    pass


class ProjectController:
    def __init__(self, store: ProjectStore) -> None:
        self._store = store
        self._lock = RLock()

    def create_project(
        self,
        *,
        name: str,
        created_by: str,
        backend: str = "codex",
        repo: str | None = None,
        workdir: str | None = None,
        group_chat_id: str | None = None,
    ) -> Project:
        with self._lock:
            project = Project(
                id=uuid4().hex[:8],
                name=name,
                created_by=created_by,
                backend=backend,
                repo=repo,
                workdir=workdir,
                group_chat_id=group_chat_id,
            )
            self._store.save(project)
            return project

    def get_project(self, project_id: str) -> Project:
        with self._lock:
            project = self._store.get(project_id)
            if project is None:
                raise ProjectNotFoundError(f"Project not found: {project_id}")
            return project

    def list_projects(self) -> list[Project]:
        with self._lock:
            return self._store.list_all()

    def list_projects_for_user(
        self,
        user_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Project]:
        with self._lock:
            projects = [
                project
                for project in self._store.list_all()
                if project.created_by == user_id
            ]
            if include_archived:
                return projects
            return [project for project in projects if not project.archived]

    def bind_group(self, project_id: str, group_chat_id: str) -> Project:
        with self._lock:
            project = self.get_project(project_id)
            project.bind_group(group_chat_id)
            self._store.save(project)
            return project

    def bind_workspace_message(self, project_id: str, message_id: str) -> Project:
        with self._lock:
            project = self.get_project(project_id)
            project.bind_workspace_message(message_id)
            self._store.save(project)
            return project

    def get_project_by_group_chat_id(self, group_chat_id: str) -> Project | None:
        with self._lock:
            for project in self._store.list_all():
                if project.group_chat_id == group_chat_id:
                    return project
            return None

    def archive_project(self, project_id: str) -> Project:
        with self._lock:
            project = self.get_project(project_id)
            project.archive()
            self._store.save(project)
            return project

    def add_dir_preset(self, project_id: str, preset: str) -> Project:
        normalized = preset.strip()
        if not normalized:
            raise ProjectConfigError("Preset path cannot be empty.")
        with self._lock:
            project = self.get_project(project_id)
            project.add_workdir_preset(normalized)
            self._store.save(project)
            return project

    def delete_project(self, project_id: str) -> None:
        with self._lock:
            project = self._store.get(project_id)
            if project is None:
                raise ProjectNotFoundError(f"Project not found: {project_id}")
            self._store.delete(project_id)
