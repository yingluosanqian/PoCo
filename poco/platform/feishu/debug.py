from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class FeishuDebugRecorder:
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
        reply_receive_id: str | None,
        reply_receive_id_type: str | None,
        payload: dict[str, Any],
    ) -> None:
        event = {
            "recorded_at": utc_now_iso(),
            "user_id": user_id,
            "text": text,
            "reply_receive_id": reply_receive_id,
            "reply_receive_id_type": reply_receive_id_type,
            "payload_keys": sorted(payload.keys()),
            "event_keys": sorted((payload.get("event") or {}).keys()) if isinstance(payload.get("event"), dict) else [],
        }
        with self._lock:
            self._inbound_events.appendleft(event)

    def record_outbound_attempt(
        self,
        *,
        source: str,
        receive_id: str,
        receive_id_type: str,
        text: str,
        task_id: str | None = None,
    ) -> None:
        event = {
            "recorded_at": utc_now_iso(),
            "source": source,
            "receive_id": receive_id,
            "receive_id_type": receive_id_type,
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
