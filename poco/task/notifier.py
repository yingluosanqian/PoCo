from __future__ import annotations

from typing import Protocol

from poco.interaction.card_dispatcher import build_render_instruction
from poco.interaction.card_models import Surface
from poco.platform.feishu.client import FeishuMessageClient
from poco.platform.feishu.cards import FeishuCardRenderer
from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.project.controller import ProjectController
from poco.session.controller import SessionController
from poco.task.controller import TaskController
from poco.task.models import Task, TaskStatus
from poco.task.rendering import headline_for_notification
from poco.workspace.controller import WorkspaceContextController


class TaskNotifier(Protocol):
    def notify_task(self, task: Task) -> None:
        ...


class NullTaskNotifier:
    def notify_task(self, task: Task) -> None:
        return None


class FeishuTaskNotifier:
    def __init__(
        self,
        message_client: FeishuMessageClient,
        *,
        renderer: FeishuCardRenderer | None = None,
        project_controller: ProjectController | None = None,
        session_controller: SessionController | None = None,
        task_controller: TaskController | None = None,
        workspace_controller: WorkspaceContextController | None = None,
        debug_recorder: FeishuDebugRecorder | None = None,
        running_update_interval_seconds: float = 0.1,
    ) -> None:
        self._message_client = message_client
        self._renderer = renderer or FeishuCardRenderer()
        self._project_controller = project_controller
        self._session_controller = session_controller
        self._task_controller = task_controller
        self._workspace_controller = workspace_controller
        self._debug_recorder = debug_recorder
        self._workspace_sync_signatures: dict[str, tuple[str | None, str, str | None, str | None, str | None]] = {}

    def notify_task(self, task: Task) -> None:
        task = self._freshest_task(task)
        if not task.reply_receive_id or task.reply_surface is None:
            return

        surface = task.reply_surface
        receive_id_type = _receive_id_type_from_surface(surface)
        if receive_id_type is None:
            return

        from poco.interaction.card_handlers import build_task_status_result

        instruction = build_render_instruction(
            build_task_status_result(
                task,
                task_controller=self._task_controller,
                message=headline_for_notification(task),
            ),
            surface=surface,
        )
        card = self._renderer.render(instruction)
        if task.notification_message_id:
            if self._debug_recorder is not None:
                self._debug_recorder.record_outbound_attempt(
                    source="task_notifier_update",
                    receive_id=task.reply_receive_id,
                    receive_id_type=receive_id_type,
                    text=f"[card-update] task_status:{task.status.value}",
                    task_id=task.id,
                )
            try:
                self._message_client.update_interactive(
                    message_id=task.notification_message_id,
                    card=card,
                )
                self._sync_workspace_card(task)
                return
            except Exception as exc:
                if self._debug_recorder is not None:
                    self._debug_recorder.record_error(
                        stage="task_notifier_update",
                        message=str(exc),
                        context={
                            "task_id": task.id,
                            "message_id": task.notification_message_id,
                        },
                    )
                if task.status == TaskStatus.RUNNING:
                    return

        preview = f"[card] task_status:{task.status.value}"
        if self._debug_recorder is not None:
            self._debug_recorder.record_outbound_attempt(
                source="task_notifier",
                receive_id=task.reply_receive_id,
                receive_id_type=receive_id_type,
                text=preview,
                task_id=task.id,
            )
        try:
            result = self._message_client.send_interactive(
                receive_id=task.reply_receive_id,
                receive_id_type=receive_id_type,
                card=card,
            )
            task.set_notification_message_id(result.message_id)
            if self._task_controller is not None:
                task = self._task_controller.bind_notification_message(
                    task.id,
                    result.message_id,
                )
            self._sync_workspace_card(task)
            return
        except Exception as exc:
            if self._debug_recorder is not None:
                self._debug_recorder.record_error(
                    stage="task_notifier",
                    message=str(exc),
                    context={
                        "task_id": task.id,
                        "receive_id": task.reply_receive_id,
                        "receive_id_type": receive_id_type,
                        "mode": "interactive",
                    },
                )
            raise

    def _freshest_task(self, task: Task) -> Task:
        if self._task_controller is None:
            return task
        try:
            latest = self._task_controller.get_task(task.id)
        except Exception:
            return task
        if latest.updated_at >= task.updated_at:
            return latest
        return task

    def _sync_workspace_card(self, task: Task) -> None:
        if (
            self._project_controller is None
            or self._workspace_controller is None
            or not task.project_id
        ):
            return
        try:
            project = self._project_controller.get_project(task.project_id)
        except ValueError:
            return
        workspace_message_id = project.workspace_message_id
        if not workspace_message_id:
            self._bootstrap_workspace_card(project, task)
            return
        if workspace_message_id == task.notification_message_id:
            return
        signature = (
            task.id,
            task.status.value,
            task.effective_workdir,
            task.agent_backend,
            task.effective_model,
        )
        if self._workspace_sync_signatures.get(project.id) == signature:
            return

        from poco.interaction.card_handlers import build_workspace_overview_result

        context = self._workspace_controller.get_context(project)
        instruction = build_render_instruction(
            build_workspace_overview_result(
                project,
                context=context,
                active_session=(
                    self._session_controller.get_active_session(project.id)
                    if self._session_controller is not None
                    else None
                ),
                latest_task=task,
                task_controller=self._task_controller,
                message=f"Workspace synced for {project.name}",
            ),
            surface=Surface.GROUP,
        )
        card = self._renderer.render(instruction)
        if self._debug_recorder is not None:
            self._debug_recorder.record_outbound_attempt(
                source="workspace_notifier_update",
                receive_id=project.group_chat_id or "",
                receive_id_type="chat_id",
                text=f"[card-update] workspace_overview:{task.status.value}",
                task_id=task.id,
            )
        try:
            self._message_client.update_interactive(
                message_id=workspace_message_id,
                card=card,
            )
            self._workspace_sync_signatures[project.id] = signature
        except Exception as exc:
            if self._debug_recorder is not None:
                self._debug_recorder.record_error(
                    stage="workspace_notifier_update",
                    message=str(exc),
                    context={
                        "task_id": task.id,
                        "workspace_message_id": workspace_message_id,
                        "project_id": project.id,
                    },
                )
            self._bootstrap_workspace_card(project, task)

    def _bootstrap_workspace_card(self, project, task: Task) -> None:
        if not project.group_chat_id or self._project_controller is None:
            return
        from poco.interaction.card_handlers import build_workspace_overview_result

        context = (
            self._workspace_controller.get_context(project)
            if self._workspace_controller is not None
            else None
        )
        instruction = build_render_instruction(
            build_workspace_overview_result(
                project,
                context=context,
                active_session=(
                    self._session_controller.get_active_session(project.id)
                    if self._session_controller is not None
                    else None
                ),
                latest_task=task,
                task_controller=self._task_controller,
                message=f"Workspace restored for {project.name}",
            ),
            surface=Surface.GROUP,
        )
        card = self._renderer.render(instruction)
        result = self._message_client.send_interactive(
            receive_id=project.group_chat_id,
            receive_id_type="chat_id",
            card=card,
        )
        if result.message_id:
            self._project_controller.bind_workspace_message(project.id, result.message_id)
        if self._debug_recorder is not None:
            self._debug_recorder.record_outbound_attempt(
                source="workspace_notifier_bootstrap",
                receive_id=project.group_chat_id,
                receive_id_type="chat_id",
                text=f"[card] Workspace: {project.name}",
                task_id=task.id,
            )


def _receive_id_type_from_surface(surface: Surface | None) -> str | None:
    if surface == Surface.GROUP:
        return "chat_id"
    if surface == Surface.DM:
        return "open_id"
    return None
