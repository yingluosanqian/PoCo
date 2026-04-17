from __future__ import annotations

from collections.abc import Iterator
import json
import logging
import os
import select
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, RLock
from time import monotonic

from poco.agent.common import (
    AgentRunUpdate,
    _cleanup_subprocess,
    _has_ready_stream,
    _normalized_prompt,
    _optional_string,
    _parse_json_event,
    _requires_confirmation,
    _string_or_none,
)
from poco.agent.completion_gate import CompletionGate
from poco.agent.tokens import TokenUsage
from poco.task.models import Task

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _ClaudePendingControl:
    event: Event = field(default_factory=Event)
    response: dict[str, object] | None = None
    error: str | None = None


@dataclass(slots=True)
class _ClaudeActiveSession:
    process: subprocess.Popen[str]
    stdin: object
    session_id: str | None = None
    io_lock: RLock = field(default_factory=RLock)
    pending_controls: dict[str, _ClaudePendingControl] = field(default_factory=dict)
    next_request_id: int = 0
    ignored_result_count: int = 0


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
        completion_settle_seconds: float = 1.0,
    ) -> None:
        self._command = command
        self._workdir = workdir
        self._model = model
        self._permission_mode = permission_mode
        self._timeout_seconds = timeout_seconds
        self._completion_settle_seconds = max(0.0, completion_settle_seconds)
        self._lock = RLock()
        self._active_processes: dict[str, subprocess.Popen[str]] = {}
        self._active_sessions: dict[str, _ClaudeActiveSession] = {}
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

    def steer(self, task: Task, prompt: str) -> tuple[bool, str]:
        instruction = prompt.strip()
        if not instruction:
            return False, "Steer prompt cannot be empty."
        with self._lock:
            active = self._active_sessions.get(task.id)
        if active is None:
            return False, "Claude Code steer is only available while the task is actively running."
        try:
            self._send_claude_control_request(active, {"subtype": "interrupt"})
            with active.io_lock:
                active.ignored_result_count += 1
            self._send_claude_user_message(
                active,
                instruction,
                session_id=active.session_id or task.backend_session_id or "default",
            )
        except RuntimeError as exc:
            return False, str(exc) or "Claude Code steer failed."
        return True, "Steer sent to Claude Code."

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        permission_mode = _string_or_none(task.effective_backend_config.get("permission_mode"))
        return (
            task.effective_model or self._model,
            task.effective_workdir or self._workdir,
            permission_mode or self._permission_mode,
        )

    def is_task_active(self, task: Task) -> bool | None:
        with self._lock:
            process = self._active_processes.get(task.id)
            active = self._active_sessions.get(task.id)
        if process is None and active is None:
            return False
        if process is not None and process.poll() is None:
            return True
        return active is not None

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
            "--verbose",
            "--output-format=stream-json",
            "--include-partial-messages",
            "--input-format",
            "stream-json",
        ]
        if resolved_model:
            command.extend(["--model", resolved_model])
        if resolved_permission_mode:
            command.extend(["--permission-mode", resolved_permission_mode])
        if task.backend_session_id:
            command.extend(["--resume", task.backend_session_id])
        env = os.environ.copy()
        if resolved_permission_mode == "bypassPermissions":
            env["IS_SANDBOX"] = "1"

        process: subprocess.Popen[str] | None = None
        backend_session_id = task.backend_session_id
        stderr_lines: list[str] = []
        final_text: str | None = None
        streamed_text = ""
        last_seen_usage: TokenUsage | None = None
        active_session: _ClaudeActiveSession | None = None
        try:
            process = subprocess.Popen(
                command,
                cwd=workdir,
                env=env,
                stdin=subprocess.PIPE,
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
            stdin = process.stdin
            if stdout is None or stderr is None or stdin is None:
                yield AgentRunUpdate(kind="failed", message="Claude Code pipes are not available.")
                return
            active_session = _ClaudeActiveSession(
                process=process,
                stdin=stdin,
                session_id=backend_session_id,
            )
            self._initialize_claude_session(
                active_session,
                stdout,
                stderr,
                stderr_lines,
                {"subtype": "initialize", "hooks": None},
                timeout=min(max(self._timeout_seconds, 60), 120),
            )
            self._send_claude_user_message(
                active_session,
                prompt,
                session_id=backend_session_id or "default",
            )
            with self._lock:
                self._active_sessions[task.id] = active_session

            completion_gate = CompletionGate(settle_seconds=self._completion_settle_seconds)
            main_stdout_eof = False
            main_stderr_eof = False
            while True:
                if self._consume_cancelled(task.id):
                    return
                if process.poll() is not None and main_stdout_eof and main_stderr_eof:
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
                should_fire, settle_elapsed = completion_gate.tick(monotonic())
                if should_fire:
                    _LOGGER.info(
                        "claude_code task %s completed via settle fallback after %.2fs (no result event observed)",
                        task.id,
                        settle_elapsed,
                    )
                    yield AgentRunUpdate(
                        kind="completed",
                        message="Task completed by the claude_code runner after the final assistant message settled.",
                        raw_result=streamed_text or final_text or "Claude Code completed without a final response body.",
                        backend_session_id=backend_session_id,
                        last_token_usage=last_seen_usage,
                    )
                    return
                ready, _, _ = select.select([stdout, stderr], [], [], min(0.25, remaining))
                if not ready:
                    continue
                for stream in ready:
                    line = stream.readline()
                    if not line:
                        if stream is stdout:
                            main_stdout_eof = True
                        else:
                            main_stderr_eof = True
                        continue
                    if stream is stderr:
                        stderr_lines.append(line)
                        continue
                    event = _parse_json_event(line)
                    if event is None:
                        continue
                    event_type = _optional_string(event.get("type")) or ""
                    if event_type == "control_response":
                        self._handle_claude_control_response(active_session, event)
                        continue
                    if event_type == "control_request":
                        self._reject_claude_control_request(active_session, event)
                        continue
                    if event_type == "system" and event.get("subtype") == "init":
                        backend_session_id = _optional_string(event.get("session_id")) or backend_session_id
                        active_session.session_id = backend_session_id
                        if backend_session_id:
                            yield AgentRunUpdate(
                                kind="progress",
                                message="Claude Code session ready.",
                                backend_session_id=backend_session_id,
                            )
                        continue
                    if event_type == "stream_event":
                        stream_event = event.get("event")
                        backend_session_id = _optional_string(event.get("session_id")) or backend_session_id
                        active_session.session_id = backend_session_id
                        if isinstance(stream_event, dict):
                            se_type = stream_event.get("type")
                            if se_type == "content_block_delta":
                                delta = stream_event.get("delta")
                                if isinstance(delta, dict) and delta.get("type") == "text_delta":
                                    text = _string_or_none(delta.get("text"))
                                    if text:
                                        completion_gate.disarm()
                                        streamed_text += text
                                        yield AgentRunUpdate(
                                            kind="progress",
                                            message="Claude Code output updated.",
                                            output_chunk=text,
                                            backend_session_id=backend_session_id,
                                        )
                            elif se_type == "content_block_start":
                                cb = stream_event.get("content_block")
                                if isinstance(cb, dict) and cb.get("type") == "tool_use":
                                    tool_name = _optional_string(cb.get("name")) or "tool"
                                    yield AgentRunUpdate(
                                        kind="progress",
                                        message=f"Claude Code is using {tool_name}.",
                                        backend_session_id=backend_session_id,
                                        activity_hint=tool_name,
                                    )
                        continue
                    if event_type == "assistant":
                        message = event.get("message")
                        stop_reason: str | None = None
                        if isinstance(message, dict):
                            final_text = _extract_claude_message_text(message) or final_text
                            stop_reason = _extract_claude_message_stop_reason(message)
                            turn_usage = _extract_claude_message_usage(message)
                            if turn_usage is not None and turn_usage != last_seen_usage:
                                last_seen_usage = turn_usage
                                yield AgentRunUpdate(
                                    kind="progress",
                                    message="Claude Code token usage updated.",
                                    backend_session_id=backend_session_id,
                                    last_token_usage=turn_usage,
                                )
                        backend_session_id = _optional_string(event.get("session_id")) or backend_session_id
                        active_session.session_id = backend_session_id
                        if stop_reason == "end_turn":
                            if completion_gate.arm(monotonic()):
                                _LOGGER.info(
                                    "claude_code task %s armed completion settle candidate (stop_reason=end_turn)",
                                    task.id,
                                )
                        elif stop_reason == "tool_use":
                            completion_gate.disarm()
                        else:
                            completion_gate.disarm()
                        continue
                    if event_type == "result":
                        backend_session_id = _optional_string(event.get("session_id")) or backend_session_id
                        active_session.session_id = backend_session_id
                        with active_session.io_lock:
                            ignored_result = active_session.ignored_result_count > 0
                            if ignored_result:
                                active_session.ignored_result_count -= 1
                        if ignored_result:
                            continue
                        if event.get("subtype") == "success":
                            raw_result = (
                                streamed_text
                                or _optional_string(event.get("result"))
                                or final_text
                                or "Claude Code completed without a final response body."
                            )
                            _LOGGER.info("claude_code task %s completed via result event", task.id)
                            yield AgentRunUpdate(
                                kind="completed",
                                message="Task completed by the claude_code runner.",
                                raw_result=raw_result,
                                backend_session_id=backend_session_id,
                                last_token_usage=last_seen_usage,
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
                raw_result=streamed_text or final_text or "Claude Code completed without a final response body.",
                backend_session_id=backend_session_id,
                last_token_usage=last_seen_usage,
            )
        except RuntimeError as exc:
            yield AgentRunUpdate(
                kind="failed",
                message=str(exc) or "Claude Code session failed.",
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
                self._active_sessions.pop(task.id, None)
                self._cancelled_tasks.discard(task.id)
            _cleanup_subprocess(process)

    def _consume_cancelled(self, task_id: str) -> bool:
        with self._lock:
            if task_id not in self._cancelled_tasks:
                return False
            self._cancelled_tasks.discard(task_id)
            return True

    def _send_claude_control_request(
        self,
        active: _ClaudeActiveSession,
        request: dict[str, object],
        *,
        timeout: float = 10.0,
    ) -> dict[str, object]:
        with active.io_lock:
            active.next_request_id += 1
            request_id = f"req_{active.next_request_id}_{os.urandom(4).hex()}"
            pending = _ClaudePendingControl()
            active.pending_controls[request_id] = pending
            self._write_claude_json_line(
                active,
                {
                    "type": "control_request",
                    "request_id": request_id,
                    "request": request,
                },
            )
        if not pending.event.wait(timeout):
            with active.io_lock:
                active.pending_controls.pop(request_id, None)
            raise RuntimeError(f"Claude Code control request timed out: {request.get('subtype')}")
        with active.io_lock:
            active.pending_controls.pop(request_id, None)
        if pending.error:
            raise RuntimeError(pending.error)
        return pending.response or {}

    def _initialize_claude_session(
        self,
        active: _ClaudeActiveSession,
        stdout,
        stderr,
        stderr_lines: list[str],
        request: dict[str, object],
        *,
        timeout: float,
    ) -> dict[str, object]:
        with active.io_lock:
            active.next_request_id += 1
            request_id = f"req_{active.next_request_id}_{os.urandom(4).hex()}"
            pending = _ClaudePendingControl()
            active.pending_controls[request_id] = pending
            self._write_claude_json_line(
                active,
                {
                    "type": "control_request",
                    "request_id": request_id,
                    "request": request,
                },
            )
        deadline = monotonic() + timeout
        stdout_eof = False
        stderr_eof = False
        while True:
            if pending.event.is_set():
                break
            remaining = max(0.0, deadline - monotonic())
            if remaining == 0.0:
                with active.io_lock:
                    active.pending_controls.pop(request_id, None)
                raise RuntimeError(f"Claude Code control request timed out: {request.get('subtype')}")
            if active.process.poll() is not None and stdout_eof and stderr_eof:
                with active.io_lock:
                    active.pending_controls.pop(request_id, None)
                stderr_text = "".join(stderr_lines).strip()
                raise RuntimeError(
                    stderr_text
                    or f"Claude Code exited during {request.get('subtype')} (exit code {active.process.returncode})."
                )
            ready, _, _ = select.select([stdout, stderr], [], [], min(0.25, remaining))
            if not ready:
                continue
            for stream in ready:
                line = stream.readline()
                if not line:
                    if stream is stdout:
                        stdout_eof = True
                    else:
                        stderr_eof = True
                    continue
                if stream is stderr:
                    stderr_lines.append(line)
                    continue
                event = _parse_json_event(line)
                if event is None:
                    continue
                event_type = _optional_string(event.get("type")) or ""
                if event_type == "control_response":
                    self._handle_claude_control_response(active, event)
                elif event_type == "control_request":
                    self._reject_claude_control_request(active, event)
        with active.io_lock:
            active.pending_controls.pop(request_id, None)
        if pending.error:
            raise RuntimeError(pending.error)
        return pending.response or {}

    def _send_claude_user_message(
        self,
        active: _ClaudeActiveSession,
        prompt: str,
        *,
        session_id: str,
    ) -> None:
        self._write_claude_json_line(
            active,
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": prompt,
                },
                "parent_tool_use_id": None,
                "session_id": session_id,
            },
        )

    def _write_claude_json_line(self, active: _ClaudeActiveSession, payload: dict[str, object]) -> None:
        with active.io_lock:
            stdin = active.stdin
            if not hasattr(stdin, "write"):
                raise RuntimeError("Claude Code stdin is not writable.")
            try:
                stdin.write(json.dumps(payload) + "\n")
                flush = getattr(stdin, "flush", None)
                if callable(flush):
                    flush()
            except Exception as exc:  # pragma: no cover - defensive for pipe edge cases
                raise RuntimeError(f"Failed to write to Claude Code CLI: {exc}") from exc

    def _handle_claude_control_response(
        self,
        active: _ClaudeActiveSession,
        event: dict[str, object],
    ) -> None:
        response = event.get("response")
        if not isinstance(response, dict):
            return
        request_id = _optional_string(response.get("request_id"))
        if not request_id:
            return
        with active.io_lock:
            pending = active.pending_controls.get(request_id)
        if pending is None:
            return
        if response.get("subtype") == "error":
            pending.error = _optional_string(response.get("error")) or "Claude Code control request failed."
        else:
            payload = response.get("response")
            pending.response = payload if isinstance(payload, dict) else {}
        pending.event.set()

    def _reject_claude_control_request(
        self,
        active: _ClaudeActiveSession,
        event: dict[str, object],
    ) -> None:
        request_id = _optional_string(event.get("request_id"))
        if not request_id:
            return
        self._write_claude_json_line(
            active,
            {
                "type": "control_response",
                "response": {
                    "subtype": "error",
                    "request_id": request_id,
                    "error": "PoCo does not support Claude Code control callbacks in streaming mode.",
                },
            },
        )


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


def _extract_claude_message_stop_reason(message: dict[str, object]) -> str | None:
    return _optional_string(message.get("stop_reason"))


def _extract_claude_message_usage(message: dict[str, object]) -> TokenUsage | None:
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    return TokenUsage.from_dict(usage)
