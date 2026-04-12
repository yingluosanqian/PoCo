from __future__ import annotations

from dataclasses import dataclass

from poco.interaction.card_models import (
    ActionIntent,
    DispatchStatus,
    IntentDispatchResult,
    RefreshMode,
    ResourceRefs,
    Surface,
    ViewModel,
)
from poco.project.bootstrap import ProjectBootstrapError, ProjectBootstrapper
from poco.project.controller import ProjectConfigError, ProjectController, ProjectNotFoundError
from poco.session.controller import SessionController
from poco.task.controller import TaskController, TaskNotFoundError, TaskStateError
from poco.task.dispatcher import AsyncTaskDispatcher
from poco.workspace.controller import WorkspaceContextController, WorkspaceContextError


@dataclass(slots=True)
class ProjectIntentHandler:
    project_controller: ProjectController
    bootstrapper: ProjectBootstrapper | None = None

    def handle(self, intent: ActionIntent) -> IntentDispatchResult:
        if intent.intent_key == "project.home":
            return self._home(intent)
        if intent.intent_key == "project.new":
            return self._open_new_project(intent)
        if intent.intent_key == "project.manage":
            return self._manage_projects(intent)
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
        if intent.intent_key == "project.add_dir_preset":
            return self._add_dir_preset(intent)
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

    def _home(self, intent: ActionIntent) -> IntentDispatchResult:
        projects = self.project_controller.list_projects_for_user(intent.actor_id)
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(),
            view_model=_project_home_view_model(projects),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message="DM home loaded.",
        )

    def _open_new_project(self, intent: ActionIntent) -> IntentDispatchResult:
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(),
            view_model=_project_create_view_model(),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message="New project form loaded.",
        )

    def _manage_projects(self, intent: ActionIntent) -> IntentDispatchResult:
        projects = self.project_controller.list_projects_for_user(intent.actor_id)
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(),
            view_model=_project_manage_view_model(projects),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message="Projects loaded.",
        )

    def _list_projects(self, intent: ActionIntent) -> IntentDispatchResult:
        return self._manage_projects(intent)

    def _create_project(self, intent: ActionIntent) -> IntentDispatchResult:
        name = str(intent.payload.get("name", "")).strip()
        if not name:
            return _rejected(intent, "Project name cannot be empty.")
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

    def _add_dir_preset(self, intent: ActionIntent) -> IntentDispatchResult:
        project_id = _required_id(intent.project_id, "project_id")
        preset = _extract_workdir_path(intent.payload)
        try:
            project = self.project_controller.add_dir_preset(project_id, preset)
        except (ProjectNotFoundError, ProjectConfigError) as exc:
            return _rejected(intent, str(exc))
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_project_dir_presets_view_model(project),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Added preset for {project.name}",
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
    task_controller: TaskController | None = None
    session_controller: SessionController | None = None

    def handle(self, intent: ActionIntent) -> IntentDispatchResult:
        if intent.intent_key == "workspace.use_default_dir":
            return self._open_use_default_dir(intent)
        if intent.intent_key == "workspace.choose_preset":
            return self._open_choose_preset(intent)
        if intent.intent_key == "workspace.use_recent_dir":
            return self._open_use_recent_dir(intent)
        if intent.intent_key == "workspace.enter_path":
            return self._open_enter_path(intent)
        if intent.intent_key == "workspace.choose_model":
            return self._open_choose_model(intent)
        if intent.intent_key == "workspace.apply_preset_dir":
            return self._apply_preset_dir(intent)
        if intent.intent_key == "workspace.apply_entered_path":
            return self._apply_entered_path(intent)
        if intent.intent_key == "workspace.apply_model":
            return self._apply_model(intent)
        if intent.intent_key != "workspace.open":
            return _rejected(intent, f"Unsupported workspace intent: {intent.intent_key}")
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        if intent.surface == Surface.GROUP and intent.source_message_id:
            project = self.project_controller.bind_workspace_message(
                project.id,
                intent.source_message_id,
            )
        context = self.workspace_controller.get_context(project)
        return build_workspace_overview_result(
            project,
            context=context,
            active_session=_active_project_session(self.session_controller, project.id),
            latest_task=_latest_project_task(self.task_controller, project.id),
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

    def _apply_preset_dir(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        preset = _extract_workdir_path(intent.payload)
        try:
            context = self.workspace_controller.use_preset_workdir(project, preset)
        except WorkspaceContextError as exc:
            return _rejected(intent, str(exc))
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_workspace_enter_path_view_model(project, context=context),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Using preset dir for {project.name}",
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
            view_model=build_workspace_overview_result(
                project,
                context=context,
                active_session=_active_project_session(self.session_controller, project.id),
                latest_task=_latest_project_task(self.task_controller, project.id),
            ).view_model,
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Updated workdir for {project.name}",
        )

    def _open_choose_model(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_workspace_choose_model_view_model(project),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Choose model for {project.name}",
        )

    def _apply_model(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        model = _optional_string(intent.payload.get("model"))
        project = self.project_controller.set_model(project.id, model)
        context = self.workspace_controller.get_context(project)
        return build_workspace_overview_result(
            project,
            context=context,
            active_session=_active_project_session(self.session_controller, project.id),
            latest_task=_latest_project_task(self.task_controller, project.id),
            message=f"Model updated for {project.name}",
        )


@dataclass(slots=True)
class TaskIntentHandler:
    project_controller: ProjectController
    workspace_controller: WorkspaceContextController
    task_controller: TaskController
    session_controller: SessionController | None = None
    dispatcher: AsyncTaskDispatcher | None = None

    def handle(self, intent: ActionIntent) -> IntentDispatchResult:
        if intent.intent_key == "task.open_composer":
            return self._open_composer(intent)
        if intent.intent_key == "task.submit":
            return self._submit_task(intent)
        if intent.intent_key == "task.open":
            return self._open_task(intent)
        if intent.intent_key == "task.stop":
            return self._stop_task(intent)
        if intent.intent_key == "task.approve":
            return self._approve_task(intent)
        if intent.intent_key == "task.reject":
            return self._reject_task(intent)
        return _rejected(intent, f"Unsupported task intent: {intent.intent_key}")

    def _open_composer(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        context = self.workspace_controller.get_context(project)
        return IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key=intent.intent_key,
            resource_refs=ResourceRefs(project_id=project.id),
            view_model=_task_composer_view_model(project, context=context),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message=f"Task composer for {project.name}",
        )

    def _submit_task(self, intent: ActionIntent) -> IntentDispatchResult:
        project = _get_project_or_reject(self.project_controller, intent)
        if isinstance(project, IntentDispatchResult):
            return project
        prompt = _extract_prompt(intent.payload)
        if not prompt:
            return _rejected(intent, "Task prompt cannot be empty.")

        context = self.workspace_controller.get_context(project)
        reply_receive_id, reply_receive_id_type = _resolve_task_reply_target(
            project,
            actor_id=intent.actor_id,
            surface=intent.surface.value,
        )
        task = self.task_controller.create_task(
            requester_id=intent.actor_id,
            prompt=prompt,
            source="feishu_card",
            project_id=project.id,
            session_id=_resolve_active_session_id(
                self.session_controller,
                project_id=project.id,
                actor_id=intent.actor_id,
            ),
            effective_model=project.model,
            effective_workdir=context.active_workdir,
            notification_message_id=_optional_string(intent.source_message_id),
            reply_receive_id=reply_receive_id,
            reply_receive_id_type=reply_receive_id_type,
        )
        message = f"Task created for {project.name}"
        if self.task_controller.has_active_task_for_project(
            project.id,
            exclude_task_id=task.id,
        ):
            task = self.task_controller.queue_task(task.id)
            message = f"Task queued for {project.name}"
        if self.dispatcher is not None:
            if task.status.value == "created":
                self.dispatcher.dispatch_start(task.id)
        return build_task_status_result(
            task,
            message=message,
        )

    def _open_task(self, intent: ActionIntent) -> IntentDispatchResult:
        task_id = _required_id(intent.task_id, "task_id")
        try:
            task = self.task_controller.get_task(task_id)
        except TaskNotFoundError as exc:
            return _rejected(intent, str(exc))
        return build_task_status_result(
            task,
            message=f"Opened task: {task.id}",
            result_page=_positive_int(intent.payload.get("page"), default=1),
        )

    def _approve_task(self, intent: ActionIntent) -> IntentDispatchResult:
        task_id = _required_id(intent.task_id, "task_id")
        try:
            task = self.task_controller.resolve_confirmation(task_id, approved=True)
        except ValueError as exc:
            return _rejected(intent, str(exc))
        if self.dispatcher is not None:
            self.dispatcher.dispatch_resume(task.id)
        return build_task_status_result(
            task,
            message="Task approved. Resuming execution.",
        )

    def _stop_task(self, intent: ActionIntent) -> IntentDispatchResult:
        task_id = _required_id(intent.task_id, "task_id")
        try:
            task = self.task_controller.cancel_task(task_id)
        except (TaskStateError, ValueError) as exc:
            return _rejected(intent, str(exc))
        if self.dispatcher is not None and task.project_id:
            self.dispatcher.dispatch_next_queued(task.project_id)
        return build_task_status_result(
            task,
            message="Task stopped.",
        )

    def _reject_task(self, intent: ActionIntent) -> IntentDispatchResult:
        task_id = _required_id(intent.task_id, "task_id")
        try:
            task = self.task_controller.resolve_confirmation(task_id, approved=False)
        except ValueError as exc:
            return _rejected(intent, str(exc))
        if self.dispatcher is not None and task.project_id:
            self.dispatcher.dispatch_next_queued(task.project_id)
        return build_task_status_result(
            task,
            message="Task rejected.",
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
        intent_key="project.home",
        resource_refs=ResourceRefs(),
        view_model=_project_home_view_model(projects),
        refresh_mode=RefreshMode.REPLACE_CURRENT,
        message="DM home loaded.",
    )


def build_workspace_overview_result(
    project,
    *,
    context=None,
    active_session=None,
    latest_task=None,
    message: str | None = None,
) -> IntentDispatchResult:
    current_workdir = None
    workdir_source = "unset"
    if context is not None:
        current_workdir = context.active_workdir
        workdir_source = context.workdir_source
    if current_workdir is None and project.workdir:
        current_workdir = project.workdir
        workdir_source = "default"
    if current_workdir is None and latest_task is not None and latest_task.effective_workdir:
        current_workdir = latest_task.effective_workdir
        workdir_source = "task"
    latest_task_status = None
    latest_task_id = None
    current_agent = project.backend
    if latest_task is not None:
        latest_task_status = latest_task.status.value
        latest_task_id = latest_task.id
        current_agent = latest_task.agent_backend or project.backend
    current_model = None
    if latest_task is not None:
        current_model = latest_task.effective_model or project.model
    else:
        current_model = project.model
    if current_model == current_agent:
        current_model = None
    stop_enabled = latest_task_status == "running" and latest_task_id is not None
    active_session_id = None
    active_session_summary = "No active session yet."
    if active_session is not None:
        active_session_id = active_session.id
        active_session_summary = active_session.summary_text()
    return IntentDispatchResult(
        status=DispatchStatus.OK,
        intent_key="workspace.open",
        resource_refs=ResourceRefs(
            project_id=project.id,
            session_id=getattr(active_session, "id", None),
        ),
        view_model=ViewModel(
            "workspace_overview",
            {
                "project": project.to_dict(),
                "active_session_id": active_session_id,
                "active_session_summary": active_session_summary,
                "latest_task_status": latest_task_status,
                "latest_task_id": latest_task_id,
                "current_agent": current_agent,
                "current_model": current_model,
                "stop_enabled": stop_enabled,
                "pending_approvals": 0,
                "current_workdir": current_workdir,
                "workdir_source": workdir_source,
            },
        ),
        refresh_mode=RefreshMode.REPLACE_CURRENT,
        message=message or f"Workspace ready for {project.name}",
    )


def build_task_status_result(
    task,
    *,
    message: str | None = None,
    result_page: int = 1,
) -> IntentDispatchResult:
    return IntentDispatchResult(
        status=DispatchStatus.OK,
        intent_key="task.status",
        resource_refs=ResourceRefs(
            project_id=task.project_id,
            session_id=task.session_id,
            task_id=task.id,
        ),
        view_model=ViewModel(
            "task_status",
            {
                "task": task.to_dict(),
                "result_page": result_page,
            },
        ),
        refresh_mode=RefreshMode.REPLACE_CURRENT,
        message=message or f"Task updated: {task.id}",
    )


def _project_home_view_model(projects) -> ViewModel:
    project_list = list(projects)
    return ViewModel(
        "project_home",
        {
            "project_count": len(project_list),
        },
    )


def _project_create_view_model() -> ViewModel:
    return ViewModel(
        "project_create",
        {
            "default_backend": "codex",
            "backend_options": [
                {"label": "Codex", "value": "codex"},
            ],
        },
    )


def _project_manage_view_model(projects) -> ViewModel:
    return ViewModel(
        "project_manage",
        {
            "projects": [project.to_dict() for project in projects],
        },
    )


def _project_list_view_model(projects) -> ViewModel:
    return _project_manage_view_model(projects)


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
            "presets": list(project.workdir_presets),
            "note": "Dir presets are project-level defaults managed from DM. They can be applied later from group workdir switcher cards.",
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
            "presets": list(project.workdir_presets),
            "note": "Choose one of the DM-managed presets to update the current workspace context.",
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
            "note": "Apply updates the current workspace and returns to the main workspace card.",
        },
    )


