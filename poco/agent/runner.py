from __future__ import annotations

from collections.abc import Iterator
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol

from poco.task.models import Task

UpdateKind = Literal["progress", "confirmation_required", "completed", "failed"]


@dataclass(frozen=True, slots=True)
class AgentRunUpdate:
    kind: UpdateKind
    message: str
    output_chunk: str | None = None
    raw_result: str | None = None

    @property
    def result_summary(self) -> str | None:
        return self.raw_result


class AgentRunner(Protocol):
    name: str

    def is_ready(self) -> tuple[bool, str]:
        ...

    def start(self, task: Task) -> Iterator[AgentRunUpdate]:
        ...

    def resume_after_confirmation(self, task: Task) -> Iterator[AgentRunUpdate]:
        ...

    def cancel(self, task_id: str) -> bool:
        ...

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None]:
        ...


class StubAgentRunner:
    """A minimal stand-in for a real server-side agent executor."""

    name = "stub"

    def is_ready(self) -> tuple[bool, str]:
        return True, "Stub runner is always available."

    def start(self, task: Task) -> Iterator[AgentRunUpdate]:
        updates = [
            AgentRunUpdate(
                kind="progress",
                message="Task accepted by the stub runner.",
            )
        ]
        if _requires_confirmation(task.prompt):
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
                raw_result=f"Stub result for: {_normalized_prompt(task.prompt)}",
            )
        )
        return updates

    def resume_after_confirmation(self, task: Task) -> Iterator[AgentRunUpdate]:
        return [
            AgentRunUpdate(
                kind="progress",
                message="Approval received. Resuming stub execution.",
            ),
            AgentRunUpdate(
                kind="completed",
                message="Task completed after approval.",
                raw_result=f"Approved stub result for: {_normalized_prompt(task.prompt)}",
            ),
        ]

    def cancel(self, task_id: str) -> bool:
        return False

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None]:
        return self.name, task.effective_workdir


class UnavailableAgentRunner:
    def __init__(self, *, name: str, reason: str) -> None:
        self.name = name
        self._reason = reason

    def is_ready(self) -> tuple[bool, str]:
        return False, self._reason

    def start(self, task: Task) -> Iterator[AgentRunUpdate]:
        return [AgentRunUpdate(kind="failed", message=self._reason)]

    def resume_after_confirmation(self, task: Task) -> Iterator[AgentRunUpdate]:
        return [AgentRunUpdate(kind="failed", message=self._reason)]

    def cancel(self, task_id: str) -> bool:
        return False

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None]:
        return self.name, task.effective_workdir


