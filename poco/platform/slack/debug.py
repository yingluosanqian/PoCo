from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class SlackDebugRecorder:
    """Ring-buffer recorder for Slack inbound/outbound traffic.

    Mirrors :class:`poco.platform.feishu.debug.FeishuDebugRecorder` so the
    debug API (and future observability tooling) can render the two
    platforms side-by-side with a consistent shape.
    """

    max_items: int = 20
    _lock: RLock = field(default_factory=RLock, init=False)
    _inbound_events: deque[dict[str, Any]] = field(init=False)
    _outbound_attempts: deque[dict[str, Any]] = field(init=False)
    _errors: deque[dict[str, Any]] = field(init=False)

    def __post_init__(self) -> None:
        self._inbound_events = deque(maxlen=self.max_items)
        self._outbound_attempts = deque(maxlen=self.max_items)
        self._errors = deque(maxlen=self.max_items)

    def record_inbound(
        self,
        *,
        user_id: str | None,
        text: str | None,
        channel: str | None,
        surface: str | None,
        payload: dict[str, Any],
    ) -> None:
        event = {
            "recorded_at": utc_now_iso(),
            "user_id": user_id,
            "text": text,
            "channel": channel,
            "surface": surface,
            "payload_keys": sorted(payload.keys()),
            "event_keys": sorted((payload.get("event") or {}).keys())
            if isinstance(payload.get("event"), dict)
            else [],
        }
        with self._lock:
            self._inbound_events.appendleft(event)

    def record_outbound_attempt(
        self,
        *,
        source: str,
        channel: str,
        text: str,
        task_id: str | None = None,
    ) -> None:
        event = {
            "recorded_at": utc_now_iso(),
            "source": source,
            "channel": channel,
            "task_id": task_id,
            "text_preview": text[:300],
        }
        with self._lock:
            self._outbound_attempts.appendleft(event)

    def record_error(
        self,
        *,
        stage: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        event = {
            "recorded_at": utc_now_iso(),
            "stage": stage,
            "message": message,
            "context": context or {},
        }
        with self._lock:
            self._errors.appendleft(event)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "inbound_events": list(self._inbound_events),
                "outbound_attempts": list(self._outbound_attempts),
                "errors": list(self._errors),
            }
