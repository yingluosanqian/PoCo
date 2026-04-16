from __future__ import annotations

from collections import deque
from collections.abc import Iterator
import json
import logging
import os
import select
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock, Thread
from time import monotonic

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
from poco.agent.completion_gate import CompletionGate
from poco.task.models import Task

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _CodexAppServerTransport:
    cache_key: tuple[str, str]
    workdir: str
    reasoning_effort: str
    process: subprocess.Popen[str]
    session: "_CodexAppServerSession"
    lock: RLock = field(default_factory=RLock)
    last_used_at: float = field(default_factory=monotonic)


@dataclass(slots=True)
class _CodexActiveTurn:
    session: "_CodexAppServerSession"
    thread_id: str
    turn_id: str
    io_lock: RLock = field(default_factory=RLock)


class CodexAppServerRunner:
    name = "codex"

    def __init__(
        self,
        *,
        command: str = "codex",
        workdir: str,
        model: str | None = None,
        sandbox: str = "workspace-write",
        reasoning_effort: str = "medium",
        approval_policy: str = "never",
        timeout_seconds: int = 900,
        transport_idle_seconds: float = 300.0,
        completion_settle_seconds: float = 1.0,
    ) -> None:
        self._command = command
        self._workdir = workdir
        self._model = model
        self._sandbox = sandbox
        self._reasoning_effort = reasoning_effort
        self._approval_policy = approval_policy
        self._timeout_seconds = timeout_seconds
        self._transport_idle_seconds = transport_idle_seconds
        self._completion_settle_seconds = max(0.0, completion_settle_seconds)
        self._lock = RLock()
        self._active_processes: dict[str, subprocess.Popen[str]] = {}
        self._active_turns: dict[str, _CodexActiveTurn] = {}
        self._cancelled_tasks: set[str] = set()
        self._transports: dict[tuple[str, str], _CodexAppServerTransport] = {}
        self._warming_keys: set[tuple[str, str]] = set()

    def is_ready(self) -> tuple[bool, str]:
        executable = shutil.which(self._command)
        if not executable:
            return False, f"Codex CLI not found: {self._command}"
        if not Path(self._workdir).exists():
            return False, f"Codex workdir does not exist: {self._workdir}"
        return True, f"Codex app-server ready via {executable}"

    def warm(
        self,
        *,
        workdir: str,
        reasoning_effort: str | None = None,
    ) -> bool:
        """Best-effort background pre-warm of a transport for the given key.

        Returns True if a warm was scheduled, False if the transport was
        already alive or a warm for the same key is in flight. Never raises;
        logs at INFO on failure.
        """
        effort = reasoning_effort or self._reasoning_effort
        cache_key = (workdir, effort)
        with self._lock:
            existing = self._transports.get(cache_key)
            if existing is not None and existing.process.poll() is None:
                return False
            if cache_key in self._warming_keys:
                return False
            self._warming_keys.add(cache_key)

        def _worker() -> None:
            transport: _CodexAppServerTransport | None = None
            try:
                transport = self._start_transport(workdir, reasoning_effort=effort)
            except Exception as exc:  # pragma: no cover - defensive catch
                _LOGGER.info(
                    "codex warm failed for workdir=%s reasoning_effort=%s: %s",
                    workdir,
                    effort,
                    exc,
                )
            stale: subprocess.Popen[str] | None = None
            with self._lock:
                self._warming_keys.discard(cache_key)
                if transport is None:
                    return
                existing = self._transports.get(cache_key)
                if existing is not None and existing.process.poll() is None:
                    stale = transport.process
                else:
                    if existing is not None:
                        self._transports.pop(cache_key, None)
                    transport.last_used_at = monotonic()
                    self._transports[cache_key] = transport
            if stale is not None:
                _cleanup_subprocess(stale)
                return
            _LOGGER.info(
                "codex warm ready: workdir=%s reasoning_effort=%s",
                workdir,
                effort,
            )

        Thread(target=_worker, daemon=True, name="codex-warm").start()
        return True

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

    def steer(self, task: Task, prompt: str) -> tuple[bool, str]:
        instruction = prompt.strip()
        if not instruction:
            return False, "Steer prompt cannot be empty."
        with self._lock:
            active_turn = self._active_turns.get(task.id)
        if active_turn is None:
            return False, "Codex steer is only available while the task is actively running."
        with active_turn.io_lock:
            try:
                result = active_turn.session.request(
                    "turn/steer",
                    {
                        "threadId": active_turn.thread_id,
                        "expectedTurnId": active_turn.turn_id,
                        "input": [{"type": "text", "text": instruction}],
                    },
                )
            except RuntimeError as exc:
                return False, str(exc) or "Codex steer failed."
        turn_id = _extract_turn_id(result)
        if turn_id:
            with self._lock:
                latest = self._active_turns.get(task.id)
                if latest is active_turn:
                    latest.turn_id = turn_id
        return True, "Steer sent to Codex."

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        return (
            task.effective_model or self._model,
            task.effective_workdir or self._workdir,
            task.effective_sandbox or self._sandbox,
        )

    def is_task_active(self, task: Task) -> bool | None:
        with self._lock:
            process = self._active_processes.get(task.id)
            active_turn = self._active_turns.get(task.id)
        if process is None and active_turn is None:
            return False
        if process is not None and process.poll() is None:
            return True
        return active_turn is not None

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
        transport: _CodexAppServerTransport | None = None
        transport_broken = False
        backend_session_id = task.backend_session_id
        try:
            resolved_reasoning_effort = (
                _string_or_none(task.effective_backend_config.get("reasoning_effort"))
                or self._reasoning_effort
            )
            transport = self._acquire_transport(
                workdir,
                reasoning_effort=resolved_reasoning_effort,
            )
            process = transport.process
            with self._lock:
                self._active_processes[task.id] = process
            session = transport.session

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

            turn_result = session.request(
                "turn/start",
                {
                    "threadId": backend_session_id,
                    "cwd": workdir,
                    "model": resolved_model,
                    "input": [{"type": "text", "text": prompt}],
                },
            )
            active_turn_id = _extract_turn_id(turn_result)
            if backend_session_id and active_turn_id:
                with self._lock:
                    self._active_turns[task.id] = _CodexActiveTurn(
                        session=session,
                        thread_id=backend_session_id,
                        turn_id=active_turn_id,
                    )

            final_text: str | None = None
            final_streamed_text = ""
            streamed_text = ""
            last_reasoning_token_count: int | None = None
            deadline = monotonic() + self._timeout_seconds
            agent_message_phases: dict[str, str | None] = {}
            completion_gate = CompletionGate(settle_seconds=self._completion_settle_seconds)
            while True:
                if self._consume_cancelled(task.id):
                    return
                if monotonic() >= deadline:
                    yield AgentRunUpdate(
                        kind="failed",
                        message=f"Codex timed out after {self._timeout_seconds} seconds.",
                        backend_session_id=backend_session_id,
                    )
                    return
                should_fire, settle_elapsed = completion_gate.tick(monotonic())
                if should_fire:
                    _LOGGER.info(
                        "codex task %s completed via settle fallback after %.2fs (no turn/completed observed)",
                        task.id,
                        settle_elapsed,
                    )
                    yield AgentRunUpdate(
                        kind="completed",
                        message="Task completed by the codex app-server runner after the final answer settled.",
                        raw_result=final_text or final_streamed_text or "Codex completed without a final response body.",
                        backend_session_id=backend_session_id,
                    )
                    return
                with self._lock:
                    active_state = self._active_turns.get(task.id)
                read_lock = active_state.io_lock if active_state is not None else None
                if read_lock is not None:
                    read_lock.acquire()
                message_stream_closed = False
                try:
                    try:
                        message = session.read_next_message(timeout_seconds=0.5)
                    except StopIteration:
                        message = None
                        message_stream_closed = True
                finally:
                    if read_lock is not None:
                        read_lock.release()
                if message is None:
                    if process.poll() is not None:
                        break
                    if message_stream_closed:
                        transport_broken = True
                        break
                    continue
                if "method" not in message:
                    continue
                method = str(message["method"])
                params = message.get("params")
                if not isinstance(params, dict):
                    continue
                message_thread_id = _optional_string(params.get("threadId"))
                message_turn_id = _optional_string(params.get("turnId"))
                if method != "error" and message_thread_id and message_thread_id != backend_session_id:
                    continue
                current_time = monotonic()

                if method == "turn/started":
                    turn = params.get("turn")
                    thread_id = _optional_string(params.get("threadId")) or backend_session_id
                    started_turn_id = active_turn_id
                    if isinstance(turn, dict):
                        started_turn_id = _optional_string(turn.get("id")) or started_turn_id
                    if (
                        thread_id != backend_session_id
                        or (
                            started_turn_id is not None
                            and active_turn_id is not None
                            and started_turn_id != active_turn_id
                        )
                    ):
                        continue
                    active_turn_id = started_turn_id
                    if thread_id and active_turn_id:
                        with self._lock:
                            self._active_turns[task.id] = _CodexActiveTurn(
                                session=session,
                                thread_id=thread_id,
                                turn_id=active_turn_id,
                            )
                    yield AgentRunUpdate(
                        kind="progress",
                        message="Codex turn started.",
                        backend_session_id=backend_session_id,
                    )
                    continue

                if method == "item/agentMessage/delta":
                    if message_turn_id and active_turn_id and message_turn_id != active_turn_id:
                        continue
                    delta = _string_or_none(params.get("delta"))
                    if delta:
                        completion_gate.disarm()
                        streamed_text += delta
                        item_id = _optional_string(params.get("itemId"))
                        if item_id and agent_message_phases.get(item_id) == "final_answer":
                            final_streamed_text += delta
                        yield AgentRunUpdate(
                            kind="progress",
                            message="Codex output updated.",
                            output_chunk=delta,
                            backend_session_id=backend_session_id,
                        )
                    continue

                if method == "item/completed":
                    if message_turn_id and active_turn_id and message_turn_id != active_turn_id:
                        continue
                    item = params.get("item")
                    if isinstance(item, dict):
                        item_type = _optional_string(item.get("type"))
                        if item_type == "agentMessage":
                            phase = _optional_string(item.get("phase"))
                            item_id = _optional_string(item.get("id"))
                            if item_id:
                                agent_message_phases[item_id] = phase
                            if phase == "final_answer":
                                final_text = _string_or_none(item.get("text")) or final_text
                                if completion_gate.arm(current_time):
                                    _LOGGER.info(
                                        "codex task %s armed completion settle candidate (phase=final_answer)",
                                        task.id,
                                    )
                            else:
                                completion_gate.disarm()
                        elif item_type == "reasoning":
                            completion_gate.disarm()
                            summary = _codex_reasoning_summary(item)
                            if summary:
                                yield AgentRunUpdate(
                                    kind="progress",
                                    message=f"Codex reasoning: {summary}",
                                    backend_session_id=backend_session_id,
                                )
                        else:
                            completion_gate.disarm()
                    continue

                if method == "turn/completed":
                    turn = params.get("turn")
                    completed_turn_id = message_turn_id
                    if isinstance(turn, dict):
                        completed_turn_id = _optional_string(turn.get("id")) or completed_turn_id
                    if completed_turn_id and active_turn_id and completed_turn_id != active_turn_id:
                        continue
                    if isinstance(turn, dict) and turn.get("error"):
                        yield AgentRunUpdate(
                            kind="failed",
                            message=_turn_error_message(turn) or "Codex turn failed.",
                            backend_session_id=backend_session_id,
                        )
                        return
                    _LOGGER.info("codex task %s completed via turn/completed", task.id)
                    yield AgentRunUpdate(
                        kind="completed",
                        message="Task completed by the codex app-server runner.",
                        raw_result=final_text or final_streamed_text or "Codex completed without a final response body.",
                        backend_session_id=backend_session_id,
                    )
                    return

                if method == "thread/status/changed":
                    if message_thread_id and backend_session_id and message_thread_id != backend_session_id:
                        continue
                    status = params.get("status")
                    if isinstance(status, dict) and status.get("type") == "active":
                        completion_gate.disarm()
                        yield AgentRunUpdate(
                            kind="progress",
                            message="Codex is processing your prompt.",
                            backend_session_id=backend_session_id,
                        )
                    continue

                if method == "mcpServer/startupStatus/updated":
                    server_name = _optional_string(params.get("name")) or "Codex tools"
                    startup_status = _optional_string(params.get("status")) or "unknown"
                    if startup_status == "starting":
                        message = f"{server_name} are starting."
                    elif startup_status == "ready":
                        message = f"{server_name} are ready."
                    else:
                        message = f"{server_name} status: {startup_status}."
                    yield AgentRunUpdate(
                        kind="progress",
                        message=message,
                        backend_session_id=backend_session_id,
                    )
                    continue

                if method == "thread/tokenUsage/updated":
                    if message_turn_id and active_turn_id and message_turn_id != active_turn_id:
                        continue
                    reasoning_token_count = _codex_reasoning_token_count(params)
                    if (
                        reasoning_token_count is None
                        or reasoning_token_count <= 0
                        or reasoning_token_count == last_reasoning_token_count
                    ):
                        continue
                    last_reasoning_token_count = reasoning_token_count
                    yield AgentRunUpdate(
                        kind="progress",
                        message=f"Codex is thinking. reasoning tokens: {reasoning_token_count}.",
                        backend_session_id=backend_session_id,
                    )
                    continue

                if method == "item/started":
                    item = params.get("item")
                    if not isinstance(item, dict):
                        continue
                    item_type = _optional_string(item.get("type"))
                    if item_type == "userMessage":
                        message = "Prompt accepted by Codex."
                    elif item_type == "reasoning":
                        completion_gate.disarm()
                        message = "Codex is thinking."
                    elif item_type == "agentMessage":
                        item_id = _optional_string(item.get("id"))
                        if item_id:
                            agent_message_phases[item_id] = _optional_string(item.get("phase"))
                        completion_gate.disarm()
                        message = "Codex is drafting a reply."
                    else:
                        completion_gate.disarm()
                        continue
                    yield AgentRunUpdate(
                        kind="progress",
                        message=message,
                        backend_session_id=backend_session_id,
                    )
                    continue

                if method == "error":
                    yield AgentRunUpdate(
                        kind="failed",
                        message=_error_notification_message(params) or "Codex app-server returned an error.",
                        backend_session_id=backend_session_id,
                    )
                    return

            transport_broken = True
            if self._consume_cancelled(task.id):
                return
            yield AgentRunUpdate(
                kind="failed",
                message=session.failure_detail("Codex app-server closed before task completion."),
                backend_session_id=backend_session_id,
            )
        except RuntimeError as exc:
            transport_broken = True
            yield AgentRunUpdate(
                kind="failed",
                message=str(exc) or "Codex app-server request failed.",
                backend_session_id=backend_session_id,
            )
        except OSError as exc:
            transport_broken = True
            yield AgentRunUpdate(
                kind="failed",
                message=f"Failed to start codex app-server: {exc}",
                backend_session_id=backend_session_id,
            )
        finally:
            with self._lock:
                self._active_processes.pop(task.id, None)
                self._active_turns.pop(task.id, None)
                self._cancelled_tasks.discard(task.id)
            self._release_transport(transport, broken=transport_broken)

    def _consume_cancelled(self, task_id: str) -> bool:
        with self._lock:
            if task_id not in self._cancelled_tasks:
                return False
            self._cancelled_tasks.discard(task_id)
            return True

    def _acquire_transport(self, workdir: str, *, reasoning_effort: str) -> _CodexAppServerTransport:
        cache_key = (workdir, reasoning_effort)
        with self._lock:
            cleanup_candidates = self._collect_idle_transports_locked(exclude_key=cache_key)
            transport = self._transports.get(cache_key)
            if transport is not None and transport.process.poll() is not None:
                self._transports.pop(cache_key, None)
                cleanup_candidates.append(transport.process)
                transport = None
            if transport is None:
                transport = self._start_transport(workdir, reasoning_effort=reasoning_effort)
                self._transports[cache_key] = transport
        for candidate in cleanup_candidates:
            _cleanup_subprocess(candidate)
        transport.lock.acquire()
        with self._lock:
            transport.last_used_at = monotonic()
        return transport

    def _release_transport(self, transport: _CodexAppServerTransport | None, *, broken: bool) -> None:
        if transport is None:
            return
        cleanup: subprocess.Popen[str] | None = None
        with self._lock:
            transport.last_used_at = monotonic()
            if broken or transport.process.poll() is not None:
                if self._transports.get(transport.cache_key) is transport:
                    self._transports.pop(transport.cache_key, None)
                cleanup = transport.process
            transport.lock.release()
        if cleanup is not None:
            _cleanup_subprocess(cleanup)

    def _start_transport(self, workdir: str, *, reasoning_effort: str) -> _CodexAppServerTransport:
        process = subprocess.Popen(
            [
                self._command,
                "app-server",
                "-c",
                f'model_reasoning_effort="{reasoning_effort}"',
                "--listen",
                "stdio://",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=workdir,
            env=os.environ.copy(),
        )
        try:
            session = _CodexAppServerSession(
                process=process,
                timeout_seconds=self._timeout_seconds,
            )
            session.initialize()
            return _CodexAppServerTransport(
                cache_key=(workdir, reasoning_effort),
                workdir=workdir,
                reasoning_effort=reasoning_effort,
                process=process,
                session=session,
            )
        except Exception:
            _cleanup_subprocess(process)
            raise

    def _collect_idle_transports_locked(
        self,
        *,
        exclude_key: tuple[str, str] | None = None,
    ) -> list[subprocess.Popen[str]]:
        if self._transport_idle_seconds <= 0:
            return []
        now = monotonic()
        stale_keys: list[tuple[str, str]] = []
        cleanup: list[subprocess.Popen[str]] = []
        for cache_key, transport in self._transports.items():
            if exclude_key is not None and cache_key == exclude_key:
                continue
            if transport.process.poll() is not None:
                stale_keys.append(cache_key)
                cleanup.append(transport.process)
                continue
            if now - transport.last_used_at < self._transport_idle_seconds:
                continue
            if not transport.lock.acquire(blocking=False):
                continue
            transport.lock.release()
            stale_keys.append(cache_key)
            cleanup.append(transport.process)
        for cache_key in stale_keys:
            self._transports.pop(cache_key, None)
        return cleanup


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

    def read_next_message(self, timeout_seconds: float | None = None) -> dict[str, object] | None:
        if self._pending_notifications:
            return self._pending_notifications.popleft()
        timeout = self._timeout_seconds if timeout_seconds is None else max(0.0, timeout_seconds)
        return self._read_message(deadline=monotonic() + timeout)

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


def _extract_thread_id(result: dict[str, object]) -> str | None:
    thread = result.get("thread")
    if not isinstance(thread, dict):
        return None
    return _optional_string(thread.get("id"))


def _extract_turn_id(result: dict[str, object]) -> str | None:
    turn = result.get("turn")
    if isinstance(turn, dict):
        return _optional_string(turn.get("id"))
    return _optional_string(result.get("turnId"))


def _codex_reasoning_token_count(params: dict[str, object]) -> int | None:
    token_usage = params.get("tokenUsage")
    if not isinstance(token_usage, dict):
        return None
    for bucket_name in ("last", "total"):
        bucket = token_usage.get(bucket_name)
        if not isinstance(bucket, dict):
            continue
        count = bucket.get("reasoningOutputTokens")
        if isinstance(count, bool):
            continue
        if isinstance(count, int):
            return count
        if isinstance(count, float):
            return int(count)
    return None


def _codex_reasoning_summary(item: dict[str, object]) -> str | None:
    parts: list[str] = []
    for value in item.get("summary", []), item.get("content", []):
        if isinstance(value, list):
            for entry in value:
                if not isinstance(entry, dict):
                    continue
                text = _optional_string(entry.get("text"))
                if text:
                    parts.append(text)
    if not parts:
        return None
    return " ".join(parts).strip() or None


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
