from __future__ import annotations

import json
from datetime import UTC, datetime
from threading import RLock, Thread
from typing import Any

from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.platform.feishu.gateway import FeishuGateway

try:
    from lark_oapi import EventDispatcherHandler, JSON, LogLevel
    from lark_oapi.ws import Client as LarkWsClient
except ImportError:  # pragma: no cover
    EventDispatcherHandler = None
    JSON = None
    LogLevel = None
    LarkWsClient = None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class FeishuLongconnListener:
    def __init__(
        self,
        *,
        app_id: str | None,
        app_secret: str | None,
        gateway: FeishuGateway,
        delivery_mode: str,
        debug_recorder: FeishuDebugRecorder | None = None,
    ) -> None:
        self._app_id = app_id or ""
        self._app_secret = app_secret or ""
        self._gateway = gateway
        self._delivery_mode = delivery_mode
        self._debug_recorder = debug_recorder
        self._lock = RLock()
        self._thread: Thread | None = None
        self._start_attempted = False
        self._running = False
        self._started_at: str | None = None
        self._last_event_at: str | None = None
        self._last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self._delivery_mode == "longconn"

    def start_background(self) -> None:
        if not self.enabled:
            return

        with self._lock:
            if self._thread is not None:
                return
            self._start_attempted = True
            ready, detail = self.readiness()
            if not ready:
                self._last_error = detail
                return

            self._thread = Thread(
                target=self._run_forever,
                name="poco-feishu-longconn",
                daemon=True,
            )
            self._thread.start()

    def readiness(self) -> tuple[bool, str]:
        if not self.enabled:
            return True, "Feishu webhook delivery mode is active."
        if not self._app_id or not self._app_secret:
            return False, "Feishu long connection requires app_id and app_secret."
        if EventDispatcherHandler is None or JSON is None or LarkWsClient is None:
            return False, "Feishu long connection requires the lark-oapi dependency."

        with self._lock:
            if self._running and self._thread is not None and self._thread.is_alive():
                return True, "Feishu long connection listener is running."
            if self._last_error and self._start_attempted:
                return False, self._last_error
            if self._start_attempted:
                return False, "Feishu long connection listener is starting."
        return True, "Feishu long connection is configured and ready to start."

    def snapshot(self) -> dict[str, Any]:
        ready, detail = self.readiness()
        with self._lock:
            thread_alive = self._thread.is_alive() if self._thread is not None else False
            return {
                "enabled": self.enabled,
                "delivery_mode": self._delivery_mode,
                "ready": ready,
                "detail": detail,
                "start_attempted": self._start_attempted,
                "running": self._running,
                "thread_alive": thread_alive,
                "started_at": self._started_at,
                "last_event_at": self._last_event_at,
                "last_error": self._last_error,
            }

    def handle_message_receive_event(self, data: Any) -> dict[str, Any]:
        payload = self._sdk_event_to_payload(data)
        self._mark_event()
        try:
            return self._gateway.handle_event(
                payload,
                headers={},
                raw_body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
        except Exception as exc:
            self._record_error(
                stage="feishu_longconn_event",
                message=str(exc),
                context={"event_type": payload.get("header", {}).get("event_type")},
            )
            raise

    def _run_forever(self) -> None:
        self._set_running(True)
        try:
            client = self._build_client()
            client.start()
        except Exception as exc:
            self._record_error(
                stage="feishu_longconn_listener",
                message=str(exc),
                context={"delivery_mode": self._delivery_mode},
            )
        finally:
            self._set_running(False)

    def _build_client(self) -> Any:
        if EventDispatcherHandler is None or LogLevel is None or LarkWsClient is None:
            raise RuntimeError("lark-oapi is not available")
        builder = EventDispatcherHandler.builder("", "")
        handler = (
            builder.register_p2_im_message_receive_v1(self.handle_message_receive_event).build()
        )
        return LarkWsClient(
            app_id=self._app_id,
            app_secret=self._app_secret,
            log_level=LogLevel.WARN,
            event_handler=handler,
        )

    def _sdk_event_to_payload(self, data: Any) -> dict[str, Any]:
        if JSON is None:
            raise RuntimeError("lark-oapi is not available")
        raw = JSON.marshal(data)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("Feishu long connection produced an invalid payload.")
        return payload

    def _mark_event(self) -> None:
        with self._lock:
            self._last_event_at = _utc_now_iso()
            self._last_error = None

    def _set_running(self, running: bool) -> None:
        with self._lock:
            self._running = running
            if running:
                self._started_at = _utc_now_iso()
                self._last_error = None

    def _record_error(
        self,
        *,
        stage: str,
        message: str,
        context: dict[str, Any],
    ) -> None:
        with self._lock:
            self._last_error = message
        if self._debug_recorder is not None:
            self._debug_recorder.record_error(
                stage=stage,
                message=message,
                context=context,
            )
