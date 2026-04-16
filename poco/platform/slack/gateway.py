from __future__ import annotations

from typing import Any

from poco.interaction.card_dispatcher import build_render_instruction
from poco.interaction.card_handlers import (
    _reconcile_project_tasks,
    build_task_status_result,
    build_workspace_overview_result,
)
from poco.interaction.card_models import Surface
from poco.interaction.service import InteractionService
from poco.platform.slack.card_gateway import SlackCardActionGateway
from poco.platform.slack.cards import SlackCardRenderer
from poco.platform.slack.client import SlackMessageClient
from poco.platform.slack.debug import SlackDebugRecorder
from poco.project.controller import ProjectController
from poco.project.models import Project
from poco.task.controller import TaskController
from poco.task.dispatcher import AsyncTaskDispatcher
from poco.workspace.controller import WorkspaceContextController


class SlackGateway:
    """Inbound Events API gateway for Slack, analogous to :class:`FeishuGateway`.

    Responsibilities:
      * URL verification (Slack sends ``type == "url_verification"`` with a
        ``challenge`` field on registration).
      * Filter out bot-originated messages to avoid feedback loops.
      * Resolve the surface (DM vs channel) and any project bound to the
        channel so the shared :class:`InteractionService` can apply the
        project's backend configuration.
      * Deliver replies via :class:`SlackMessageClient`, preferring a
        task-status card when a task id is produced and falling back to a
        plain text message otherwise.
      * Bootstrap a workspace card in any Slack channel that maps to a
        project but has no workspace message yet (parallels the Feishu path
        but adds ``channel`` bookkeeping now that messages are addressed by
        ``(channel, ts)``).
    """

    def __init__(
        self,
        interaction_service: InteractionService,
        *,
        message_client: SlackMessageClient | None = None,
        dispatcher: AsyncTaskDispatcher | None = None,
        card_gateway: SlackCardActionGateway | None = None,
        task_controller: TaskController | None = None,
        card_renderer: SlackCardRenderer | None = None,
        debug_recorder: SlackDebugRecorder | None = None,
        project_controller: ProjectController | None = None,
        workspace_controller: WorkspaceContextController | None = None,
    ) -> None:
        self._interaction_service = interaction_service
        self._message_client = message_client
        self._dispatcher = dispatcher
        self._card_gateway = card_gateway
        self._task_controller = task_controller
        self._card_renderer = card_renderer or SlackCardRenderer()
        self._debug_recorder = debug_recorder
        self._project_controller = project_controller
        self._workspace_controller = workspace_controller

    # Events API -------------------------------------------------------------

    def handle_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge", "")}

        event = payload.get("event") or {}
        event_type = event.get("type")
        if event_type not in {"message", "app_mention"}:
            return {"ok": True, "ignored": True, "reason": f"event_type:{event_type}"}
        if self._is_bot_message(event):
            return {"ok": True, "ignored": True, "reason": "bot_message"}
        if event.get("subtype") in {"message_changed", "message_deleted", "bot_message"}:
            return {"ok": True, "ignored": True, "reason": f"subtype:{event.get('subtype')}"}

        user_id = str(event.get("user") or "anonymous")
        channel = str(event.get("channel") or "")
        text = self._extract_text(event)
        surface_str = self._surface_from_channel_type(event.get("channel_type"))
        project = self._resolve_group_project(event)
        project_id = project.id if project is not None else None

        self._record_inbound(
            user_id=user_id,
            text=text,
            channel=channel,
            surface=surface_str,
            payload=payload,
        )

        # DM project-list surface: mirror Feishu's behavior — any inbound DM
        # renders the project list card via the card gateway rather than
        # running through interaction parsing.
        if (
            surface_str == "dm"
            and self._message_client is not None
            and self._card_gateway is not None
        ):
            rendered = self._card_gateway.render_dm_project_list(actor_id=user_id)
            self._record_outbound_attempt(
                source="gateway_dm_card",
                channel=channel,
                text="[card] PoCo Projects",
                task_id=None,
            )
            try:
                self._message_client.send_interactive(
                    receive_id=channel,
                    receive_id_type="channel",
                    card=rendered["card"],
                )
            except Exception as exc:
                self._record_error(
                    stage="gateway_dm_card",
                    message=str(exc),
                    context={"channel": channel},
                )
                raise
            return {
                "ok": True,
                "delivered": True,
                "reply_preview": "[card] PoCo Projects",
                "task_id": None,
            }

        _reconcile_project_tasks(
            project_id,
            task_controller=self._task_controller,
            dispatcher=self._dispatcher,
        )

        response = self._interaction_service.handle_text(
            user_id=user_id,
            text=text,
            source="slack",
            message_surface=surface_str,
            project_id=project_id,
            agent_backend=project.backend if project is not None else None,
            effective_backend_config=dict(project.backend_config)
            if project is not None
            else None,
            effective_model=project.model if project is not None else None,
            effective_sandbox=project.sandbox if project is not None else None,
            effective_workdir=self._resolve_effective_workdir(project),
            reply_receive_id=channel,
            reply_surface=Surface.GROUP if surface_str == "group" else Surface.DM,
        )

        if project is not None:
            self._ensure_workspace_card(project)

        start_dispatched = False
        if (
            self._dispatcher is not None
            and response.task_id
            and response.dispatch_action == "start"
        ):
            self._dispatcher.dispatch_start(response.task_id)
            start_dispatched = True

        delivered = False
        reply_preview = response.text
        if self._message_client is not None:
            try:
                if start_dispatched:
                    delivered = True
                    reply_preview = "[async] task_status:running"
                elif (
                    response.task_id
                    and self._task_controller is not None
                    and channel
                ):
                    task = self._task_controller.get_task(response.task_id)
                    surface = (
                        Surface.GROUP if surface_str == "group" else Surface.DM
                    )
                    instruction = build_render_instruction(
                        build_task_status_result(
                            task,
                            task_controller=self._task_controller,
                            message=response.text,
                        ),
                        surface=surface,
                    )
                    card = self._card_renderer.render(instruction)
                    self._record_outbound_attempt(
                        source="gateway_task_card",
                        channel=channel,
                        text=f"[card] task_status:{task.status.value}",
                        task_id=response.task_id,
                    )
                    result = self._message_client.send_interactive(
                        receive_id=channel,
                        receive_id_type="channel",
                        card=card,
                    )
                    if result.message_id:
                        self._task_controller.bind_notification_message(
                            task.id,
                            result.message_id,
                            channel=result.channel or channel,
                        )
                    reply_preview = f"[card] task_status:{task.status.value}"
                    delivered = True
                elif channel:
                    self._record_outbound_attempt(
                        source="gateway_reply",
                        channel=channel,
                        text=response.text,
                        task_id=response.task_id,
                    )
                    self._message_client.send_text(
                        receive_id=channel,
                        receive_id_type="channel",
                        text=response.text,
                    )
                    delivered = True
            except Exception as exc:
                self._record_error(
                    stage="gateway_reply",
                    message=str(exc),
                    context={"channel": channel, "task_id": response.task_id},
                )
                raise

        if self._dispatcher is not None and response.task_id:
            if response.dispatch_action == "start" and not start_dispatched:
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

    # Slash commands ---------------------------------------------------------

    def handle_slash_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Respond to ``/poco`` by posting the DM project list card.

        Slack slash commands expect an immediate JSON response. Returning
        ``{"response_type": "ephemeral", ...}`` keeps the reply visible only
        to the invoker. For ``/poco`` we attach the same project-list Block
        Kit card the DM surface renders.
        """

        command = str(payload.get("command") or "").strip()
        user_id = str(payload.get("user_id") or "anonymous")
        if command not in {"/poco", "/poco-dev"}:
            return {
                "response_type": "ephemeral",
                "text": f"Unknown command `{command}`.",
            }
        if self._card_gateway is None:
            return {
                "response_type": "ephemeral",
                "text": "PoCo is not yet configured to respond here.",
            }
        rendered = self._card_gateway.render_dm_project_list(actor_id=user_id)
        card = rendered["card"]
        response: dict[str, Any] = {
            "response_type": "ephemeral",
            "text": card.get("text") or "PoCo Projects",
            "blocks": card.get("blocks") or [],
        }
        return response

    # Helpers ----------------------------------------------------------------

    def _is_bot_message(self, event: dict[str, Any]) -> bool:
        if event.get("bot_id"):
            return True
        if event.get("subtype") == "bot_message":
            return True
        return False

    def _extract_text(self, event: dict[str, Any]) -> str:
        text = event.get("text")
        if isinstance(text, str):
            return text.strip()
        return ""

    def _surface_from_channel_type(self, channel_type: Any) -> str:
        normalized = str(channel_type).lower() if channel_type is not None else ""
        if normalized == "im":
            return "dm"
        if normalized in {"channel", "group", "mpim"}:
            return "group"
        return "unknown"

    def _resolve_group_project(self, event: dict[str, Any]) -> Project | None:
        if self._project_controller is None:
            return None
        channel = event.get("channel")
        channel_type = event.get("channel_type")
        if not channel or str(channel_type).lower() == "im":
            return None
        return self._project_controller.get_project_by_group_chat_id(str(channel))

    def _resolve_effective_workdir(self, project: Project | None) -> str | None:
        if project is None:
            return None
        if self._workspace_controller is None:
            return project.workdir
        context = self._workspace_controller.get_context(project)
        return context.active_workdir

    def _ensure_workspace_card(self, project: Project) -> None:
        if self._message_client is None or self._project_controller is None:
            return
        if not project.group_chat_id or project.workspace_message_id:
            return

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
                task_controller=self._task_controller,
            ),
            surface=Surface.GROUP,
        )
        card = self._card_renderer.render(instruction)
        result = self._message_client.send_interactive(
            receive_id=project.group_chat_id,
            receive_id_type="channel",
            card=card,
        )
        if result.message_id:
            self._project_controller.bind_workspace_message(
                project.id,
                result.message_id,
                channel=result.channel or project.group_chat_id,
            )
        self._record_outbound_attempt(
            source="gateway_workspace_bootstrap",
            channel=project.group_chat_id,
            text=f"[card] Workspace: {project.name}",
            task_id=project.id,
        )

    def _record_inbound(
        self,
        *,
        user_id: str,
        text: str,
        channel: str,
        surface: str,
        payload: dict[str, Any],
    ) -> None:
        if self._debug_recorder is None:
            return
        self._debug_recorder.record_inbound(
            user_id=user_id,
            text=text,
            channel=channel,
            surface=surface,
            payload=payload,
        )

    def _record_outbound_attempt(
        self,
        *,
        source: str,
        channel: str,
        text: str,
        task_id: str | None,
    ) -> None:
        if self._debug_recorder is None:
            return
        self._debug_recorder.record_outbound_attempt(
            source=source,
            channel=channel,
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
