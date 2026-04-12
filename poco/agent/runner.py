from __future__ import annotations

from collections import deque
from collections.abc import Iterator
import json
import os
import select
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Literal, Protocol

from poco.task.models import Task

UpdateKind = Literal["progress", "confirmation_required", "completed", "failed"]
_TraePromptEventKind = Literal["output", "completed", "failed", "cancelled"]


@dataclass(frozen=True, slots=True)
class AgentRunUpdate:
    kind: UpdateKind
    message: str
    output_chunk: str | None = None
    raw_result: str | None = None
    backend_session_id: str | None = None

    @property
    def result_summary(self) -> str | None:
        return self.raw_result


@dataclass(frozen=True, slots=True)
class _TraePromptEvent:
    kind: _TraePromptEventKind
    message: str
    output_chunk: str | None = None
    raw_result: str | None = None


@dataclass(slots=True)
class _TraePromptTurnState:
    session_id: str
    prompt_request_id: int
    ignored_message_ids: set[str] = field(default_factory=set)
    live_text: str = ""
    current_chunk_id: str | None = None

    def should_ignore_message(self, message_id: str | None) -> bool:
        return bool(
            message_id
            and self.current_chunk_id is None
            and message_id in self.ignored_message_ids
        )

    def record_message_id(self, message_id: str | None) -> None:
        if message_id:
            self.ignored_message_ids.add(message_id)


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

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        ...


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

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        return self.name, task.effective_workdir, task.effective_sandbox


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

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        return self.name, task.effective_workdir, task.effective_sandbox


