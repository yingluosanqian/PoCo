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
from poco.workspace.controller import WorkspaceContextController, WorkspaceContextError


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
        if intent.intent_key == "project.configure_agent":
            return self._open_agent_config(intent)
        if intent.intent_key == "project.configure_repo":
            return self._open_repo_config(intent)
        if intent.intent_key == "project.configure_default_dir":
            return self._open_default_dir_config(intent)
        if intent.intent_key == "project.manage_dir_presets":
            return self._open_dir_presets(intent)
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
                try:
                    self.bootstrapper.notify_project_workspace(
                        project=project,
                        actor_id=intent.actor_id,
                    )
                except Exception:
                    pass

        message = f"Project created: {project.name}"
        if project.group_chat_id:
            message = f"Project created with group: {project.name}"
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_project_config_view_model(project),
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
            view_model=_project_config_view_model(project),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Opened project: {project.name}",
        )

    def _open_agent_config(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_project_agent_config_view_model(project),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Agent config for {project.name}",
        )

    def _open_repo_config(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_project_repo_config_view_model(project),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Repo config for {project.name}",
        )

    def _open_default_dir_config(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_project_default_dir_config_view_model(project),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Default dir config for {project.name}",
        )

    def _open_dir_presets(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_project_dir_presets_view_model(project),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Dir presets for {project.name}",
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
            view_model=_project_config_view_model(project),
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
    workspace_controller: WorkspaceContextController

    def handle(self, intent: ActionIntent) -> IntentDispatchResult:
        if intent.intent_key == "workspace.open_workdir_switcher":
            return self._open_workdir_switcher(intent)
        if intent.intent_key == "workspace.use_default_dir":
            return self._open_use_default_dir(intent)
        if intent.intent_key == "workspace.choose_preset":
            return self._open_choose_preset(intent)
        if intent.intent_key == "workspace.use_recent_dir":
            return self._open_use_recent_dir(intent)
        if intent.intent_key == "workspace.enter_path":
            return self._open_enter_path(intent)
        if intent.intent_key == "workspace.apply_entered_path":
            return self._apply_entered_path(intent)
        if intent.intent_key not in {"workspace.open", "workspace.refresh"}:
            return _rejected(intent, f"Unsupported workspace intent: {intent.intent_key}")
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        context = self.workspace_controller.get_context(project)
        return build_workspace_overview_result(project, context=context)

    def _open_workdir_switcher(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        context = self.workspace_controller.get_context(project)
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_workspace_workdir_switcher_view_model(project, context=context),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Workdir switcher for {project.name}",
        )

    def _open_use_default_dir(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        try:
            context = self.workspace_controller.use_default_workdir(project)
        except WorkspaceContextError as exc:
            return _rejected(intent, str(exc))
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_workspace_use_default_dir_view_model(project, context=context),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Using default dir for {project.name}",
        )

    def _open_choose_preset(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_workspace_choose_preset_view_model(project),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Preset dirs for {project.name}",
        )

    def _open_use_recent_dir(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_workspace_recent_dirs_view_model(project),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Recent dirs for {project.name}",
        )

    def _open_enter_path(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        context = self.workspace_controller.get_context(project)
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_workspace_enter_path_view_model(project, context=context),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Manual dir entry for {project.name}",
        )

    def _apply_entered_path(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        workdir = _extract_workdir_path(intent.payload)
        try:
            context = self.workspace_controller.use_manual_workdir(project, workdir)
        except WorkspaceContextError as exc:
            return _rejected(intent, str(exc))
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_workspace_workdir_switcher_view_model(project, context=context),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Updated workdir for {project.name}",
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


def build_workspace_overview_result(project, *, context=None) -> IntentDispatchResult:
    current_workdir = None
    workdir_source = "unset"
    if context is not None:
        current_workdir = context.active_workdir
        workdir_source = context.workdir_source
    elif project.workdir:
        current_workdir = project.workdir
        workdir_source = "default"
    return IntentDispatchResult(
        status=DispatchStatus.OK,
        intent_key="workspace.open",
        resource_refs=ResourceRefs(project_id=project.id),
        view_model=ViewModel(
            "workspace_overview",
            {
                "project": project.to_dict(),
                "active_session_summary": "No active session yet.",
                "latest_task_status": None,
                "pending_approvals": 0,
                "latest_result_summary": None,
                "current_workdir": current_workdir,
                "workdir_source": workdir_source,
            },
        ),
        refresh_mode=RefreshMode.REPLACE_CURRENT,
        message=f"Workspace ready for {project.name}",
    )


def _project_list_view_model(projects) -> ViewModel:
    return ViewModel(
        "project_list",
        {
            "projects": [project.to_dict() for project in projects],
        },
    )


def _project_config_view_model(project) -> ViewModel:
    return ViewModel(
        "project_config",
        {
            "project": project.to_dict(),
            "recent_session_summary": None,
        },
    )


def _project_agent_config_view_model(project) -> ViewModel:
    return ViewModel(
        "project_agent_config",
        {
            "project": project.to_dict(),
            "current_agent": project.backend,
            "note": "Agent is treated as project identity. Changing it later should be a high-cost migration, not a casual switch.",
        },
    )


def _project_repo_config_view_model(project) -> ViewModel:
    return ViewModel(
        "project_repo_config",
        {
            "project": project.to_dict(),
            "repo_root": project.repo,
            "note": "Repo binding is not implemented yet. This card reserves the DM control-plane entrypoint.",
        },
    )


def _project_default_dir_config_view_model(project) -> ViewModel:
    return ViewModel(
        "project_default_dir_config",
        {
            "project": project.to_dict(),
            "default_workdir": project.workdir,
            "note": "Default workdir configuration is not implemented yet. Working dir remains a session-level stance.",
        },
    )


def _project_dir_presets_view_model(project) -> ViewModel:
    return ViewModel(
        "project_dir_presets",
        {
            "project": project.to_dict(),
            "presets": [],
            "note": "Dir preset management is not implemented yet. This card reserves the DM management surface.",
        },
    )


def _workspace_workdir_switcher_view_model(project, *, context) -> ViewModel:
    return ViewModel(
        "workspace_workdir_switcher",
        {
            "project": project.to_dict(),
            "current_agent": project.backend,
            "current_workdir": context.active_workdir,
            "source": context.workdir_source,
        },
    )


def _workspace_use_default_dir_view_model(project, *, context) -> ViewModel:
    return ViewModel(
        "workspace_use_default_dir",
        {
            "project": project.to_dict(),
            "default_workdir": project.workdir,
            "current_workdir": context.active_workdir,
            "source": context.workdir_source,
            "note": "Default-dir switching is now active for the current in-memory workspace context. It is not yet persisted across service restarts.",
        },
    )


def _workspace_choose_preset_view_model(project) -> ViewModel:
    return ViewModel(
        "workspace_choose_preset",
        {
            "project": project.to_dict(),
            "presets": [],
            "note": "Preset switching is not implemented yet. Presets remain a DM-managed project-level list.",
        },
    )


def _workspace_recent_dirs_view_model(project) -> ViewModel:
    return ViewModel(
        "workspace_recent_dirs",
        {
            "project": project.to_dict(),
            "recent_dirs": [],
            "note": "Recent-dir switching is not implemented yet. This card reserves the group-side quick path.",
        },
    )


def _workspace_enter_path_view_model(project, *, context) -> ViewModel:
    return ViewModel(
        "workspace_enter_path",
        {
            "project": project.to_dict(),
            "current_workdir": context.active_workdir,
            "note": "Manual path entry is a fallback path. It updates the current in-memory workspace context only.",
        },
    )


def _get_project_or_reject(
    project_controller: ProjectController,
    intent: ActionIntent,
):
    project_id = _required_id(intent.project_id, "project_id")
    try:
        return project_controller.get_project(project_id)
    except ProjectNotFoundError as exc:
        return _rejected(intent, str(exc))


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_workdir_path(payload: dict[str, object]) -> str:
    direct = _optional_string(payload.get("workdir"))
    if direct is not None:
        return direct
    input_value = payload.get("input_value")
    if isinstance(input_value, str) and input_value.strip():
        return input_value.strip()
    if isinstance(input_value, dict):
        nested = _optional_string(input_value.get("workdir"))
        if nested is not None:
            return nested
    return ""


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
