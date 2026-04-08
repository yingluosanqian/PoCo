from __future__ import annotations

from dataclasses import dataclass

from poco.interaction.card_models import (
    ActionIntent,
    DispatchStatus,
    IntentDispatchResult,
    RefreshMode,
    ResourceRefs,
    ViewModel,
)
from poco.project.bootstrap import ProjectBootstrapError, ProjectBootstrapper
from poco.project.controller import ProjectController, ProjectNotFoundError


@dataclass(slots=True)
class ProjectIntentHandler:
    project_controller: ProjectController
    bootstrapper: ProjectBootstrapper | None = None

    def handle(self, intent: ActionIntent) -> IntentDispatchResult:
        if intent.intent_key == "project.list":
            return self._list_projects(intent)
        if intent.intent_key == "project.create":
            return self._create_project(intent)
        if intent.intent_key == "project.open":
            return self._open_project(intent)
        if intent.intent_key == "project.bind_group":
            return self._bind_group(intent)
        if intent.intent_key == "project.archive":
            return self._archive_project(intent)
        return IntentDispatchResult(
            status=DispatchStatus.REJECTED,
            intent_key=intent.intent_key,
            resource_refs=intent.resource_refs,
            view_model=None,
            refresh_mode=RefreshMode.ACK_ONLY,
            message=f"Unsupported project intent: {intent.intent_key}",
        )

    def _list_projects(self, intent: ActionIntent) -> IntentDispatchResult:
        projects = self.project_controller.list_projects_for_user(intent.actor_id)
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(),
            view_model=_project_list_view_model(projects),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message="Projects loaded.",
        )

    def _create_project(self, intent: ActionIntent) -> IntentDispatchResult:
        name = str(intent.payload.get("name", "")).strip() or "Untitled Project"
        backend = str(intent.payload.get("backend", "codex")).strip() or "codex"
        project = self.project_controller.create_project(
            name=name,
            created_by=intent.actor_id,
            backend=backend,
            repo=_optional_string(intent.payload.get("repo")),
            workdir=_optional_string(intent.payload.get("workdir")),
        )
        if self.bootstrapper is not None:
            try:
                bootstrap = self.bootstrapper.bootstrap_project(
                    project=project,
                    actor_id=intent.actor_id,
                )
            except ProjectBootstrapError as exc:
                self.project_controller.delete_project(project.id)
                return _rejected(intent, f"Failed to create project group: {exc}")
            if bootstrap.group_chat_id is not None:
                project = self.project_controller.bind_group(
                    project.id,
                    bootstrap.group_chat_id,
                )

        message = f"Project created: {project.name}"
        if project.group_chat_id:
            message = f"Project created with group: {project.name}"
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_project_detail_view_model(project),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=message,
        )

    def _open_project(self, intent: ActionIntent) -> IntentDispatchResult:
        project_id = _required_id(intent.project_id, "project_id")
        try:
            project = self.project_controller.get_project(project_id)
        except ProjectNotFoundError as exc:
            return _rejected(intent, str(exc))
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_project_detail_view_model(project),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Opened project: {project.name}",
        )

    def _bind_group(self, intent: ActionIntent) -> IntentDispatchResult:
        project_id = _required_id(intent.project_id, "project_id")
        group_chat_id = _required_id(
            _optional_string(intent.payload.get("group_chat_id")),
            "group_chat_id",
        )
        try:
            project = self.project_controller.bind_group(project_id, group_chat_id)
        except ProjectNotFoundError as exc:
            return _rejected(intent, str(exc))
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_project_detail_view_model(project),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Group bound to project: {project.name}",
        )

    def _archive_project(self, intent: ActionIntent) -> IntentDispatchResult:
        project_id = _required_id(intent.project_id, "project_id")
        try:
            project = self.project_controller.archive_project(project_id)
        except ProjectNotFoundError as exc:
            return _rejected(intent, str(exc))
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_project_list_view_model(self.project_controller.list_projects()),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Archived project: {project.name}",
        )


@dataclass(slots=True)
class WorkspaceIntentHandler:
    project_controller: ProjectController

    def handle(self, intent: ActionIntent) -> IntentDispatchResult:
        if intent.intent_key not in {"workspace.open", "workspace.refresh"}:
            return _rejected(intent, f"Unsupported workspace intent: {intent.intent_key}")
        project_id = _required_id(intent.project_id, "project_id")
        try:
            project = self.project_controller.get_project(project_id)
        except ProjectNotFoundError as exc:
            return _rejected(intent, str(exc))
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=ViewModel(
                "workspace_overview",
                {
                    "project": project.to_dict(),
                    "active_session_summary": "No active session yet.",
                    "latest_task_status": None,
                    "pending_approvals": 0,
                    "latest_result_summary": None,
                },
            ),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Workspace ready for {project.name}",
        )


def build_dm_project_list_result(
    project_controller: ProjectController,
    *,
    actor_id: str | None = None,
) -> IntentDispatchResult:
    if actor_id:
        projects = project_controller.list_projects_for_user(actor_id)
    else:
        projects = project_controller.list_projects()
    return IntentDispatchResult(
        status=DispatchStatus.OK,
        intent_key="project.list",
        resource_refs=ResourceRefs(),
        view_model=_project_list_view_model(projects),
        refresh_mode=RefreshMode.REPLACE_CURRENT,
        message="Projects loaded.",
    )


def _project_list_view_model(projects) -> ViewModel:
    return ViewModel(
        "project_list",
        {
            "projects": [project.to_dict() for project in projects],
        },
    )


def _project_detail_view_model(project) -> ViewModel:
    return ViewModel(
        "project_detail",
        {
            "project": project.to_dict(),
            "recent_session_summary": None,
        },
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_id(value: str | None, label: str) -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"Missing required field: {label}")
    return str(value).strip()


def _rejected(intent: ActionIntent, message: str) -> IntentDispatchResult:
    return IntentDispatchResult(
        status=DispatchStatus.REJECTED,
        intent_key=intent.intent_key,
        resource_refs=intent.resource_refs,
        view_model=None,
        refresh_mode=RefreshMode.ACK_ONLY,
        message=message,
    )
