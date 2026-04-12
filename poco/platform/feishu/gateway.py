from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from poco.interaction.card_dispatcher import build_render_instruction
from poco.interaction.card_handlers import build_task_status_result
from poco.interaction.card_models import Surface
from poco.interaction.service import InteractionService
from poco.platform.feishu.client import FeishuMessageClient
from poco.platform.feishu.card_gateway import FeishuCardActionGateway
from poco.platform.feishu.cards import FeishuCardRenderer
from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.platform.feishu.verification import FeishuRequestVerifier
from poco.project.models import Project
from poco.project.controller import ProjectController
from poco.task.controller import TaskController
from poco.task.dispatcher import AsyncTaskDispatcher
from poco.workspace.controller import WorkspaceContextController


class FeishuGateway:
    def __init__(
        self,
        interaction_service: InteractionService,
        *,
        request_verifier: FeishuRequestVerifier | None = None,
        message_client: FeishuMessageClient | None = None,
        dispatcher: AsyncTaskDispatcher | None = None,
        card_gateway: FeishuCardActionGateway | None = None,
        task_controller: TaskController | None = None,
        card_renderer: FeishuCardRenderer | None = None,
        debug_recorder: FeishuDebugRecorder | None = None,
        project_controller: ProjectController | None = None,
        workspace_controller: WorkspaceContextController | None = None,
    ) -> None:
        self._interaction_service = interaction_service
        self._request_verifier = request_verifier
        self._message_client = message_client
        self._dispatcher = dispatcher
        self._card_gateway = card_gateway
        self._task_controller = task_controller
        self._card_renderer = card_renderer or FeishuCardRenderer()
        self._debug_recorder = debug_recorder
        self._project_controller = project_controller
        self._workspace_controller = workspace_controller

    def handle_event(
        self,
        payload: dict[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
        raw_body: bytes | None = None,
    ) -> dict[str, Any]:
        request_headers = headers or {}
        request_body = raw_body or json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if self._request_verifier is not None:
            self._request_verifier.verify(
                payload=payload,
                headers=request_headers,
                raw_body=request_body,
            )

        if "challenge" in payload:
            return {"challenge": payload["challenge"]}

        event = payload.get("event", payload)
        if self._should_ignore_sender(event):
            return {"ok": True, "ignored": True, "reason": "non_user_sender"}
        if not event.get("message"):
            return {"ok": True, "ignored": True}

        user_id = self._extract_user_id(event)
        text = self._extract_text(event)
        target = self._resolve_reply_target(event, fallback_user_id=user_id)
        self._record_inbound(
            user_id=user_id,
            text=text,
            target=target,
            payload=payload,
        )

        if (
            target["receive_id_type"] == "open_id"
            and self._message_client is not None
            and self._card_gateway is not None
        ):
            rendered = self._card_gateway.render_dm_project_list(actor_id=user_id)
            self._record_outbound_attempt(
                source="gateway_dm_card",
                receive_id=target["receive_id"],
                receive_id_type=target["receive_id_type"],
                text="[card] PoCo Projects",
                task_id=None,
            )
            try:
                self._message_client.send_interactive(
                    receive_id=target["receive_id"],
                    receive_id_type=target["receive_id_type"],
                    card=rendered["card"],
                )
            except Exception as exc:
                self._record_error(
                    stage="gateway_dm_card",
                    message=str(exc),
                    context={
                        "receive_id": target["receive_id"],
                        "receive_id_type": target["receive_id_type"],
                    },
                )
                raise

            return {
                "ok": True,
                "delivered": True,
                "reply_preview": "[card] PoCo Projects",
                "task_id": None,
            }

        response = self._interaction_service.handle_text(
            user_id=user_id,
            text=text,
            source="feishu",
            message_surface=self._message_surface(event),
            project_id=self._resolve_project_id(event),
            effective_backend_config=self._resolve_effective_backend_config(event),
            effective_model=self._resolve_effective_model(event),
            effective_sandbox=self._resolve_effective_sandbox(event),
            effective_workdir=self._resolve_effective_workdir(event),
            reply_receive_id=target["receive_id"],
            reply_receive_id_type=target["receive_id_type"],
        )

        group_project = self._resolve_group_project(event)
        if group_project is not None:
            self._ensure_workspace_card(group_project)

        delivered = False
        reply_preview = response.text
        if self._message_client is not None:
            try:
                if (
                    response.task_id
                    and self._task_controller is not None
                    and target["receive_id_type"] in {"chat_id", "open_id"}
                ):
                    task = self._task_controller.get_task(response.task_id)
                    surface = (
                        Surface.GROUP
                        if target["receive_id_type"] == "chat_id"
                        else Surface.DM
                    )
                    instruction = build_render_instruction(
                        build_task_status_result(task, message=response.text),
                        surface=surface,
                    )
                    card = self._card_renderer.render(instruction)
                    self._record_outbound_attempt(
                        source="gateway_task_card",
                        receive_id=target["receive_id"],
                        receive_id_type=target["receive_id_type"],
                        text=f"[card] task_status:{task.status.value}",
                        task_id=response.task_id,
                    )
                    result = self._message_client.send_interactive(
                        receive_id=target["receive_id"],
                        receive_id_type=target["receive_id_type"],
                        card=card,
                    )
                    task.set_notification_message_id(result.message_id)
                    task = self._task_controller.bind_notification_message(
                        task.id,
                        result.message_id,
                    )
                    reply_preview = f"[card] task_status:{task.status.value}"
                else:
                    self._record_outbound_attempt(
                        source="gateway_reply",
                        receive_id=target["receive_id"],
                        receive_id_type=target["receive_id_type"],
                        text=response.text,
                        task_id=response.task_id,
                    )
                    self._message_client.send_text(
                        receive_id=target["receive_id"],
                        receive_id_type=target["receive_id_type"],
                        text=response.text,
                    )
                delivered = True
            except Exception as exc:
                self._record_error(
                    stage="gateway_reply",
                    message=str(exc),
                    context={
                        "receive_id": target["receive_id"],
                        "receive_id_type": target["receive_id_type"],
                        "task_id": response.task_id,
                    },
                )
                raise

        if self._dispatcher is not None and response.task_id:
            if response.dispatch_action == "start":
                self._dispatcher.dispatch_start(response.task_id)
            elif response.dispatch_action == "resume":
                self._dispatcher.dispatch_resume(response.task_id)
            elif response.dispatch_action == "advance_queue" and self._task_controller is not None:
                task = self._task_controller.get_task(response.task_id)
                if task.project_id:
                    self._dispatcher.dispatch_next_queued(task.project_id)

        return {
            "ok": True,
            "delivered": delivered,
            "reply_preview": reply_preview,
            "task_id": response.task_id,
        }

    def _should_ignore_sender(self, event: dict[str, Any]) -> bool:
        sender = event.get("sender", {})
        sender_type = sender.get("sender_type")
        if sender_type is None:
            return False
        return str(sender_type).lower() in {"app", "bot"}

    def _extract_user_id(self, event: dict[str, Any]) -> str:
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {})
        return (
            sender_id.get("open_id")
            or sender_id.get("user_id")
            or sender.get("open_id")
            or "anonymous"
        )

    def _extract_text(self, event: dict[str, Any]) -> str:
        message = event.get("message", {})
        content = message.get("content")

        if isinstance(content, str):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                return content
            if isinstance(parsed, dict):
                return str(parsed.get("text", "")).strip()
            return ""

        if isinstance(content, dict):
            return str(content.get("text", "")).strip()

        return str(event.get("text", "")).strip()

    def _message_surface(self, event: dict[str, Any]) -> str:
        message = event.get("message", {})
        chat_type = (
            message.get("chat_type")
            or event.get("chat_type")
            or event.get("message_type")
        )
        normalized = str(chat_type).lower() if chat_type is not None else ""
        if normalized in {"group", "chat", "group_chat"}:
            return "group"
        if normalized in {"p2p", "dm"}:
            return "dm"
        return "unknown"

    def _resolve_reply_target(
        self,
        event: dict[str, Any],
        *,
        fallback_user_id: str,
    ) -> dict[str, str]:
        message = event.get("message", {})
        chat_id = message.get("chat_id")
        chat_type = (
            message.get("chat_type")
            or event.get("chat_type")
            or event.get("message_type")
        )
        normalized_chat_type = str(chat_type).lower() if chat_type is not None else ""
        if chat_id and normalized_chat_type in {"group", "chat", "group_chat"}:
            return {
                "receive_id": str(chat_id),
                "receive_id_type": "chat_id",
            }

        return {
            "receive_id": fallback_user_id,
            "receive_id_type": "open_id",
        }

    def _record_inbound(
        self,
        *,
        user_id: str,
        text: str,
        target: dict[str, str],
        payload: dict[str, Any],
    ) -> None:
        if self._debug_recorder is None:
            return
        self._debug_recorder.record_inbound(
            user_id=user_id,
            text=text,
            reply_receive_id=target["receive_id"],
            reply_receive_id_type=target["receive_id_type"],
            payload=payload,
        )

    def _record_outbound_attempt(
        self,
        *,
        source: str,
        receive_id: str,
        receive_id_type: str,
        text: str,
        task_id: str | None,
    ) -> None:
        if self._debug_recorder is None:
            return
        self._debug_recorder.record_outbound_attempt(
            source=source,
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            text=text,
            task_id=task_id,
        )

    def _record_error(
        self,
        *,
        stage: str,
        message: str,
        context: dict[str, Any],
    ) -> None:
        if self._debug_recorder is None:
            return
        self._debug_recorder.record_error(
            stage=stage,
            message=message,
            context=context,
        )

    def _resolve_project_id(self, event: dict[str, Any]) -> str | None:
        project = self._resolve_group_project(event)
        if project is None:
            return None
        return project.id

    def _resolve_effective_workdir(self, event: dict[str, Any]) -> str | None:
        project = self._resolve_group_project(event)
        if project is None:
            return None
        if self._workspace_controller is None:
            return project.workdir
        context = self._workspace_controller.get_context(project)
        return context.active_workdir

    def _resolve_effective_model(self, event: dict[str, Any]) -> str | None:
        project = self._resolve_group_project(event)
        if project is None:
            return None
        return project.model

    def _resolve_effective_backend_config(self, event: dict[str, Any]) -> dict[str, object] | None:
        project = self._resolve_group_project(event)
        if project is None:
            return None
        return dict(project.backend_config)

    def _resolve_effective_sandbox(self, event: dict[str, Any]) -> str | None:
        project = self._resolve_group_project(event)
        if project is None:
            return None
        return project.sandbox

    def _resolve_group_project(self, event: dict[str, Any]) -> Project | None:
        if self._project_controller is None:
            return None
        message = event.get("message", {})
        chat_id = message.get("chat_id")
        chat_type = message.get("chat_type") or event.get("chat_type")
        if not chat_id or str(chat_type).lower() not in {"group", "chat", "group_chat"}:
            return None
        return self._project_controller.get_project_by_group_chat_id(str(chat_id))

    def _ensure_workspace_card(self, project: Project) -> None:
        if self._message_client is None or self._project_controller is None:
            return
        if not project.group_chat_id or project.workspace_message_id:
            return

        from poco.interaction.card_handlers import build_workspace_overview_result

        context = (
            self._workspace_controller.get_context(project)
            if self._workspace_controller is not None
            else None
        )
        latest_task = None
        if self._task_controller is not None:
            tasks = self._task_controller.list_tasks_for_project(project.id)
            if tasks:
                latest_task = max(tasks, key=lambda task: task.updated_at)
        instruction = build_render_instruction(
            build_workspace_overview_result(
                project,
                context=context,
                latest_task=latest_task,
            ),
            surface=Surface.GROUP,
        )
        card = self._card_renderer.render(instruction)
        result = self._message_client.send_interactive(
            receive_id=project.group_chat_id,
            receive_id_type="chat_id",
            card=card,
        )
        if result.message_id:
            self._project_controller.bind_workspace_message(project.id, result.message_id)
        self._record_outbound_attempt(
            source="gateway_workspace_bootstrap",
            receive_id=project.group_chat_id,
            receive_id_type="chat_id",
            text=f"[card] Workspace: {project.name}",
            task_id=project.id,
        )
