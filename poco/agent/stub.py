from __future__ import annotations

from collections.abc import Iterator

from poco.agent.common import (
    AgentRunUpdate,
    AgentRunner,
    _normalized_prompt,
    _requires_confirmation,
)
from poco.task.models import Task


class StubAgentRunner:
    """A minimal stand-in for a real server-side agent executor."""

    name = "stub"

    def is_ready(self) -> tuple[bool, str]:
        return True, "Stub runner is always available."

    def start(self, task: Task) -> Iterator[AgentRunUpdate]:
        yield AgentRunUpdate(
            kind="progress",
            message="Task accepted by the stub runner.",
        )
        if _requires_confirmation(task.prompt):
            yield AgentRunUpdate(
                kind="confirmation_required",
                message="Awaiting explicit approval before continuing.",
            )
            return

        yield AgentRunUpdate(
            kind="completed",
            message="Task completed by the stub runner.",
            raw_result=f"Stub result for: {_normalized_prompt(task.prompt)}",
        )

    def resume_after_confirmation(self, task: Task) -> Iterator[AgentRunUpdate]:
        yield AgentRunUpdate(
            kind="progress",
            message="Approval received. Resuming stub execution.",
        )
        yield AgentRunUpdate(
            kind="completed",
            message="Task completed after approval.",
            raw_result=f"Approved stub result for: {_normalized_prompt(task.prompt)}",
        )

    def cancel(self, task_id: str) -> bool:
        return False

    def steer(self, task: Task, prompt: str) -> tuple[bool, str]:
        return False, f"Steer is not supported by the {self.name} runner."

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        return self.name, task.effective_workdir, task.effective_sandbox

    def is_task_active(self, task: Task) -> bool | None:
        return None


class UnavailableAgentRunner:
    def __init__(self, *, name: str, reason: str) -> None:
        self.name = name
        self._reason = reason

    def is_ready(self) -> tuple[bool, str]:
        return False, self._reason

    def start(self, task: Task) -> Iterator[AgentRunUpdate]:
        yield AgentRunUpdate(kind="failed", message=self._reason)

    def resume_after_confirmation(self, task: Task) -> Iterator[AgentRunUpdate]:
        yield AgentRunUpdate(kind="failed", message=self._reason)

    def cancel(self, task_id: str) -> bool:
        return False

    def steer(self, task: Task, prompt: str) -> tuple[bool, str]:
        return False, self._reason

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        return self.name, task.effective_workdir, task.effective_sandbox

    def is_task_active(self, task: Task) -> bool | None:
        return False


class MultiAgentRunner:
    def __init__(
        self,
        *,
        default_backend: str,
        runners: dict[str, AgentRunner],
    ) -> None:
        self.name = default_backend
        self._default_backend = default_backend
        self._runners = dict(runners)

    def is_ready(self) -> tuple[bool, str]:
        runner = self._runners.get(self._default_backend)
        if runner is None:
            return False, f"Default backend is not configured: {self._default_backend}"
        ready, detail = runner.is_ready()
        return ready, f"default={self._default_backend}; {detail}"

    def start(self, task: Task) -> Iterator[AgentRunUpdate]:
        return self._delegate(task).start(task)

    def resume_after_confirmation(self, task: Task) -> Iterator[AgentRunUpdate]:
        return self._delegate(task).resume_after_confirmation(task)

    def cancel(self, task_id: str) -> bool:
        cancelled = False
        for runner in self._runners.values():
            cancelled = runner.cancel(task_id) or cancelled
        return cancelled

    def steer(self, task: Task, prompt: str) -> tuple[bool, str]:
        return self._delegate(task).steer(task, prompt)

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        return self._delegate(task).resolve_execution_context(task)

    def is_task_active(self, task: Task) -> bool | None:
        delegate = self._delegate(task)
        probe = getattr(delegate, "is_task_active", None)
        if not callable(probe):
            return None
        return probe(task)

    def warm(
        self,
        *,
        backend: str,
        workdir: str,
        reasoning_effort: str | None = None,
    ) -> bool:
        runner = self._runners.get(backend)
        if runner is None:
            return False
        warm_method = getattr(runner, "warm", None)
        if not callable(warm_method):
            return False
        try:
            result = warm_method(workdir=workdir, reasoning_effort=reasoning_effort)
        except TypeError:
            return False
        return bool(result)

    def _delegate(self, task: Task) -> AgentRunner:
        runner = self._runners.get(task.agent_backend)
        if runner is not None:
            return runner
        return UnavailableAgentRunner(
            name=task.agent_backend or "unknown",
            reason=f"Unsupported agent backend: {task.agent_backend}",
        )