def _cleanup_subprocess(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(process, stream_name, None)
        if stream is None:
            continue
        try:
            stream.close()
        except Exception:
            pass
    try:
        process.wait(timeout=1)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
        try:
            process.wait(timeout=1)
        except Exception:
            pass


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

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        return self._delegate(task).resolve_execution_context(task)

    def _delegate(self, task: Task) -> AgentRunner:
        runner = self._runners.get(task.agent_backend)
        if runner is not None:
            return runner
        return UnavailableAgentRunner(
            name=task.agent_backend or "unknown",
            reason=f"Unsupported agent backend: {task.agent_backend}",
        )


class CodexAppServerRunner:
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
        return True, f"Codex app-server ready via {executable}"

    def start(self, task: Task) -> Iterator[AgentRunUpdate]:
        yield AgentRunUpdate(
            kind="progress",
            message=f"Task accepted by the {self.name} app-server runner.",
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

        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                [self._command, "app-server", "--listen", "stdio://"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=workdir,
                env=os.environ.copy(),
            )
            with self._lock:
                self._active_processes[task.id] = process
            session = _CodexAppServerSession(
                process=process,
                timeout_seconds=self._timeout_seconds,
            )
            session.initialize()

            resolved_model = task.effective_model or self._model
            thread_result: dict[str, object]
            if task.backend_session_id:
                thread_result = session.request(
                    "thread/resume",
                    {
                        "threadId": task.backend_session_id,
                        "cwd": workdir,
                        "model": resolved_model,
                        "sandbox": task.effective_sandbox or self._sandbox,
                        "approvalPolicy": self._approval_policy,
                    },
                )
            else:
                thread_result = session.request(
                    "thread/start",
                    {
                        "cwd": workdir,
                        "model": resolved_model,
                        "sandbox": task.effective_sandbox or self._sandbox,
                        "approvalPolicy": self._approval_policy,
                    },
                )
            backend_session_id = _extract_thread_id(thread_result) or task.backend_session_id
            if backend_session_id:
                yield AgentRunUpdate(
                    kind="progress",
                    message="Codex session ready.",
                    backend_session_id=backend_session_id,
                )

            session.request(
                "turn/start",
                {
                    "threadId": backend_session_id,
                    "cwd": workdir,
                    "model": resolved_model,
                    "input": [{"type": "text", "text": prompt}],
                },
            )

            final_text: str | None = None
            while True:
                if self._consume_cancelled(task.id):
                    return
                message = session.read_next_message()
                if message is None:
                    break
                if "method" not in message:
                    continue
                method = str(message["method"])
                params = message.get("params")
                if not isinstance(params, dict):
                    continue

                if method == "item/agentMessage/delta":
                    delta = _string_or_none(params.get("delta"))
                    if delta:
                        yield AgentRunUpdate(
                            kind="progress",
                            message="Codex output updated.",
                            output_chunk=delta,
                            backend_session_id=backend_session_id,
                        )
                    continue

                if method == "item/completed":
                    item = params.get("item")
                    if isinstance(item, dict) and item.get("type") == "agentMessage":
                        final_text = _string_or_none(item.get("text")) or final_text
                    continue

                if method == "turn/completed":
                    turn = params.get("turn")
                    if isinstance(turn, dict) and turn.get("error"):
                        yield AgentRunUpdate(
                            kind="failed",
                            message=_turn_error_message(turn) or "Codex turn failed.",
                            backend_session_id=backend_session_id,
                        )
                        return
                    yield AgentRunUpdate(
                        kind="completed",
                        message="Task completed by the codex app-server runner.",
                        raw_result=final_text or "Codex completed without a final response body.",
                        backend_session_id=backend_session_id,
                    )
                    return

                if method == "thread/status/changed":
                    status = params.get("status")
                    if (
                        isinstance(status, dict)
                        and status.get("type") == "idle"
                        and final_text is not None
                    ):
                        yield AgentRunUpdate(
                            kind="completed",
                            message="Task completed by the codex app-server runner.",
                            raw_result=final_text,
                            backend_session_id=backend_session_id,
                        )
                        return
                    continue

                if method == "error":
                    yield AgentRunUpdate(
                        kind="failed",
                        message=_error_notification_message(params) or "Codex app-server returned an error.",
                        backend_session_id=backend_session_id,
                    )
                    return

            if self._consume_cancelled(task.id):
                return
            yield AgentRunUpdate(
                kind="failed",
                message=session.failure_detail("Codex app-server closed before task completion."),
                backend_session_id=backend_session_id,
            )
        except OSError as exc:
            yield AgentRunUpdate(
                kind="failed",
                message=f"Failed to start codex app-server: {exc}",
                backend_session_id=task.backend_session_id,
            )
        finally:
            with self._lock:
                self._active_processes.pop(task.id, None)
                self._cancelled_tasks.discard(task.id)
            _cleanup_subprocess(process)

    def _consume_cancelled(self, task_id: str) -> bool:
        with self._lock:
            if task_id not in self._cancelled_tasks:
                return False
            self._cancelled_tasks.discard(task_id)
            return True


class ClaudeCodeRunner:
    name = "claude_code"

    def __init__(
        self,
        *,
        command: str = "claude",
        workdir: str,
        model: str | None = None,
        permission_mode: str = "default",
        timeout_seconds: int = 900,
    ) -> None:
        self._command = command
        self._workdir = workdir
        self._model = model
        self._permission_mode = permission_mode
        self._timeout_seconds = timeout_seconds
        self._lock = RLock()
        self._active_processes: dict[str, subprocess.Popen[str]] = {}
        self._cancelled_tasks: set[str] = set()

    def is_ready(self) -> tuple[bool, str]:
        executable = shutil.which(self._command)
        if not executable:
            return False, f"Claude Code CLI not found: {self._command}"
        if not Path(self._workdir).exists():
            return False, f"Claude Code workdir does not exist: {self._workdir}"
        return True, f"Claude Code ready via {executable}"

    def start(self, task: Task) -> Iterator[AgentRunUpdate]:
        yield AgentRunUpdate(
            kind="progress",
            message=f"Task accepted by the {self.name} runner.",
        )
        if _requires_confirmation(task.prompt):
            yield AgentRunUpdate(
                kind="confirmation_required",
                message="Awaiting explicit approval before invoking Claude Code.",
            )
            return
        yield from self._execute_prompt(task, _normalized_prompt(task.prompt))

    def resume_after_confirmation(self, task: Task) -> Iterator[AgentRunUpdate]:
        yield AgentRunUpdate(
            kind="progress",
            message="Approval received. Invoking Claude Code.",
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

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        permission_mode = _string_or_none(task.effective_backend_config.get("permission_mode"))
        return (
            task.effective_model or self._model,
            task.effective_workdir or self._workdir,
            permission_mode or self._permission_mode,
        )

    def _execute_prompt(self, task: Task, prompt: str) -> Iterator[AgentRunUpdate]:
        executable = shutil.which(self._command)
        if not executable:
            yield AgentRunUpdate(kind="failed", message=f"Claude Code CLI not found: {self._command}")
            return

        workdir = task.effective_workdir or self._workdir
        if not Path(workdir).exists():
            yield AgentRunUpdate(kind="failed", message=f"Claude Code workdir does not exist: {workdir}")
            return

        resolved_model = task.effective_model or self._model
        resolved_permission_mode = _string_or_none(task.effective_backend_config.get("permission_mode")) or self._permission_mode
        command = [
            self._command,
            "-p",
            "--verbose",
            "--output-format=stream-json",
            "--include-partial-messages",
        ]
        if resolved_model:
            command.extend(["--model", resolved_model])
        if resolved_permission_mode:
            command.extend(["--permission-mode", resolved_permission_mode])
        if task.backend_session_id:
            command.extend(["--resume", task.backend_session_id])
        command.append(prompt)
        env = os.environ.copy()
        if resolved_permission_mode == "bypassPermissions":
            env["IS_SANDBOX"] = "1"

        process: subprocess.Popen[str] | None = None
        backend_session_id = task.backend_session_id
        stderr_lines: list[str] = []
        final_text: str | None = None
        try:
            process = subprocess.Popen(
                command,
                cwd=workdir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            with self._lock:
                self._active_processes[task.id] = process

            deadline = monotonic() + self._timeout_seconds
            stdout = process.stdout
            stderr = process.stderr
            if stdout is None or stderr is None:
                yield AgentRunUpdate(kind="failed", message="Claude Code pipes are not available.")
                return

            while True:
                if self._consume_cancelled(task.id):
                    return
                if process.poll() is not None and not _has_ready_stream(stdout, stderr):
                    break
                remaining = max(0.0, deadline - monotonic())
                if remaining == 0.0:
                    process.kill()
                    yield AgentRunUpdate(
                        kind="failed",
                        message=f"Claude Code timed out after {self._timeout_seconds} seconds.",
                        backend_session_id=backend_session_id,
                    )
                    return
                ready, _, _ = select.select([stdout, stderr], [], [], min(0.25, remaining))
                if not ready:
                    continue
                for stream in ready:
                    line = stream.readline()
                    if not line:
                        continue
                    if stream is stderr:
                        stderr_lines.append(line)
                        continue
                    event = _parse_json_event(line)
                    if event is None:
                        continue
                    event_type = _optional_string(event.get("type")) or ""
                    if event_type == "system" and event.get("subtype") == "init":
                        backend_session_id = _optional_string(event.get("session_id")) or backend_session_id
                        if backend_session_id:
                            yield AgentRunUpdate(
                                kind="progress",
                                message="Claude Code session ready.",
                                backend_session_id=backend_session_id,
                            )
                        continue
                    if event_type == "stream_event":
                        stream_event = event.get("event")
                        if isinstance(stream_event, dict) and stream_event.get("type") == "content_block_delta":
                            delta = stream_event.get("delta")
                            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                                text = _string_or_none(delta.get("text"))
                                if text:
                                    yield AgentRunUpdate(
                                        kind="progress",
                                        message="Claude Code output updated.",
                                        output_chunk=text,
                                        backend_session_id=backend_session_id,
                                    )
                        continue
                    if event_type == "assistant":
                        message = event.get("message")
                        if isinstance(message, dict):
                            final_text = _extract_claude_message_text(message) or final_text
                        backend_session_id = _optional_string(event.get("session_id")) or backend_session_id
                        continue
                    if event_type == "result":
                        backend_session_id = _optional_string(event.get("session_id")) or backend_session_id
                        if event.get("subtype") == "success":
                            raw_result = _optional_string(event.get("result")) or final_text or "Claude Code completed without a final response body."
                            yield AgentRunUpdate(
                                kind="completed",
                                message="Task completed by the claude_code runner.",
                                raw_result=raw_result,
                                backend_session_id=backend_session_id,
                            )
                            return
                        detail = _optional_string(event.get("result")) or _optional_string(event.get("error")) or "".join(stderr_lines).strip() or "Claude Code failed."
                        yield AgentRunUpdate(
                            kind="failed",
                            message=detail,
                            backend_session_id=backend_session_id,
                        )
                        return

            if self._consume_cancelled(task.id):
                return
            if process.returncode and process.returncode != 0:
                yield AgentRunUpdate(
                    kind="failed",
                    message="".join(stderr_lines).strip() or "Claude Code exited with a non-zero status.",
                    backend_session_id=backend_session_id,
                )
                return
            yield AgentRunUpdate(
                kind="completed",
                message="Task completed by the claude_code runner.",
                raw_result=final_text or "Claude Code completed without a final response body.",
                backend_session_id=backend_session_id,
            )
        except OSError as exc:
            yield AgentRunUpdate(
                kind="failed",
                message=f"Failed to start Claude Code CLI: {exc}",
                backend_session_id=backend_session_id,
            )
        finally:
            with self._lock:
                self._active_processes.pop(task.id, None)
                self._cancelled_tasks.discard(task.id)
            _cleanup_subprocess(process)

    def _consume_cancelled(self, task_id: str) -> bool:
        with self._lock:
            if task_id not in self._cancelled_tasks:
                return False
            self._cancelled_tasks.discard(task_id)
            return True


class CursorAgentRunner:
    name = "cursor_agent"

    def __init__(
        self,
        *,
        command: str = "cursor-agent",
        workdir: str,
        model: str | None = None,
        mode: str = "default",
        sandbox: str = "default",
        timeout_seconds: int = 900,
    ) -> None:
        self._command = command
        self._workdir = workdir
        self._model = model
        self._mode = mode
        self._sandbox = sandbox
        self._timeout_seconds = timeout_seconds
        self._lock = RLock()
        self._active_processes: dict[str, subprocess.Popen[str]] = {}
        self._cancelled_tasks: set[str] = set()

    def is_ready(self) -> tuple[bool, str]:
        executable = shutil.which(self._command)
        if not executable:
            return False, f"Cursor Agent CLI not found: {self._command}"
        if not Path(self._workdir).exists():
            return False, f"Cursor Agent workdir does not exist: {self._workdir}"
        return True, f"Cursor Agent ready via {executable}"

    def start(self, task: Task) -> Iterator[AgentRunUpdate]:
        yield AgentRunUpdate(
            kind="progress",
            message=f"Task accepted by the {self.name} runner.",
        )
        if _requires_confirmation(task.prompt):
            yield AgentRunUpdate(
                kind="confirmation_required",
                message="Awaiting explicit approval before invoking Cursor Agent.",
            )
            return
        yield from self._execute_prompt(task, _normalized_prompt(task.prompt))

    def resume_after_confirmation(self, task: Task) -> Iterator[AgentRunUpdate]:
        yield AgentRunUpdate(
            kind="progress",
            message="Approval received. Invoking Cursor Agent.",
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

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        return (
            task.effective_model or self._model,
            task.effective_workdir or self._workdir,
            _string_or_none(task.effective_backend_config.get("sandbox")) or self._sandbox,
        )

    def _execute_prompt(self, task: Task, prompt: str) -> Iterator[AgentRunUpdate]:
        executable = shutil.which(self._command)
        if not executable:
            yield AgentRunUpdate(kind="failed", message=f"Cursor Agent CLI not found: {self._command}")
            return

        workdir = task.effective_workdir or self._workdir
        if not Path(workdir).exists():
            yield AgentRunUpdate(kind="failed", message=f"Cursor Agent workdir does not exist: {workdir}")
            return

        resolved_model = task.effective_model or self._model
        resolved_mode = _string_or_none(task.effective_backend_config.get("mode")) or self._mode
        resolved_sandbox = _string_or_none(task.effective_backend_config.get("sandbox")) or self._sandbox
        command = [
            self._command,
            "-p",
            "--output-format",
            "stream-json",
            "--stream-partial-output",
            "--trust",
            "--workspace",
            workdir,
        ]
        if resolved_model:
            command.extend(["--model", resolved_model])
        if resolved_mode and resolved_mode != "default":
            command.extend(["--mode", resolved_mode])
        if resolved_sandbox and resolved_sandbox != "default":
            command.extend(["--sandbox", resolved_sandbox])
        if task.backend_session_id:
            command.extend(["--resume", task.backend_session_id])
        command.append(prompt)

        process: subprocess.Popen[str] | None = None
        backend_session_id = task.backend_session_id
        stderr_lines: list[str] = []
        final_text: str | None = None
        live_text = ""
        try:
            process = subprocess.Popen(
                command,
                cwd=workdir,
                env=os.environ.copy(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            with self._lock:
                self._active_processes[task.id] = process

            deadline = monotonic() + self._timeout_seconds
            stdout = process.stdout
            stderr = process.stderr
            if stdout is None or stderr is None:
                yield AgentRunUpdate(kind="failed", message="Cursor Agent pipes are not available.")
                return

            session_announced = False
            while True:
                if self._consume_cancelled(task.id):
                    return
                if process.poll() is not None and not _has_ready_stream(stdout, stderr):
                    break
                remaining = max(0.0, deadline - monotonic())
                if remaining == 0.0:
                    process.kill()
                    yield AgentRunUpdate(
                        kind="failed",
                        message=f"Cursor Agent timed out after {self._timeout_seconds} seconds.",
                        backend_session_id=backend_session_id,
                    )
                    return
                ready, _, _ = select.select([stdout, stderr], [], [], min(0.25, remaining))
                if not ready:
                    continue
                for stream in ready:
                    line = stream.readline()
                    if not line:
                        continue
                    if stream is stderr:
                        stderr_lines.append(line)
                        continue
                    event = _parse_json_event(line)
                    if event is None:
                        continue
                    extracted_session_id = _extract_cursor_session_id(event)
                    if extracted_session_id:
                        backend_session_id = extracted_session_id
                        if not session_announced:
                            session_announced = True
                            yield AgentRunUpdate(
                                kind="progress",
                                message="Cursor Agent session ready.",
                                backend_session_id=backend_session_id,
                            )
                    output_chunk, live_text = _extract_cursor_output_chunk(event, current_live_text=live_text)
                    if output_chunk:
                        yield AgentRunUpdate(
                            kind="progress",
                            message="Cursor Agent output updated.",
                            output_chunk=output_chunk,
                            backend_session_id=backend_session_id,
                        )
                    extracted_final_text = _extract_cursor_final_text(event)
                    if extracted_final_text:
                        final_text = extracted_final_text

            if self._consume_cancelled(task.id):
                return
            if process.returncode and process.returncode != 0:
                yield AgentRunUpdate(
                    kind="failed",
                    message="".join(stderr_lines).strip() or "Cursor Agent exited with a non-zero status.",
                    backend_session_id=backend_session_id,
                )
                return
            raw_result = final_text or live_text.strip() or "Cursor Agent completed without a final response body."
            yield AgentRunUpdate(
                kind="completed",
                message="Task completed by the cursor_agent runner.",
                raw_result=raw_result,
                backend_session_id=backend_session_id,
            )
        except OSError as exc:
            yield AgentRunUpdate(
                kind="failed",
                message=f"Failed to start Cursor Agent CLI: {exc}",
                backend_session_id=backend_session_id,
            )
        finally:
            with self._lock:
                self._active_processes.pop(task.id, None)
                self._cancelled_tasks.discard(task.id)
            _cleanup_subprocess(process)

    def _consume_cancelled(self, task_id: str) -> bool:
        with self._lock:
            if task_id not in self._cancelled_tasks:
                return False
            self._cancelled_tasks.discard(task_id)
            return True


class CocoRunner:
    name = "coco"

    def __init__(
        self,
        *,
        command: str = "traecli",
        workdir: str,
        model: str | None = None,
        approval_mode: str = "default",
        timeout_seconds: int = 900,
    ) -> None:
        self._command = command
        self._workdir = workdir
        self._model = model
        self._approval_mode = approval_mode
        self._timeout_seconds = timeout_seconds
        self._lock = RLock()
        self._active_processes: dict[str, subprocess.Popen[str]] = {}
        self._cancelled_tasks: set[str] = set()

    def is_ready(self) -> tuple[bool, str]:
        executable = shutil.which(self._command)
        if not executable:
            return False, f"Trae CLI not found: {self._command}"
        if not Path(self._workdir).exists():
            return False, f"Trae CLI workdir does not exist: {self._workdir}"
        return True, f"Trae CLI ready via {executable}"

    def start(self, task: Task) -> Iterator[AgentRunUpdate]:
        yield AgentRunUpdate(
            kind="progress",
            message=f"Task accepted by the {self.name} runner.",
        )
        if _requires_confirmation(task.prompt):
            yield AgentRunUpdate(
                kind="confirmation_required",
                message="Awaiting explicit approval before invoking Trae CLI.",
            )
            return
        yield from self._execute_prompt(task, _normalized_prompt(task.prompt))

    def resume_after_confirmation(self, task: Task) -> Iterator[AgentRunUpdate]:
        yield AgentRunUpdate(
            kind="progress",
            message="Approval received. Invoking Trae CLI.",
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

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        return (
            task.effective_model or self._model,
            task.effective_workdir or self._workdir,
            task.effective_sandbox,
        )

    def _execute_prompt(self, task: Task, prompt: str) -> Iterator[AgentRunUpdate]:
        executable = shutil.which(self._command)
        if not executable:
            yield AgentRunUpdate(kind="failed", message=f"Trae CLI not found: {self._command}")
            return

        workdir = task.effective_workdir or self._workdir
        if not Path(workdir).exists():
            yield AgentRunUpdate(kind="failed", message=f"Trae CLI workdir does not exist: {workdir}")
            return

        resolved_approval_mode = _string_or_none(task.effective_backend_config.get("approval_mode")) or self._approval_mode
        mode_id = "bypass_permissions" if resolved_approval_mode == "yolo" else "default"

        process: subprocess.Popen[str] | None = None
        backend_session_id = task.backend_session_id
        try:
            process = subprocess.Popen(
                [self._command, "acp", "serve"],
                cwd=workdir,
                env=os.environ.copy(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            with self._lock:
                self._active_processes[task.id] = process
            session = _TraeAcpClient(
                process=process,
            )
            session.initialize()
            session_result = session.open_session(
                session_id=task.backend_session_id,
                cwd=workdir,
            )
            backend_session_id = _extract_coco_acp_session_id(session_result) or task.backend_session_id
            if backend_session_id:
                yield AgentRunUpdate(
                    kind="progress",
                    message="Trae CLI session ready.",
                    backend_session_id=backend_session_id,
                )
            if backend_session_id and mode_id:
                session.set_mode(
                    session_id=backend_session_id,
                    mode_id=mode_id,
                )
            resolved_model = task.effective_model or self._model
            if backend_session_id and resolved_model:
                session.set_model(
                    session_id=backend_session_id,
                    model_id=resolved_model,
                )

            seen_message_ids: set[str] = set()
            for pending in session.drain_pending_notifications():
                params = pending.get("params")
                if not isinstance(params, dict):
                    continue
                if _optional_string(params.get("sessionId")) != backend_session_id:
                    continue
                update = params.get("update")
                if not isinstance(update, dict):
                    continue
                message_id = _extract_coco_acp_message_id(update)
                if message_id:
                    seen_message_ids.add(message_id)

            prompt_request_id = session.start_prompt(
                session_id=backend_session_id,
                prompt=prompt,
            )
            turn_state = _TraePromptTurnState(
                session_id=backend_session_id,
                prompt_request_id=prompt_request_id,
            )
            prompt_stream = _TraeAcpPromptStream(
                client=session,
                state=turn_state,
                ignored_message_ids=seen_message_ids,
            )
            for event in prompt_stream:
                if self._consume_cancelled(task.id):
                    return
                if event.kind == "output":
                    yield AgentRunUpdate(
                        kind="progress",
                        message=event.message,
                        output_chunk=event.output_chunk,
                        backend_session_id=backend_session_id,
                    )
                    continue
                if event.kind == "completed":
                    yield AgentRunUpdate(
                        kind="completed",
                        message=event.message,
                        raw_result=event.raw_result,
                        backend_session_id=backend_session_id,
                    )
                    return
                if event.kind == "cancelled":
                    return
                yield AgentRunUpdate(
                    kind="failed",
                    message=event.message,
                    backend_session_id=backend_session_id,
                )
                return
        except OSError as exc:
            yield AgentRunUpdate(
                kind="failed",
                message=f"Failed to start Trae CLI: {exc}",
                backend_session_id=backend_session_id,
            )
        finally:
            with self._lock:
                self._active_processes.pop(task.id, None)
                self._cancelled_tasks.discard(task.id)
            _cleanup_subprocess(process)

    def _consume_cancelled(self, task_id: str) -> bool:
        with self._lock:
            if task_id not in self._cancelled_tasks:
                return False
            self._cancelled_tasks.discard(task_id)
            return True


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


def create_agent_runner(
    *,
    backend: str,
    codex_command: str,
    codex_workdir: str,
    codex_model: str | None,
    codex_sandbox: str,
    codex_approval_policy: str,
    codex_timeout_seconds: int,
    claude_command: str,
    claude_workdir: str,
    claude_model: str | None,
    claude_permission_mode: str,
    claude_timeout_seconds: int,
    cursor_command: str,
    cursor_workdir: str,
    cursor_model: str | None,
    cursor_mode: str,
    cursor_sandbox: str,
    cursor_timeout_seconds: int,
    coco_command: str,
    coco_workdir: str,
    coco_model: str | None,
    coco_approval_mode: str,
    coco_timeout_seconds: int,
) -> AgentRunner:
    normalized = backend.strip().lower() or "codex"
    runners: dict[str, AgentRunner] = {
        "codex": CodexAppServerRunner(
            command=codex_command,
            workdir=codex_workdir,
            model=codex_model,
            sandbox=codex_sandbox,
            approval_policy=codex_approval_policy,
            timeout_seconds=codex_timeout_seconds,
        ),
        "claude_code": ClaudeCodeRunner(
            command=claude_command,
            workdir=claude_workdir,
            model=claude_model,
            permission_mode=claude_permission_mode,
            timeout_seconds=claude_timeout_seconds,
        ),
        "cursor_agent": CursorAgentRunner(
            command=cursor_command,
            workdir=cursor_workdir,
            model=cursor_model,
            mode=cursor_mode,
            sandbox=cursor_sandbox,
            timeout_seconds=cursor_timeout_seconds,
        ),
        "coco": CocoRunner(
            command=coco_command,
            workdir=coco_workdir,
            model=coco_model,
            approval_mode=coco_approval_mode,
            timeout_seconds=coco_timeout_seconds,
        ),
        "stub": StubAgentRunner(),
    }
    if normalized not in runners:
        return UnavailableAgentRunner(
            name=normalized or "unknown",
            reason=(
                f"Unsupported agent backend: {backend}. "
                "Current implemented backends are 'codex', 'claude_code', 'cursor_agent', 'coco', and 'stub'."
            ),
        )
    return MultiAgentRunner(
        default_backend=normalized,
        runners=runners,
    )


def _requires_confirmation(prompt: str) -> bool:
    return prompt.lower().startswith("confirm:")


def _normalized_prompt(prompt: str) -> str:
    if _requires_confirmation(prompt):
        return prompt.split(":", 1)[1].strip()
    return prompt.strip()


def _parse_json_event(line: str) -> dict[str, object] | None:
    text = line.strip()
    if not text or not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _first_non_empty(*candidates: str) -> str:
    for candidate in candidates:
        text = candidate.strip()
        if text:
            return text
    return ""


def _has_ready_stream(stdout, stderr) -> bool:  # type: ignore[no-untyped-def]
    ready, _, _ = select.select([stdout, stderr], [], [], 0)
    return bool(ready)


def _extract_claude_message_text(message: dict[str, object]) -> str | None:
    content = message.get("content")
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = _optional_string(item.get("text"))
        if text:
            parts.append(text)
    if not parts:
        return None
    return "".join(parts)


def _extract_cursor_session_id(event: dict[str, object]) -> str | None:
    for key in ("chatId", "sessionId", "session_id", "conversationId", "conversation_id"):
        value = _optional_string(event.get(key))
        if value:
            return value
    result = event.get("result")
    if isinstance(result, dict):
        for key in ("chatId", "sessionId", "session_id", "conversationId", "conversation_id"):
            value = _optional_string(result.get(key))
            if value:
                return value
    return None


def _extract_cursor_output_chunk(
    event: dict[str, object],
    *,
    current_live_text: str,
) -> tuple[str | None, str]:
    text_delta = _string_or_none(event.get("textDelta"))
    if text_delta is not None:
        return text_delta, current_live_text + text_delta
    partial_message = _string_or_none(event.get("partialMessage"))
    if partial_message is not None:
        if partial_message.startswith(current_live_text):
            return partial_message[len(current_live_text):] or None, partial_message
        return partial_message, partial_message
    result = event.get("result")
    if isinstance(result, dict):
        text_delta = _string_or_none(result.get("textDelta"))
        if text_delta is not None:
            return text_delta, current_live_text + text_delta
        partial_message = _string_or_none(result.get("partialMessage"))
        if partial_message is not None:
            if partial_message.startswith(current_live_text):
                return partial_message[len(current_live_text):] or None, partial_message
            return partial_message, partial_message
    return None, current_live_text


def _extract_cursor_final_text(event: dict[str, object]) -> str | None:
    result = event.get("result")
    if isinstance(result, str):
        return _optional_string(result)
    if isinstance(result, dict):
        for key in ("text", "message", "content", "finalMessage"):
            value = _optional_string(result.get(key))
            if value:
                return value
    assistant = event.get("assistant")
    if isinstance(assistant, dict):
        for key in ("text", "message", "content"):
            value = _optional_string(assistant.get(key))
            if value:
                return value
    for key in ("message", "content", "text"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_coco_acp_session_id(payload: dict[str, object]) -> str | None:
    return _optional_string(payload.get("sessionId"))


def _extract_coco_acp_output_chunk(
    update: dict[str, object],
    *,
    current_live_text: str,
    current_chunk_id: str | None,
) -> tuple[str | None, str, str | None]:
    session_update = _optional_string(update.get("sessionUpdate"))
    if session_update != "agent_message_chunk":
        return None, current_live_text, current_chunk_id
    meta = update.get("_meta")
    message_id = None
    message_type = None
    if isinstance(meta, dict):
        message_id = _optional_string(meta.get("id"))
        message_type = _optional_string(meta.get("type"))
    if message_type == "partial":
        content = update.get("content")
        if not isinstance(content, dict):
            return None, current_live_text, current_chunk_id
        text = _optional_string(content.get("text"))
        if not text:
            return None, current_live_text, current_chunk_id
        return text, current_live_text + text, current_chunk_id
    if message_id and message_id != current_chunk_id:
        current_live_text = ""
        current_chunk_id = message_id
    content = update.get("content")
    if not isinstance(content, dict):
        return None, current_live_text, current_chunk_id
    text = _optional_string(content.get("text"))
    if not text:
        return None, current_live_text, current_chunk_id
    if text.startswith(current_live_text):
        delta = text[len(current_live_text):] or None
        return delta, text, current_chunk_id
    return text, text, current_chunk_id


def _extract_coco_acp_message_id(update: dict[str, object]) -> str | None:
    if _optional_string(update.get("sessionUpdate")) != "agent_message_chunk":
        return None
    meta = update.get("_meta")
    if not isinstance(meta, dict):
        return None
    return _optional_string(meta.get("id"))


def _extract_coco_acp_stop_reason(update: dict[str, object]) -> str | None:
    if _optional_string(update.get("sessionUpdate")) != "usage_update":
        return None
    return _optional_string(update.get("stopReason"))


class _CodexAppServerSession:
    def __init__(
        self,
        *,
        process: subprocess.Popen[str],
        timeout_seconds: int,
    ) -> None:
        self._process = process
        self._timeout_seconds = timeout_seconds
        self._next_request_id = 1
        self._pending_notifications: deque[dict[str, object]] = deque()
        self._stderr_lines: list[str] = []

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "poco",
                    "version": "0.1",
                },
                "capabilities": {},
            },
        )

    def request(self, method: str, params: dict[str, object]) -> dict[str, object]:
        request_id = self._next_request_id
        self._next_request_id += 1
        payload = {
            "id": request_id,
            "method": method,
            "params": params,
        }
        self._write(payload)
        deadline = monotonic() + self._timeout_seconds
        while True:
            message = self._read_message(deadline=deadline)
            if message is None:
                raise RuntimeError(self.failure_detail(f"Timed out waiting for {method} response."))
            if message.get("id") == request_id:
                error = message.get("error")
                if isinstance(error, dict):
                    raise RuntimeError(_jsonrpc_error_message(error) or f"{method} failed.")
                result = message.get("result")
                return result if isinstance(result, dict) else {}
            if "method" in message:
                self._pending_notifications.append(message)

    def read_next_message(self) -> dict[str, object] | None:
        if self._pending_notifications:
            return self._pending_notifications.popleft()
        return self._read_message(deadline=monotonic() + self._timeout_seconds)

    def failure_detail(self, default: str) -> str:
        stderr = "".join(self._stderr_lines).strip()
        if stderr:
            return stderr
        return default

    def _write(self, payload: dict[str, object]) -> None:
        if self._process.stdin is None:
            raise RuntimeError("Codex app-server stdin is not available.")
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()

    def _read_message(self, *, deadline: float) -> dict[str, object] | None:
        stdout = self._process.stdout
        stderr = self._process.stderr
        if stdout is None or stderr is None:
            raise RuntimeError("Codex app-server pipes are not available.")
        while True:
            if self._process.poll() is not None and not self._has_ready_stream(stdout, stderr):
                return None
            remaining = max(0.0, deadline - monotonic())
            if remaining == 0.0:
                return None
            ready, _, _ = select.select([stdout, stderr], [], [], min(0.25, remaining))
            if not ready:
                continue
            for stream in ready:
                line = stream.readline()
                if not line:
                    continue
                if stream is stderr:
                    self._stderr_lines.append(line)
                    continue
                parsed = _parse_json_event(line)
                if parsed is None:
                    continue
                return parsed

    def _has_ready_stream(self, stdout, stderr) -> bool:  # type: ignore[no-untyped-def]
        return _has_ready_stream(stdout, stderr)


class _TraeAcpClient:
    def __init__(
        self,
        *,
        process: subprocess.Popen[str],
    ) -> None:
        self._process = process
        self._next_request_id = 1
        self._pending_notifications: deque[dict[str, object]] = deque()
        self._stderr_lines: list[str] = []

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "poco",
                    "version": "0.1",
                },
                "capabilities": {},
            },
        )

    def open_session(
        self,
        *,
        session_id: str | None,
        cwd: str,
    ) -> dict[str, object]:
        if session_id:
            return self.request(
                "session/load",
                {
                    "sessionId": session_id,
                    "cwd": cwd,
                    "mcpServers": [],
                },
            )
        return self.request(
            "session/new",
            {
                "cwd": cwd,
                "mcpServers": [],
            },
        )

    def set_mode(self, *, session_id: str, mode_id: str) -> None:
        self.request(
            "session/set_mode",
            {
                "sessionId": session_id,
                "modeId": mode_id,
            },
        )

    def set_model(self, *, session_id: str, model_id: str) -> None:
        self.request(
            "session/set_model",
            {
                "sessionId": session_id,
                "modelId": model_id,
            },
        )

    def start_prompt(self, *, session_id: str, prompt: str) -> int:
        return self.send_request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": prompt}],
            },
        )

    def drain_pending_notifications(self) -> list[dict[str, object]]:
        drained = list(self._pending_notifications)
        self._pending_notifications.clear()
        return drained

    def request(self, method: str, params: dict[str, object]) -> dict[str, object]:
        request_id = self.send_request(method, params)
        while True:
            message = self.read_next_message()
            if message is None:
                raise RuntimeError(self.failure_detail(f"ACP server closed while waiting for {method}."))
            if message.get("id") == request_id:
                error = message.get("error")
                if isinstance(error, dict):
                    raise RuntimeError(_jsonrpc_error_message(error) or f"{method} failed.")
                result = message.get("result")
                return result if isinstance(result, dict) else {}
            if "method" in message:
                self._pending_notifications.append(message)

    def send_request(self, method: str, params: dict[str, object]) -> int:
        request_id = self._next_request_id
        self._next_request_id += 1
        self._write(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        return request_id

    def read_next_message(self) -> dict[str, object] | None:
        if self._pending_notifications:
            return self._pending_notifications.popleft()
        return self._read_message()

    def failure_detail(self, default: str) -> str:
        stderr = "".join(self._stderr_lines).strip()
        if stderr:
            return stderr
        return default

    def _write(self, payload: dict[str, object]) -> None:
        if self._process.stdin is None:
            raise RuntimeError("Trae CLI ACP stdin is not available.")
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()

    def _read_message(self) -> dict[str, object] | None:
        stdout = self._process.stdout
        stderr = self._process.stderr
        if stdout is None or stderr is None:
            raise RuntimeError("Trae CLI ACP pipes are not available.")
        while True:
            if self._process.poll() is not None and not _has_ready_stream(stdout, stderr):
                return None
            ready, _, _ = select.select([stdout, stderr], [], [], 0.25)
            if not ready:
                continue
            for stream in ready:
                line = stream.readline()
                if not line:
                    continue
                if stream is stderr:
                    self._stderr_lines.append(line)
                    continue
                parsed = _parse_json_event(line)
                if parsed is None:
                    continue
                return parsed


class _TraeAcpPromptStream:
    def __init__(
        self,
        *,
        client: _TraeAcpClient,
        state: _TraePromptTurnState,
        ignored_message_ids: set[str] | None = None,
    ) -> None:
        self._client = client
        self._state = state
        if ignored_message_ids:
            self._state.ignored_message_ids.update(ignored_message_ids)

    def __iter__(self) -> Iterator[_TraePromptEvent]:
        while True:
            message = self._client.read_next_message()
            if message is None:
                yield _TraePromptEvent(
                    kind="failed",
                    message=self._client.failure_detail("Trae CLI ACP server closed before task completion."),
                )
                return
            event = self._translate_message(message)
            if event is None:
                continue
            yield event
            if event.kind != "output":
                return

    def _translate_message(self, message: dict[str, object]) -> _TraePromptEvent | None:
        if message.get("id") == self._state.prompt_request_id:
            error = message.get("error")
            if isinstance(error, dict):
                return _TraePromptEvent(
                    kind="failed",
                    message=_jsonrpc_error_message(error) or "Trae CLI prompt failed.",
                )
            result = message.get("result")
            if isinstance(result, dict):
                stop_reason = _optional_string(result.get("stopReason"))
                if stop_reason == "cancelled":
                    return _TraePromptEvent(kind="cancelled", message="Trae CLI prompt cancelled.")
            return _TraePromptEvent(
                kind="completed",
                message="Task completed by the coco runner.",
                raw_result=self._state.live_text.strip() or "Trae CLI completed without a final response body.",
            )

        if message.get("method") != "session/update":
            return None
        params = message.get("params")
        if not isinstance(params, dict):
            return None
        if _optional_string(params.get("sessionId")) != self._state.session_id:
            return None
        update = params.get("update")
        if not isinstance(update, dict):
            return None

        stop_reason = _extract_coco_acp_stop_reason(update)
        if stop_reason:
            if stop_reason == "cancelled":
                return _TraePromptEvent(kind="cancelled", message="Trae CLI prompt cancelled.")
            return _TraePromptEvent(
                kind="completed",
                message="Task completed by the coco runner.",
                raw_result=self._state.live_text.strip() or "Trae CLI completed without a final response body.",
            )

        message_id = _extract_coco_acp_message_id(update)
        if self._state.should_ignore_message(message_id):
            return None

        output_chunk, self._state.live_text, self._state.current_chunk_id = _extract_coco_acp_output_chunk(
            update,
            current_live_text=self._state.live_text,
            current_chunk_id=self._state.current_chunk_id,
        )
        self._state.record_message_id(self._state.current_chunk_id)
        if not output_chunk:
            return None
        return _TraePromptEvent(
            kind="output",
            message="Trae CLI output updated.",
            output_chunk=output_chunk,
        )


def _extract_thread_id(result: dict[str, object]) -> str | None:
    thread = result.get("thread")
    if not isinstance(thread, dict):
        return None
    return _optional_string(thread.get("id"))


def _turn_error_message(turn: dict[str, object]) -> str | None:
    error = turn.get("error")
    if isinstance(error, dict):
        message = _optional_string(error.get("message"))
        if message:
            return message
    return None


def _error_notification_message(params: dict[str, object]) -> str | None:
    message = _optional_string(params.get("message"))
    if message:
        return message
    error = params.get("error")
    if isinstance(error, dict):
        return _jsonrpc_error_message(error)
    return None


def _jsonrpc_error_message(error: dict[str, object]) -> str | None:
    message = _optional_string(error.get("message"))
    if message:
        return message
    data = error.get("data")
    if isinstance(data, str):
        text = data.strip()
        if text:
            return text
    if isinstance(data, dict):
        nested = _optional_string(data.get("message"))
        if nested:
            return nested
    return None
