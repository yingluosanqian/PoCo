from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from poco.interaction.card_models import Surface
from poco.session.controller import SessionController
from poco.task.controller import TaskController, TaskNotFoundError, TaskStateError
from poco.task.rendering import render_task_text


MessageSurface = Literal["dm", "group", "unknown"]


@dataclass(frozen=True, slots=True)
class InteractionResponse:
    text: str
    task_id: str | None = None
    dispatch_action: str | None = None


class InteractionService:
    def __init__(
        self,
        controller: TaskController,
        session_controller: SessionController | None = None,
    ) -> None:
        self._controller = controller
        self._session_controller = session_controller

    def handle_text(
        self,
        user_id: str,
        text: str,
        source: str,
        *,
        message_surface: MessageSurface = "unknown",
        project_id: str | None = None,
        agent_backend: str | None = None,
        effective_backend_config: dict[str, object] | None = None,
        effective_model: str | None = None,
        effective_sandbox: str | None = None,
        effective_workdir: str | None = None,
        reply_receive_id: str | None = None,
        reply_surface: Surface | None = None,
    ) -> InteractionResponse:
        command = text.strip()
        if not command:
            return InteractionResponse(
                text=self._help_text(
                    message_surface=message_surface,
                    project_id=project_id,
                )
            )

        if message_surface == "group" and project_id:
            return self._create_task_response(
                requester_id=user_id,
                prompt=command,
                source=source,
                project_id=project_id,
                agent_backend=agent_backend,
                effective_backend_config=effective_backend_config,
                effective_model=effective_model,
                effective_sandbox=effective_sandbox,
                effective_workdir=effective_workdir,
                reply_receive_id=reply_receive_id,
                reply_surface=reply_surface,
            )

        if command == "/help":
            return InteractionResponse(
                text=self._help_text(
                    message_surface=message_surface,
                    project_id=project_id,
                )
            )

        if command.startswith("/run "):
            prompt = command.removeprefix("/run ").strip()
            if not prompt:
                return InteractionResponse(text="Usage: /run <prompt>")
            return self._create_task_response(
                requester_id=user_id,
                prompt=prompt,
                source=source,
                project_id=project_id,
                agent_backend=agent_backend,
                effective_backend_config=effective_backend_config,
                effective_model=effective_model,
                effective_sandbox=effective_sandbox,
                effective_workdir=effective_workdir,
                reply_receive_id=reply_receive_id,
                reply_surface=reply_surface,
            )

        if command.startswith("/status "):
            task_id = command.removeprefix("/status ").strip()
            return self._task_lookup_response(task_id)

        if command.startswith("/approve "):
            task_id = command.removeprefix("/approve ").strip()
            return self._resolve_confirmation(task_id, approved=True)

        if command.startswith("/reject "):
            task_id = command.removeprefix("/reject ").strip()
            return self._resolve_confirmation(task_id, approved=False)

        if command.startswith("/"):
            return InteractionResponse(
                text=self._help_text(
                    message_surface=message_surface,
                    project_id=project_id,
                )
            )

        return InteractionResponse(
            text=self._help_text(
                message_surface=message_surface,
                project_id=project_id,
            )
        )

    def _create_task_response(
        self,
        *,
        requester_id: str,
        prompt: str,
        source: str,
        project_id: str | None,
        agent_backend: str | None,
        effective_backend_config: dict[str, object] | None,
        effective_model: str | None,
        effective_sandbox: str | None,
        effective_workdir: str | None,
        reply_receive_id: str | None,
        reply_surface: Surface | None,
    ) -> InteractionResponse:
        task = self._controller.create_task(
            requester_id=requester_id,
            prompt=prompt,
            source=source,
            agent_backend=agent_backend,
            project_id=project_id,
            session_id=self._resolve_session_id(project_id=project_id, requester_id=requester_id),
            effective_backend_config=effective_backend_config,
            effective_model=effective_model,
            effective_sandbox=effective_sandbox,
            effective_workdir=effective_workdir,
            reply_receive_id=reply_receive_id,
            reply_surface=reply_surface,
        )
        dispatch_action = "start"
        headline = "Task created."
        if project_id and self._controller.has_active_task_for_project(
            project_id,
            exclude_task_id=task.id,
        ):
            task = self._controller.queue_task(task.id)
            dispatch_action = None
            headline = "Task queued."
        return InteractionResponse(
            text=render_task_text(task, headline=headline),
            task_id=task.id,
            dispatch_action=dispatch_action,
        )

    def _task_lookup_response(self, task_id: str) -> InteractionResponse:
        try:
            task = self._controller.get_task(task_id)
        except TaskNotFoundError as exc:
            return InteractionResponse(text=str(exc))
        return InteractionResponse(text=render_task_text(task, headline="Task status."))

    def _resolve_confirmation(self, task_id: str, approved: bool) -> InteractionResponse:
        try:
            task = self._controller.resolve_confirmation(task_id, approved=approved)
        except (TaskNotFoundError, TaskStateError) as exc:
            return InteractionResponse(text=str(exc))

        headline = "Task approved." if approved else "Task rejected."
        return InteractionResponse(
            text=render_task_text(task, headline=headline),
            task_id=task.id,
            dispatch_action="resume" if approved else "advance_queue",
        )

    def _help_text(
        self,
        *,
        message_surface: MessageSurface,
        project_id: str | None,
    ) -> str:
        lines: list[str] = []
        if message_surface == "group" and project_id:
            lines.append("Send any text message, including slash-prefixed text, to create a task in this project.")
        elif message_surface == "group":
            lines.append("This group is not bound to a project yet.")
        elif message_surface == "dm":
            lines.append("DM is the PoCo control plane. Use cards to manage projects and workspaces.")
        else:
            lines.append("PoCo help.")

        lines.extend(
            [
                "Commands:",
                "/run <prompt>",
                "/status <task_id>",
                "/approve <task_id>",
                "/reject <task_id>",
                "/help",
            ]
        )
        return "\n".join(lines)

    def _resolve_session_id(
        self,
        *,
        project_id: str | None,
        requester_id: str,
    ) -> str | None:
        if project_id is None or self._session_controller is None:
            return None
        session = self._session_controller.get_or_create_active_session(
            project_id=project_id,
            created_by=requester_id,
        )
        return session.id
