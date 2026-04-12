from __future__ import annotations

from poco.interaction.card_dispatcher import build_render_instruction
from poco.interaction.card_handlers import build_workspace_overview_result
from poco.interaction.card_models import Surface
from poco.platform.feishu.client import (
    FeishuApiError,
    FeishuChatDeleteForbiddenError,
    FeishuChatNotFoundError,
    FeishuMessageClient,
)
from poco.platform.feishu.cards import FeishuCardRenderer
from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.project.bootstrap import (
    ProjectBootstrapError,
    ProjectBootstrapResult,
)
from poco.project.controller import ProjectController
from poco.project.models import Project


class FeishuProjectBootstrapper:
    def __init__(
        self,
        message_client: FeishuMessageClient,
        renderer: FeishuCardRenderer,
        *,
        project_controller: ProjectController | None = None,
        debug_recorder: FeishuDebugRecorder | None = None,
    ) -> None:
        self._message_client = message_client
        self._renderer = renderer
        self._project_controller = project_controller
        self._debug_recorder = debug_recorder

    def bootstrap_project(
        self,
        *,
        project: Project,
        actor_id: str,
    ) -> ProjectBootstrapResult:
        chat_name = _group_name_for_project(project.name)
        try:
            created_chat = self._message_client.create_group_chat(
                name=chat_name,
                owner_open_id=actor_id,
            )
        except FeishuApiError as exc:
            if self._debug_recorder is not None:
                self._debug_recorder.record_error(
                    stage="project_group_bootstrap",
                    message=str(exc),
                    context={
                        "project_id": project.id,
                        "project_name": project.name,
                        "actor_id": actor_id,
                    },
                )
            raise ProjectBootstrapError(str(exc)) from exc

        if self._debug_recorder is not None:
            self._debug_recorder.record_outbound_attempt(
                source="project_group_bootstrap",
                receive_id=actor_id,
                receive_id_type="open_id",
                text=f"{chat_name} -> {created_chat.chat_id}",
                task_id=project.id,
            )
        return ProjectBootstrapResult(group_chat_id=created_chat.chat_id)

    def notify_project_workspace(
        self,
        *,
        project: Project,
        actor_id: str,
    ) -> None:
        if not project.group_chat_id:
            return

        result = build_workspace_overview_result(project)
        instruction = build_render_instruction(result, surface=Surface.GROUP)
        card = self._renderer.render(instruction)
        try:
            result = self._message_client.send_interactive(
                receive_id=project.group_chat_id,
                receive_id_type="chat_id",
                card=card,
            )
        except FeishuApiError as exc:
            if self._debug_recorder is not None:
                self._debug_recorder.record_error(
                    stage="project_workspace_bootstrap",
                    message=str(exc),
                    context={
                        "project_id": project.id,
                        "project_name": project.name,
                        "group_chat_id": project.group_chat_id,
                        "actor_id": actor_id,
                    },
                )
            return

        if self._project_controller is not None and result.message_id:
            self._project_controller.bind_workspace_message(project.id, result.message_id)

        if self._debug_recorder is not None:
            self._debug_recorder.record_outbound_attempt(
                source="project_workspace_bootstrap",
                receive_id=project.group_chat_id,
                receive_id_type="chat_id",
                text=f"[card] Workspace: {project.name}",
                task_id=project.id,
            )

    def destroy_project_workspace(
        self,
        *,
        project: Project,
        actor_id: str,
    ) -> None:
        if not project.group_chat_id:
            raise ProjectBootstrapError("Project group not found.")
        try:
            self._message_client.delete_group_chat(chat_id=project.group_chat_id)
        except FeishuChatNotFoundError as exc:
            if self._debug_recorder is not None:
                self._debug_recorder.record_error(
                    stage="project_group_destroy",
                    message=str(exc),
                    context={
                        "project_id": project.id,
                        "project_name": project.name,
                        "group_chat_id": project.group_chat_id,
                        "actor_id": actor_id,
                    },
                )
            raise ProjectBootstrapError("Project group not found.") from exc
        except FeishuChatDeleteForbiddenError as exc:
            if self._debug_recorder is not None:
                self._debug_recorder.record_error(
                    stage="project_group_destroy",
                    message=str(exc),
                    context={
                        "project_id": project.id,
                        "project_name": project.name,
                        "group_chat_id": project.group_chat_id,
                        "actor_id": actor_id,
                    },
                )
            raise ProjectBootstrapError(
                "Project group could not be dismissed by the app. Delete the group manually in Feishu, or keep the group and only delete the project record."
            ) from exc
        except FeishuApiError as exc:
            if self._debug_recorder is not None:
                self._debug_recorder.record_error(
                    stage="project_group_destroy",
                    message=str(exc),
                    context={
                        "project_id": project.id,
                        "project_name": project.name,
                        "group_chat_id": project.group_chat_id,
                        "actor_id": actor_id,
                    },
                )
            raise ProjectBootstrapError(str(exc)) from exc


def _group_name_for_project(project_name: str) -> str:
    return f"PoCo | {project_name}"
