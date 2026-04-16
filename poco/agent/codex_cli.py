from __future__ import annotations

from collections.abc import Iterator
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from threading import RLock

from poco.agent.common import (
    AgentRunUpdate,
    _cleanup_subprocess,
    _first_non_empty,
    _normalized_prompt,
    _optional_string,
    _parse_json_event,
    _requires_confirmation,
    _string_or_none,
)
from poco.task.models import Task


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
        yield AgentRunUpdate(
            kind="progress",
            message=f"Task accepted by the {self.name} runner.",
        )
        if _requires_confirmation(task.prompt):
            yield AgentRunUpdate(
                kind="confirmation_required",
                message="Awaiting explicit approval before invoking codex.",
            )
            return

        yield from self._execute_prompt(task, _normalized_prompt(task.prompt))

    def resume_after_confirmation(self, task: Task) -> Iterator[AgentRunUpdate]:
        yield AgentRunUpdate(
            kind="progress",
            message="Approval received. Invoking codex.",
        )
        yield from self._execute_prompt(task, _normalized_prompt(task.prompt))

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            process = self._active_processes.get(task_id)
            if process is None:
                return False
            self._cancelled_tasks.add(task_id)
        process.kill()
        return True

    def steer(self, task: Task, prompt: str) -> tuple[bool, str]:
        return False, f"Steer is not supported by the {self.name} runner."

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        return (
            task.effective_model or self._model,
            task.effective_workdir or self._workdir,
            task.effective_sandbox or self._sandbox,
        )

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
        backend_session_id = task.backend_session_id
        try:
            with tempfile.NamedTemporaryFile(prefix="poco-codex-", suffix=".txt", delete=False) as handle:
                output_file_path = handle.name

            command = self._build_command(
                task=task,
                prompt=prompt,
                workdir=workdir,
                output_file_path=output_file_path,
            )

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
                    event = _parse_json_event(line)
                    if event is None:
                        yield AgentRunUpdate(
                            kind="progress",
                            message="Codex output updated.",
                            output_chunk=line,
                            backend_session_id=backend_session_id,
                        )
                        continue
                    if event.get("type") == "thread.started":
                        backend_session_id = _optional_string(event.get("thread_id")) or backend_session_id
                        yield AgentRunUpdate(
                            kind="progress",
                            message="Codex session ready.",
                            backend_session_id=backend_session_id,
                        )
                        continue
                    if event.get("type") == "item.completed":
                        item = event.get("item") or {}
                        if item.get("type") == "agent_message":
                            text = _string_or_none(item.get("text"))
                            if text:
                                yield AgentRunUpdate(
                                    kind="progress",
                                    message="Codex output updated.",
                                    output_chunk=f"{text}\n",
                                    backend_session_id=backend_session_id,
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
                yield AgentRunUpdate(
                    kind="failed",
                    message=detail,
                    backend_session_id=backend_session_id,
                )
                return

            raw_result = self._read_output_file(output_file_path)
            message = "Task completed by the codex runner."
            yield AgentRunUpdate(
                kind="completed",
                message=message,
                raw_result=raw_result or "Codex completed without a final response body.",
                backend_session_id=backend_session_id,
            )
        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
            if self._consume_cancelled(task.id):
                return
            yield AgentRunUpdate(
                kind="failed",
                message=f"Codex CLI timed out after {self._timeout_seconds} seconds.",
                backend_session_id=backend_session_id,
            )
        except OSError as exc:
            yield AgentRunUpdate(
                kind="failed",
                message=f"Failed to start codex CLI: {exc}",
                backend_session_id=backend_session_id,
            )
        finally:
            with self._lock:
                self._active_processes.pop(task.id, None)
                self._cancelled_tasks.discard(task.id)
            _cleanup_subprocess(process)
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

    def _build_command(
        self,
        *,
        task: Task,
        prompt: str,
        workdir: str,
        output_file_path: str,
    ) -> list[str]:
        command = [self._command]
        resolved_model = task.effective_model or self._model
        if resolved_model:
            command.extend(["-m", resolved_model])
        if self._approval_policy:
            command.extend(["-a", self._approval_policy])
        resolved_sandbox = task.effective_sandbox or self._sandbox
        if resolved_sandbox:
            command.extend(["-s", resolved_sandbox])
        command.extend(["exec"])
        if task.backend_session_id:
            command.extend(
                [
                    "resume",
                    "--json",
                    "--skip-git-repo-check",
                    "-o",
                    output_file_path,
                    task.backend_session_id,
                    prompt,
                ]
            )
            return command
        command.extend(
            [
                "--json",
                "-C",
                workdir,
                "--skip-git-repo-check",
                "--color",
                "never",
                "-o",
                output_file_path,
                prompt,
            ]
        )
        return command
