from __future__ import annotations

from collections.abc import Iterator
import logging
import os
import select
import shutil
import subprocess
from pathlib import Path
from threading import RLock
from time import monotonic

from poco.agent.common import (
    AgentRunUpdate,
    _cleanup_subprocess,
    _compact_json,
    _has_ready_stream,
    _normalized_prompt,
    _optional_string,
    _parse_json_event,
    _requires_confirmation,
    _string_or_none,
)
from poco.agent.completion_gate import CompletionGate
from poco.task.models import Task

_LOGGER = logging.getLogger(__name__)


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
        completion_settle_seconds: float = 1.0,
    ) -> None:
        self._command = command
        self._workdir = workdir
        self._model = model
        self._mode = mode
        self._sandbox = sandbox
        self._timeout_seconds = timeout_seconds
        self._completion_settle_seconds = max(0.0, completion_settle_seconds)
        self._logger = _LOGGER
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

    def steer(self, task: Task, prompt: str) -> tuple[bool, str]:
        return False, f"Steer is not supported by the {self.name} runner."

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        return (
            task.effective_model or self._model,
            task.effective_workdir or self._workdir,
            _string_or_none(task.effective_backend_config.get("sandbox")) or self._sandbox,
        )

    def is_task_active(self, task: Task) -> bool | None:
        with self._lock:
            process = self._active_processes.get(task.id)
        if process is None:
            return False
        return process.poll() is None

    def _execute_prompt(self, task: Task, prompt: str) -> Iterator[AgentRunUpdate]:
        executable = shutil.which(self._command)
        if not executable:
            yield AgentRunUpdate(kind="failed", message=f"Cursor Agent CLI not found: {self._command}")
            return

        workdir = task.effective_workdir or self._workdir
        if not Path(workdir).exists():
            yield AgentRunUpdate(kind="failed", message=f"Cursor Agent workdir does not exist: {workdir}")
            return

        resolved_model = _normalize_cursor_model(task.effective_model or self._model)
        resolved_mode = _string_or_none(task.effective_backend_config.get("mode")) or self._mode
        resolved_sandbox = _normalize_cursor_sandbox(
            _string_or_none(task.effective_backend_config.get("sandbox")) or self._sandbox
        )
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
            self._logger.info(
                "Starting cursor-agent task %s: model=%s mode=%s sandbox=%s workdir=%s resume=%s",
                task.id,
                resolved_model or "<default>",
                resolved_mode or "<default>",
                resolved_sandbox or "<default>",
                workdir,
                bool(task.backend_session_id),
            )
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
            completion_gate = CompletionGate(settle_seconds=self._completion_settle_seconds)
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
                should_fire, settle_elapsed = completion_gate.tick(monotonic())
                if should_fire:
                    raw_result = final_text or live_text or "Cursor Agent completed without a final response body."
                    self._logger.info(
                        "cursor-agent task %s completed via settle fallback after %.2fs (no result event observed)",
                        task.id,
                        settle_elapsed,
                    )
                    yield AgentRunUpdate(
                        kind="completed",
                        message="Task completed by the cursor_agent runner after the final assistant message settled.",
                        raw_result=raw_result,
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
                        stderr_line = line.strip()
                        if stderr_line:
                            self._logger.warning(
                                "cursor-agent stderr for task %s: %s",
                                task.id,
                                stderr_line,
                            )
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
                        completion_gate.disarm()
                        yield AgentRunUpdate(
                            kind="progress",
                            message="Cursor Agent output updated.",
                            output_chunk=output_chunk,
                            backend_session_id=backend_session_id,
                        )
                    extracted_final_text = _extract_cursor_final_text(event)
                    if extracted_final_text:
                        final_text = extracted_final_text
                    if (
                        output_chunk is None
                        and extracted_final_text
                        and live_text
                        and _optional_string(event.get("type")) != "result"
                    ):
                        if completion_gate.arm(monotonic()):
                            self._logger.info(
                                "cursor-agent task %s armed completion settle candidate (summary assistant event)",
                                task.id,
                            )
                    terminal_result = _extract_cursor_terminal_result(event)
                    if terminal_result is not None:
                        if terminal_result.get("is_error"):
                            detail = _extract_cursor_error_detail(terminal_result)
                            self._logger.warning(
                                "cursor-agent terminal error for task %s: %s event=%s",
                                task.id,
                                detail or "<no detail>",
                                _compact_json(terminal_result),
                            )
                            yield AgentRunUpdate(
                                kind="failed",
                                message=detail
                                or "".join(stderr_lines).strip()
                                or "Cursor Agent reported an error.",
                                backend_session_id=backend_session_id,
                            )
                            return
                        raw_result = final_text or live_text or "Cursor Agent completed without a final response body."
                        self._logger.info(
                            "cursor-agent task %s completed via terminal result: session=%s chars=%s",
                            task.id,
                            backend_session_id or "<none>",
                            len(raw_result),
                        )
                        yield AgentRunUpdate(
                            kind="completed",
                            message="Task completed by the cursor_agent runner.",
                            raw_result=raw_result,
                            backend_session_id=backend_session_id,
                        )
                        return

            if self._consume_cancelled(task.id):
                return
            if process.returncode and process.returncode != 0:
                self._logger.warning(
                    "cursor-agent task %s exited non-zero: returncode=%s stderr=%s",
                    task.id,
                    process.returncode,
                    "".join(stderr_lines).strip() or "<empty>",
                )
                yield AgentRunUpdate(
                    kind="failed",
                    message="".join(stderr_lines).strip() or "Cursor Agent exited with a non-zero status.",
                    backend_session_id=backend_session_id,
                )
                return
            raw_result = final_text or live_text or "Cursor Agent completed without a final response body."
            self._logger.info(
                "cursor-agent task %s completed after process exit: session=%s chars=%s",
                task.id,
                backend_session_id or "<none>",
                len(raw_result),
            )
            yield AgentRunUpdate(
                kind="completed",
                message="Task completed by the cursor_agent runner.",
                raw_result=raw_result,
                backend_session_id=backend_session_id,
            )
        except RuntimeError as exc:
            self._logger.warning("cursor-agent task %s runtime error: %s", task.id, exc)
            yield AgentRunUpdate(
                kind="failed",
                message=str(exc) or "Cursor Agent session failed.",
                backend_session_id=backend_session_id,
            )
        except OSError as exc:
            self._logger.warning("Failed to start cursor-agent task %s: %s", task.id, exc)
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


def _normalize_cursor_model(model: str | None) -> str | None:
    if model == "gpt-5":
        return "auto"
    return model


def _normalize_cursor_sandbox(sandbox: str | None) -> str | None:
    if sandbox in {None, "", "default"}:
        return sandbox
    if sandbox in {"enabled", "disabled"}:
        return sandbox
    if sandbox in {"read-only", "workspace-write"}:
        return "enabled"
    if sandbox == "danger-full-access":
        return "disabled"
    return sandbox


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
    if _optional_string(event.get("type")) == "assistant":
        message = event.get("message")
        if isinstance(message, dict):
            full_text = _extract_message_text_preserving_whitespace(message)
            if full_text is None:
                return None, current_live_text
            if full_text.startswith(current_live_text):
                delta = full_text[len(current_live_text):] or None
                return delta, full_text
            if current_live_text and full_text in current_live_text:
                return None, current_live_text
            return full_text, current_live_text + full_text
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
    message = event.get("message")
    if isinstance(message, dict):
        extracted = _extract_message_text_preserving_whitespace(message)
        if extracted:
            return extracted
    for key in ("message", "content", "text"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_cursor_terminal_result(event: dict[str, object]) -> dict[str, object] | None:
    if _optional_string(event.get("type")) != "result":
        return None
    return event


def _extract_cursor_error_detail(event: dict[str, object]) -> str | None:
    result = event.get("result")
    if isinstance(result, str):
        return _optional_string(result)
    if isinstance(result, dict):
        for key in ("error", "message", "content", "text", "finalMessage"):
            value = _optional_string(result.get(key))
            if value:
                return value
    error = event.get("error")
    if isinstance(error, dict):
        for key in ("message", "content", "text", "details"):
            value = _optional_string(error.get(key))
            if value:
                return value
    if isinstance(error, str):
        return _optional_string(error)
    for key in ("message", "content", "text"):
        value = _optional_string(event.get(key))
        if value:
            return value
    return None


def _extract_message_text_preserving_whitespace(message: dict[str, object]) -> str | None:
    content = message.get("content")
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = _string_or_none(item.get("text"))
        if text is not None:
            parts.append(text)
    if not parts:
        return None
    return "".join(parts)
