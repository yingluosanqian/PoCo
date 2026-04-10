from __future__ import annotations

from threading import RLock

from poco.project.models import Project
from poco.storage.protocols import WorkspaceContextStore
from poco.workspace.models import WorkspaceContext


class WorkspaceContextError(ValueError):
    pass


class WorkspaceContextController:
    def __init__(self, store: WorkspaceContextStore) -> None:
        self._store = store
        self._lock = RLock()

    def get_context(self, project: Project) -> WorkspaceContext:
        with self._lock:
            context = self._store.get(project.id)
            if context is not None:
                return context
            if project.workdir:
                return WorkspaceContext(
                    project_id=project.id,
                    active_workdir=project.workdir,
                    workdir_source="default",
                )
            return WorkspaceContext(project_id=project.id)

    def set_active_workdir(
        self,
        project: Project,
        *,
        workdir: str | None,
        source: str,
    ) -> WorkspaceContext:
        with self._lock:
            context = self._store.get(project.id) or WorkspaceContext(project_id=project.id)
            context.set_active_workdir(workdir, source=source)
            self._store.save(context)
            return context

    def use_default_workdir(self, project: Project) -> WorkspaceContext:
        if not project.workdir:
            raise WorkspaceContextError(
                f"Project {project.name} has no default workdir configured."
            )
        return self.set_active_workdir(
            project,
            workdir=project.workdir,
            source="default",
        )

    def use_manual_workdir(self, project: Project, workdir: str) -> WorkspaceContext:
        normalized = workdir.strip()
        if not normalized:
            raise WorkspaceContextError("Workdir path cannot be empty.")
        return self.set_active_workdir(
            project,
            workdir=normalized,
            source="manual",
        )

    def use_preset_workdir(self, project: Project, preset: str) -> WorkspaceContext:
        normalized = preset.strip()
        if not normalized:
            raise WorkspaceContextError("Preset path cannot be empty.")
        if normalized not in project.workdir_presets:
            raise WorkspaceContextError(
                f"Preset path is not configured for project {project.name}: {normalized}"
            )
        return self.set_active_workdir(
            project,
            workdir=normalized,
            source="preset",
        )
