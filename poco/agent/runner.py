from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from poco.task.models import Task

UpdateKind = Literal["progress", "confirmation_required", "completed", "failed"]


@dataclass(frozen=True, slots=True)
class AgentRunUpdate:
    kind: UpdateKind
    message: str
    raw_result: str | None = None

    @property
    def result_summary(self) -> str | None:
        return self.raw_result


class AgentRunner(Protocol):
    name: str

    def is_ready(self) -> tuple[bool, str]:
        ...

    def start(self, task: Task) -> list[AgentRunUpdate]:
        ...

    def resume_after_confirmation(self, task: Task) -> list[AgentRunUpdate]:
        ...


class StubAgentRunner:
    """A minimal stand-in for a real server-side agent executor."""

    name = "stub"

    def is_ready(self) -> tuple[bool, str]:
        return True, "Stub runner is always available."

    def start(self, task: Task) -> list[AgentRunUpdate]:
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

    def resume_after_confirmation(self, task: Task) -> list[AgentRunUpdate]:
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


class UnavailableAgentRunner:
    def __init__(self, *, name: str, reason: str) -> None:
        self.name = name
        self._reason = reason

    def is_ready(self) -> tuple[bool, str]:
        return False, self._reason

    def start(self, task: Task) -> list[AgentRunUpdate]:
        return [AgentRunUpdate(kind="failed", message=self._reason)]

    def resume_after_confirmation(self, task: Task) -> list[AgentRunUpdate]:
        return [AgentRunUpdate(kind="failed", message=self._reason)]


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

    def is_ready(self) -> tuple[bool, str]:
        executable = shutil.which(self._command)
        if not executable:
            return False, f"Codex CLI not found: {self._command}"
        if not Path(self._workdir).exists():
            return False, f"Codex workdir does not exist: {self._workdir}"
        return True, f"Codex CLI ready at {executable}"

    def start(self, task: Task) -> list[AgentRunUpdate]:
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

    def resume_after_confirmation(self, task: Task) -> list[AgentRunUpdate]:
        updates = [
            AgentRunUpdate(
                kind="progress",
                message="Approval received. Invoking codex.",
            )
        ]
        updates.extend(self._execute_prompt(task, _normalized_prompt(task.prompt)))
        return updates

    def _execute_prompt(self, task: Task, prompt: str) -> list[AgentRunUpdate]:
        executable = shutil.which(self._command)
        if not executable:
            return [AgentRunUpdate(kind="failed", message=f"Codex CLI not found: {self._command}")]

        workdir = task.effective_workdir or self._workdir
        if not Path(workdir).exists():
            return [AgentRunUpdate(kind="failed", message=f"Codex workdir does not exist: {workdir}")]

        output_file_path: str | None = None
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
            if self._model:
                command[command.index("exec") + 1:command.index("exec") + 1] = [
                    "-m",
                    self._model,
                ]

            completed = subprocess.run(
                command,
                cwd=workdir,
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                detail = _first_non_empty(
                    completed.stderr,
                    completed.stdout,
                    "Codex CLI exited with a non-zero status.",
                )
                return [AgentRunUpdate(kind="failed", message=detail)]

            raw_result = self._read_output_file(output_file_path)
            message = "Task completed by the codex runner."
            return [
                AgentRunUpdate(
                    kind="completed",
                    message=message,
                    raw_result=raw_result or "Codex completed without a final response body.",
                )
            ]
        except subprocess.TimeoutExpired:
            return [
                AgentRunUpdate(
                    kind="failed",
                    message=f"Codex CLI timed out after {self._timeout_seconds} seconds.",
                )
            ]
        except OSError as exc:
            return [
                AgentRunUpdate(
                    kind="failed",
                    message=f"Failed to start codex CLI: {exc}",
                )
            ]
        finally:
            if output_file_path:
                Path(output_file_path).unlink(missing_ok=True)

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
