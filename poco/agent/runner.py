from __future__ import annotations

from collections import deque
from collections.abc import Iterator
import json
import os
import select
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Literal, Protocol

from poco.task.models import Task

UpdateKind = Literal["progress", "confirmation_required", "completed", "failed"]


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
        updates = [
            AgentRunUpdate(
                kind="progress",
                message=f"Task accepted by the {self.name} app-server runner.",
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
        return task.effective_model or self._model, task.effective_workdir or self._workdir

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
                        "sandbox": self._sandbox,
                        "approvalPolicy": self._approval_policy,
                    },
                )
            else:
                thread_result = session.request(
                    "thread/start",
                    {
                        "cwd": workdir,
                        "model": resolved_model,
                        "sandbox": self._sandbox,
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
            if process is not None:
                if process.poll() is None:
                    process.kill()
                try:
                    process.wait(timeout=1)
                except Exception:
                    pass
                for stream_name in ("stdin", "stdout", "stderr"):
                    stream = getattr(process, stream_name, None)
                    if stream is None:
                        continue
                    try:
                        stream.close()
                    except Exception:
                        pass

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
        return task.effective_model or self._model, task.effective_workdir or self._workdir

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
        if self._sandbox:
            command.extend(["-s", self._sandbox])
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
) -> AgentRunner:
    normalized = backend.strip().lower()
    if normalized == "codex":
        return CodexAppServerRunner(
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
        ready, _, _ = select.select([stdout, stderr], [], [], 0)
        return bool(ready)


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
    if isinstance(data, dict):
        nested = _optional_string(data.get("message"))
        if nested:
            return nested
    return None
