from __future__ import annotations

from threading import RLock
from uuid import uuid4

from poco.project.models import Project
from poco.storage.protocols import ProjectStore, SessionStore, TaskStore, WorkspaceContextStore


class ProjectNotFoundError(ValueError):
    pass


class ProjectConfigError(ValueError):
    pass


class ProjectController:
    def __init__(
        self,
        store: ProjectStore,
        *,
        task_store: TaskStore | None = None,
        session_store: SessionStore | None = None,
        workspace_store: WorkspaceContextStore | None = None,
    ) -> None:
        self._store = store
        self._task_store = task_store
        self._session_store = session_store
        self._workspace_store = workspace_store
        self._lock = RLock()

    def create_project(
        self,
        *,
        name: str,
        created_by: str,
        backend: str = "codex",
        backend_config: dict[str, object] | None = None,
        model: str | None = None,
        sandbox: str = "workspace-write",
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
                backend_config=backend_config or {},
                model=model,
                sandbox=sandbox,
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

    def set_model(self, project_id: str, model: str | None) -> Project:
        with self._lock:
            project = self.get_project(project_id)
            project.set_model(model)
            self._store.save(project)
            return project

    def set_model_config(
        self,
        project_id: str,
        *,
        model: str | None,
        sandbox: str | None,
    ) -> Project:
        return self.set_agent_config(
            project_id,
            backend_config={
                **({"model": model} if model else {}),
                **({"sandbox": sandbox} if sandbox else {}),
            },
        )

    def set_agent_config(
        self,
        project_id: str,
        *,
        backend_config: dict[str, object],
    ) -> Project:
        with self._lock:
            project = self.get_project(project_id)
            project.set_backend_config(backend_config)
            self._store.save(project)
            return project

    def delete_project(self, project_id: str) -> None:
        with self._lock:
            project = self._store.get(project_id)
            if project is None:
                raise ProjectNotFoundError(f"Project not found: {project_id}")
            if self._task_store is not None:
                self._task_store.delete_by_project_id(project_id)
            if self._session_store is not None:
                self._session_store.delete_by_project_id(project_id)
            if self._workspace_store is not None:
                self._workspace_store.delete(project_id)
            self._store.delete(project_id)
