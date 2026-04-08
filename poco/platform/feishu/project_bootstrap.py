from __future__ import annotations

from poco.platform.feishu.client import FeishuApiError, FeishuMessageClient
from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.project.bootstrap import (
    ProjectBootstrapError,
    ProjectBootstrapResult,
)
from poco.project.models import Project


class FeishuProjectBootstrapper:
    def __init__(
        self,
        message_client: FeishuMessageClient,
        *,
        debug_recorder: FeishuDebugRecorder | None = None,
    ) -> None:
        self._message_client = message_client
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


def _group_name_for_project(project_name: str) -> str:
    return f"PoCo | {project_name}"
