from __future__ import annotations

from collections.abc import Iterator
import json
import logging
import select
import subprocess
from dataclasses import dataclass
from typing import Literal, Protocol

from poco.agent.tokens import TokenUsage
from poco.task.models import Task

_LOGGER = logging.getLogger(__name__)

UpdateKind = Literal["progress", "confirmation_required", "completed", "failed"]


@dataclass(frozen=True, slots=True)
class AgentRunUpdate:
    kind: UpdateKind
    message: str
    output_chunk: str | None = None
    raw_result: str | None = None
    backend_session_id: str | None = None
    last_token_usage: TokenUsage | None = None
    total_token_usage: TokenUsage | None = None
    activity_hint: str | None = None

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

    def steer(self, task: Task, prompt: str) -> tuple[bool, str]:
        ...

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        ...

    def is_task_active(self, task: Task) -> bool | None:
        ...


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


def _compact_json(value: object, *, limit: int = 800) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


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
