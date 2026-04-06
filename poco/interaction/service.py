from __future__ import annotations

from dataclasses import dataclass

from poco.task.controller import TaskController, TaskNotFoundError, TaskStateError
from poco.task.models import Task, TaskStatus


@dataclass(frozen=True, slots=True)
class InteractionResponse:
    text: str
    task_id: str | None = None


class InteractionService:
    def __init__(self, controller: TaskController) -> None:
        self._controller = controller

    def handle_text(self, user_id: str, text: str, source: str) -> InteractionResponse:
        command = text.strip()
        if not command:
            return InteractionResponse(text=self._help_text())

        if command == "/help":
            return InteractionResponse(text=self._help_text())

        if command.startswith("/run "):
            prompt = command.removeprefix("/run ").strip()
            if not prompt:
                return InteractionResponse(text="Usage: /run <prompt>")
            task = self._controller.create_task(
                requester_id=user_id,
                prompt=prompt,
                source=source,
            )
            return InteractionResponse(
                text=self._format_task(task, headline="Task created."),
                task_id=task.id,
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

        return InteractionResponse(text=self._help_text())

    def _task_lookup_response(self, task_id: str) -> InteractionResponse:
        try:
            task = self._controller.get_task(task_id)
        except TaskNotFoundError as exc:
            return InteractionResponse(text=str(exc))
        return InteractionResponse(text=self._format_task(task, headline="Task status."))

    def _resolve_confirmation(self, task_id: str, approved: bool) -> InteractionResponse:
        try:
            task = self._controller.resolve_confirmation(task_id, approved=approved)
        except (TaskNotFoundError, TaskStateError) as exc:
            return InteractionResponse(text=str(exc))

        headline = "Task approved." if approved else "Task rejected."
        return InteractionResponse(text=self._format_task(task, headline=headline))

    def _format_task(self, task: Task, headline: str) -> str:
        lines = [
            headline,
            f"task_id={task.id}",
            f"status={task.status.value}",
            f"source={task.source}",
            f"prompt={task.prompt}",
        ]

        if task.awaiting_confirmation_reason:
            lines.append(f"awaiting_confirmation={task.awaiting_confirmation_reason}")

        if task.result_summary:
            lines.append(f"result={task.result_summary}")

        if task.events:
            lines.append(f"latest_event={task.events[-1].message}")

        if task.status == TaskStatus.WAITING_FOR_CONFIRMATION:
            lines.append(f"next=/approve {task.id} or /reject {task.id}")

        return "\n".join(lines)

    def _help_text(self) -> str:
        return "\n".join(
            [
                "Commands:",
                "/run <prompt>",
                "/status <task_id>",
                "/approve <task_id>",
                "/reject <task_id>",
                "/help",
            ]
        )