class CodexCliRunner:
    name = "codex"

    def __init__(
        self,
        *,
        command: str = "codex",
        workdir: str,
        model: str | None = None,
        sandbox: str = "workspace-write",
        approval_policy: str = "never",
        timeout_seconds: int = 900,
    ) -> None:
        self._command = command
        self._workdir = workdir
        self._model = model
        self._sandbox = sandbox
        self._approval_policy = approval_policy
        self._timeout_seconds = timeout_seconds
        self._lock = RLock()
        self._active_processes: dict[str, subprocess.Popen[str]] = {}
        self._cancelled_tasks: set[str] = set()

    def is_ready(self) -> tuple[bool, str]:
        executable = shutil.which(self._command)
        if not executable:
            return False, f"Codex CLI not found: {self._command}"
        if not Path(self._workdir).exists():
            return False, f"Codex workdir does not exist: {self._workdir}"
        return True, f"Codex CLI ready at {executable}"

    def start(self, task: Task) -> Iterator[AgentRunUpdate]:
        updates = [
            AgentRunUpdate(
                kind="progress",
                message=f"Task accepted by the {self.name} runner.",
            )
        ]
        if _requires_confirmation(task.prompt):
            updates.append(
                AgentRunUpdate(
                    kind="confirmation_required",
                    message="Awaiting explicit approval before invoking codex.",
                )
            )
            return updates

        updates.extend(self._execute_prompt(task, _normalized_prompt(task.prompt)))
        return updates

    def resume_after_confirmation(self, task: Task) -> Iterator[AgentRunUpdate]:
        updates = [
            AgentRunUpdate(
                kind="progress",
                message="Approval received. Invoking codex.",
            )
        ]
        updates.extend(self._execute_prompt(task, _normalized_prompt(task.prompt)))
        return updates

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            process = self._active_processes.get(task_id)
            if process is None:
                return False
            self._cancelled_tasks.add(task_id)
        process.kill()
        return True

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None]:
        return task.effective_model or self._model or self.name, task.effective_workdir or self._workdir

    def _execute_prompt(self, task: Task, prompt: str) -> Iterator[AgentRunUpdate]:
        executable = shutil.which(self._command)
        if not executable:
            yield AgentRunUpdate(kind="failed", message=f"Codex CLI not found: {self._command}")
            return

        workdir = task.effective_workdir or self._workdir
        if not Path(workdir).exists():
            yield AgentRunUpdate(kind="failed", message=f"Codex workdir does not exist: {workdir}")
            return

        output_file_path: str | None = None
        process: subprocess.Popen[str] | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="poco-codex-", suffix=".txt", delete=False) as handle:
                output_file_path = handle.name

            command = [self._command]
            if self._approval_policy:
                command.extend(["-a", self._approval_policy])
            command.extend(
                [
                    "exec",
                    "-C",
                    workdir,
                    "-s",
                    self._sandbox,
                    "--skip-git-repo-check",
                    "--color",
                    "never",
                    "-o",
                    output_file_path,
                    prompt,
                ]
            )
            resolved_model = task.effective_model or self._model
            if resolved_model:
                command[command.index("exec") + 1:command.index("exec") + 1] = [
                    "-m",
                    resolved_model,
                ]

            process = subprocess.Popen(
                command,
                cwd=workdir,
                env=os.environ.copy(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            with self._lock:
                self._active_processes[task.id] = process
            streamed_output: list[str] = []
            if process.stdout is not None:
                for line in process.stdout:
                    if not line:
                        continue
                    streamed_output.append(line)
                    yield AgentRunUpdate(
                        kind="progress",
                        message="Codex output updated.",
                        output_chunk=line,
                    )
                process.stdout.close()

            returncode = process.wait(timeout=self._timeout_seconds)
            if self._consume_cancelled(task.id):
                return
            if returncode != 0:
                detail = _first_non_empty(
                    "".join(streamed_output),
                    "Codex CLI exited with a non-zero status.",
                )
                yield AgentRunUpdate(kind="failed", message=detail)
                return

            raw_result = self._read_output_file(output_file_path)
            message = "Task completed by the codex runner."
            yield AgentRunUpdate(
                kind="completed",
                message=message,
                raw_result=raw_result or "Codex completed without a final response body.",
            )
        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
            if self._consume_cancelled(task.id):
                return
            yield AgentRunUpdate(
                kind="failed",
                message=f"Codex CLI timed out after {self._timeout_seconds} seconds.",
            )
        except OSError as exc:
            yield AgentRunUpdate(
                kind="failed",
                message=f"Failed to start codex CLI: {exc}",
            )
        finally:
            with self._lock:
                self._active_processes.pop(task.id, None)
                self._cancelled_tasks.discard(task.id)
            if output_file_path:
                Path(output_file_path).unlink(missing_ok=True)

    def _consume_cancelled(self, task_id: str) -> bool:
        with self._lock:
            if task_id not in self._cancelled_tasks:
                return False
            self._cancelled_tasks.discard(task_id)
            return True

    def _read_output_file(self, output_file_path: str) -> str | None:
        path = Path(output_file_path)
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return None
        return content


def create_agent_runner(
    *,
    backend: str,
    codex_command: str,
    codex_workdir: str,
    codex_model: str | None,
    codex_sandbox: str,
    codex_approval_policy: str,
    codex_timeout_seconds: int,
) -> AgentRunner:
    normalized = backend.strip().lower()
    if normalized == "codex":
        return CodexCliRunner(
            command=codex_command,
            workdir=codex_workdir,
            model=codex_model,
            sandbox=codex_sandbox,
            approval_policy=codex_approval_policy,
            timeout_seconds=codex_timeout_seconds,
        )
    if normalized == "stub":
        return StubAgentRunner()
    if normalized in {"claude_code", "cursor_agent"}:
        return UnavailableAgentRunner(
            name=normalized,
            reason=(
                f"Agent backend '{normalized}' is planned but not implemented yet. "
                "Current working backend is 'codex'."
            ),
        )
    return UnavailableAgentRunner(
        name=normalized or "unknown",
        reason=(
            f"Unsupported agent backend: {backend}. "
            "Current implemented backends are 'codex' and 'stub'."
        ),
    )


def _requires_confirmation(prompt: str) -> bool:
    return prompt.lower().startswith("confirm:")


def _normalized_prompt(prompt: str) -> str:
    if _requires_confirmation(prompt):
        return prompt.split(":", 1)[1].strip()
    return prompt.strip()


def _first_non_empty(*candidates: str) -> str:
    for candidate in candidates:
        text = candidate.strip()
        if text:
            return text
    return ""
