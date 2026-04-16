from __future__ import annotations

from collections import deque
from collections.abc import Iterator
import json
import os
import select
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Literal

from poco.agent.common import (
    AgentRunUpdate,
    _cleanup_subprocess,
    _has_ready_stream,
    _jsonrpc_error_message,
    _normalized_prompt,
    _optional_string,
    _parse_json_event,
    _requires_confirmation,
    _string_or_none,
)
from poco.task.models import Task

_TraePromptEventKind = Literal["output", "completed", "failed", "cancelled"]


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


@dataclass(slots=True)
class _TraeAcpTransport:
    workdir: str
    process: subprocess.Popen[str]
    client: "_TraeAcpClient"
    lock: RLock = field(default_factory=RLock)
    last_used_at: float = field(default_factory=monotonic)


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
        transport_idle_seconds: float = 30.0,
    ) -> None:
        self._command = command
        self._workdir = workdir
        self._model = model
        self._approval_mode = approval_mode
        self._timeout_seconds = timeout_seconds
        self._transport_idle_seconds = transport_idle_seconds
        self._lock = RLock()
        self._active_processes: dict[str, subprocess.Popen[str]] = {}
        self._cancelled_tasks: set[str] = set()
        self._transports: dict[str, _TraeAcpTransport] = {}

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

    def steer(self, task: Task, prompt: str) -> tuple[bool, str]:
        return False, f"Steer is not supported by the {self.name} runner."

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        return (
            task.effective_model or self._model,
            task.effective_workdir or self._workdir,
            task.effective_sandbox,
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
            yield AgentRunUpdate(kind="failed", message=f"Trae CLI not found: {self._command}")
            return

        workdir = task.effective_workdir or self._workdir
        if not Path(workdir).exists():
            yield AgentRunUpdate(kind="failed", message=f"Trae CLI workdir does not exist: {workdir}")
            return

        resolved_approval_mode = _string_or_none(task.effective_backend_config.get("approval_mode")) or self._approval_mode
        mode_id = "bypass_permissions" if resolved_approval_mode == "yolo" else "default"

        process: subprocess.Popen[str] | None = None
        transport: _TraeAcpTransport | None = None
        backend_session_id = task.backend_session_id
        transport_broken = False
        try:
            transport = self._acquire_transport(workdir)
            process = transport.process
            with self._lock:
                self._active_processes[task.id] = process
            session = transport.client
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
        except RuntimeError as exc:
            transport_broken = True
            yield AgentRunUpdate(
                kind="failed",
                message=str(exc) or "Trae CLI ACP request failed.",
                backend_session_id=backend_session_id,
            )
        except OSError as exc:
            transport_broken = True
            yield AgentRunUpdate(
                kind="failed",
                message=f"Failed to start Trae CLI: {exc}",
                backend_session_id=backend_session_id,
            )
        finally:
            with self._lock:
                self._active_processes.pop(task.id, None)
                self._cancelled_tasks.discard(task.id)
            self._release_transport(transport, broken=transport_broken)

    def _consume_cancelled(self, task_id: str) -> bool:
        with self._lock:
            if task_id not in self._cancelled_tasks:
                return False
            self._cancelled_tasks.discard(task_id)
            return True

    def _acquire_transport(self, workdir: str) -> _TraeAcpTransport:
        with self._lock:
            cleanup_candidates = self._collect_idle_transports_locked(exclude_workdir=workdir)
            transport = self._transports.get(workdir)
            if transport is not None and transport.process.poll() is not None:
                self._transports.pop(workdir, None)
                cleanup_candidates.append(transport.process)
                transport = None
            if transport is None:
                transport = self._start_transport(workdir)
                self._transports[workdir] = transport
        for candidate in cleanup_candidates:
            _cleanup_subprocess(candidate)
        transport.lock.acquire()
        with self._lock:
            transport.last_used_at = monotonic()
        return transport

    def _release_transport(self, transport: _TraeAcpTransport | None, *, broken: bool) -> None:
        if transport is None:
            return
        cleanup: subprocess.Popen[str] | None = None
        with self._lock:
            transport.last_used_at = monotonic()
            if broken or transport.process.poll() is not None:
                if self._transports.get(transport.workdir) is transport:
                    self._transports.pop(transport.workdir, None)
                cleanup = transport.process
            transport.lock.release()
        if cleanup is not None:
            _cleanup_subprocess(cleanup)

    def _start_transport(self, workdir: str) -> _TraeAcpTransport:
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
        try:
            client = _TraeAcpClient(process=process)
            client.initialize()
            return _TraeAcpTransport(
                workdir=workdir,
                process=process,
                client=client,
            )
        except Exception:
            _cleanup_subprocess(process)
            raise

    def _collect_idle_transports_locked(self, *, exclude_workdir: str | None = None) -> list[subprocess.Popen[str]]:
        if self._transport_idle_seconds <= 0:
            return []
        now = monotonic()
        stale_workdirs: list[str] = []
        cleanup: list[subprocess.Popen[str]] = []
        for workdir, transport in self._transports.items():
            if exclude_workdir is not None and workdir == exclude_workdir:
                continue
            if transport.process.poll() is not None:
                stale_workdirs.append(workdir)
                cleanup.append(transport.process)
                continue
            if now - transport.last_used_at < self._transport_idle_seconds:
                continue
            if not transport.lock.acquire(blocking=False):
                continue
            transport.lock.release()
            stale_workdirs.append(workdir)
            cleanup.append(transport.process)
        for workdir in stale_workdirs:
            self._transports.pop(workdir, None)
        return cleanup


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
        text = _coco_content_text(content.get("text"))
        if not text:
            return None, current_live_text, current_chunk_id
        return text, current_live_text + text, current_chunk_id
    if message_id and message_id != current_chunk_id:
        current_live_text = ""
        current_chunk_id = message_id
    content = update.get("content")
    if not isinstance(content, dict):
        return None, current_live_text, current_chunk_id
    text = _coco_content_text(content.get("text"))
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


def _coco_content_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