def _workspace_choose_model_view_model(project) -> ViewModel:
    return ViewModel(
        "workspace_choose_model",
        {
            "project": project.to_dict(),
            "current_model": project.model,
            "options": [
                {"label": "Clear Model", "value": ""},
                {"label": "gpt-5.4", "value": "gpt-5.4"},
                {"label": "gpt-5.4-mini", "value": "gpt-5.4-mini"},
                {"label": "gpt-5.3-codex", "value": "gpt-5.3-codex"},
                {"label": "gpt-5.3-codex-spark", "value": "gpt-5.3-codex-spark"},
            ],
            "note": "Apply updates the project model and returns to the main workspace card.",
        },
    )


def _task_composer_view_model(project, *, context) -> ViewModel:
    return ViewModel(
        "task_composer",
        {
            "project": project.to_dict(),
            "current_agent": project.backend,
            "current_workdir": context.active_workdir,
            "note": "Task submit now inherits the current workspace workdir and dispatches asynchronously.",
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


def _extract_prompt(payload: dict[str, object]) -> str:
    direct = _optional_string(payload.get("prompt"))
    if direct is not None:
        return direct
    input_value = payload.get("input_value")
    if isinstance(input_value, str) and input_value.strip():
        return input_value.strip()
    if isinstance(input_value, dict):
        nested = _optional_string(input_value.get("prompt"))
        if nested is not None:
            return nested
    return ""


def _positive_int(value: object, *, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _resolve_task_reply_target(project, *, actor_id: str, surface: str) -> tuple[str | None, str | None]:
    if surface == "group" and project.group_chat_id:
        return project.group_chat_id, "chat_id"
    return actor_id, "open_id"


def _latest_project_task(task_controller: TaskController | None, project_id: str):
    if task_controller is None:
        return None
    tasks = task_controller.list_tasks_for_project(project_id)
    if not tasks:
        return None
    return max(tasks, key=lambda task: task.updated_at)


def _active_project_session(session_controller: SessionController | None, project_id: str):
    if session_controller is None:
        return None
    return session_controller.get_active_session(project_id)


def _resolve_active_session_id(
    session_controller: SessionController | None,
    *,
    project_id: str,
    actor_id: str,
) -> str | None:
    if session_controller is None:
        return None
    session = session_controller.get_or_create_active_session(
        project_id=project_id,
        created_by=actor_id,
    )
    return session.id


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
