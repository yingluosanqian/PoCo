from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from poco.task.models import Task

UpdateKind = Literal["progress", "confirmation_required", "completed"]


@dataclass(frozen=True, slots=True)
class AgentRunUpdate:
    kind: UpdateKind
    message: str
    result_summary: str | None = None


class StubAgentRunner:
    """A minimal stand-in for a real server-side agent executor."""

    def start(self, task: Task) -> list[AgentRunUpdate]:
        updates = [
            AgentRunUpdate(
                kind="progress",
                message="Task accepted by the server-side runner.",
            )
        ]
        if task.prompt.lower().startswith("confirm:"):
            updates.append(
                AgentRunUpdate(
                    kind="confirmation_required",
                    message="Awaiting explicit approval before continuing.",
                )
            )
            return updates

        updates.append(
            AgentRunUpdate(
                kind="completed",
                message="Task completed by the stub runner.",
                result_summary=f"Stub result for: {task.prompt}",
            )
        )
        return updates

    def resume_after_confirmation(self, task: Task) -> list[AgentRunUpdate]:
        return [
            AgentRunUpdate(
                kind="progress",
                message="Approval received. Resuming server-side execution.",
            ),
            AgentRunUpdate(
                kind="completed",
                message="Task completed after approval.",
                result_summary=f"Approved stub result for: {task.prompt}",
            ),
        ]
