from __future__ import annotations

from collections import deque
from collections.abc import Iterator
import json
import logging
import os
import select
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, RLock
from time import monotonic
from typing import Literal, Protocol

from poco.agent.completion_gate import CompletionGate
from poco.task.models import Task

_LOGGER = logging.getLogger(__name__)

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


@dataclass(slots=True)
class _TraeAcpTransport:
    workdir: str
    process: subprocess.Popen[str]
    client: "_TraeAcpClient"
    lock: RLock = field(default_factory=RLock)
    last_used_at: float = field(default_factory=monotonic)


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

    def steer(self, task: Task, prompt: str) -> tuple[bool, str]:
        ...

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        ...

    def is_task_active(self, task: Task) -> bool | None:
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
        anthropic_base_url = _string_or_none(task.effective_backend_config.get("anthropic_base_url"))
        anthropic_api_key = _string_or_none(task.effective_backend_config.get("anthropic_api_key"))
        if anthropic_base_url:
            env["ANTHROPIC_BASE_URL"] = anthropic_base_url
        if anthropic_api_key:
            env["ANTHROPIC_API_KEY"] = anthropic_api_key
        if resolved_permission_mode == "bypassPermissions":
            env["IS_SANDBOX"] = "1"

        process: subprocess.Popen[str] | None = None
        backend_session_id = task.backend_session_id
        stderr_lines: list[str] = []
        final_text: str | None = None
        streamed_text = ""
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
                        if isinstance(stream_event, dict) and stream_event.get("type") == "content_block_delta":
                            delta = stream_event.get("delta")
                            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                                text = _string_or_none(delta.get("text"))
                                if text:
                                    streamed_text += text
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
                        active_session.session_id = backend_session_id
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
                raw_result=streamed_text or final_text or "Claude Code completed without a final response body.",
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
        while True:
            if pending.event.is_set():
                break
            remaining = max(0.0, deadline - monotonic())
            if remaining == 0.0:
                with active.io_lock:
                    active.pending_controls.pop(request_id, None)
                raise RuntimeError(f"Claude Code control request timed out: {request.get('subtype')}")
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
                        yield AgentRunUpdate(
                            kind="progress",
                            message="Cursor Agent output updated.",
                            output_chunk=output_chunk,
                            backend_session_id=backend_session_id,
                        )
                    extracted_final_text = _extract_cursor_final_text(event)
                    if extracted_final_text:
                        final_text = extracted_final_text
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


def create_agent_runner(
    *,
    backend: str,
    codex_command: str,
    codex_workdir: str,
    codex_model: str | None,
    codex_sandbox: str,
    codex_reasoning_effort: str,
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
            reasoning_effort=codex_reasoning_effort,
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


def _compact_json(value: object, *, limit: int = 800) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


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
