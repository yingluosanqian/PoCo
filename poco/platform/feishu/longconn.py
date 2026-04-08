from __future__ import annotations

import asyncio
import base64
import http
import importlib
import json
import time
from datetime import UTC, datetime
from threading import RLock, Thread
from typing import Any

from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.platform.feishu.card_gateway import FeishuCardActionGateway
from poco.platform.feishu.gateway import FeishuGateway

try:
    from lark_oapi import EventDispatcherHandler, JSON, LogLevel
    from lark_oapi.core.const import UTF_8
    from lark_oapi.ws import Client as LarkWsClient
    from lark_oapi.ws.const import (
        HEADER_BIZ_RT,
        HEADER_MESSAGE_ID,
        HEADER_SEQ,
        HEADER_SUM,
        HEADER_TRACE_ID,
        HEADER_TYPE,
    )
    from lark_oapi.ws.enum import MessageType
    from lark_oapi.ws.model import Response
except ImportError:  # pragma: no cover
    EventDispatcherHandler = None
    JSON = None
    LogLevel = None
    LarkWsClient = None
    HEADER_BIZ_RT = None
    HEADER_MESSAGE_ID = None
    HEADER_SEQ = None
    HEADER_SUM = None
    HEADER_TRACE_ID = None
    HEADER_TYPE = None
    UTF_8 = "utf-8"
    MessageType = None
    Response = None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class FeishuLongconnListener:
    def __init__(
        self,
        *,
        app_id: str | None,
        app_secret: str | None,
        gateway: FeishuGateway,
        card_gateway: FeishuCardActionGateway | None = None,
        delivery_mode: str,
        debug_recorder: FeishuDebugRecorder | None = None,
    ) -> None:
        self._app_id = app_id or ""
        self._app_secret = app_secret or ""
        self._gateway = gateway
        self._card_gateway = card_gateway
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
            missing_detail = self._missing_dependency_detail()
            if missing_detail is not None:
                self._start_attempted = True
                self._last_error = missing_detail
                return
            self._start_attempted = True

            self._thread = Thread(
                target=self._run_forever,
                name="poco-feishu-longconn",
                daemon=True,
            )
            self._thread.start()

    def readiness(self) -> tuple[bool, str]:
        if not self.enabled:
            return True, "Feishu webhook delivery mode is active."
        missing_detail = self._missing_dependency_detail()
        if missing_detail is not None:
            return False, missing_detail

        with self._lock:
            if self._running and self._thread is not None and self._thread.is_alive():
                return True, "Feishu long connection listener is running."
            if self._thread is not None and self._thread.is_alive():
                return False, "Feishu long connection listener is starting."
            if self._last_error and self._start_attempted:
                return False, self._last_error
            if self._start_attempted:
                return True, "Feishu long connection listener has been started."
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

    def handle_card_action_event(self, data: Any) -> dict[str, Any]:
        if self._card_gateway is None:
            raise RuntimeError("Feishu long connection card action gateway is not configured.")

        payload = self._sdk_event_to_payload(data)
        self._mark_event()
        try:
            return self._card_gateway.handle_action(
                payload,
                headers={},
                raw_body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
        except Exception as exc:
            self._record_error(
                stage="feishu_longconn_card",
                message=str(exc),
                context={"event_type": payload.get("event_type")},
            )
            raise

    def _run_forever(self) -> None:
        loop = self._prepare_sdk_event_loop()
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
            if not loop.is_closed():
                loop.close()
            self._set_running(False)

    def _build_client(self) -> Any:
        if EventDispatcherHandler is None or LogLevel is None or LarkWsClient is None:
            raise RuntimeError("lark-oapi is not available")
        builder = EventDispatcherHandler.builder("", "")
        builder.register_p2_im_message_receive_v1(self.handle_message_receive_event)
        if self._card_gateway is not None:
            builder.register_p2_card_action_trigger(self.handle_card_action_event)
        handler = builder.build()
        return PoCoLarkWsClient(
            app_id=self._app_id,
            app_secret=self._app_secret,
            log_level=LogLevel.WARNING,
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

    def _missing_dependency_detail(self) -> str | None:
        if not self._app_id or not self._app_secret:
            return "Feishu long connection requires app_id and app_secret."
        if EventDispatcherHandler is None or JSON is None or LarkWsClient is None:
            return "Feishu long connection requires the lark-oapi dependency."
        return None

    def _prepare_sdk_event_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client_module = importlib.import_module("lark_oapi.ws.client")
        client_module.loop = loop
        return loop


if LarkWsClient is not None:
    class PoCoLarkWsClient(LarkWsClient):
        async def _handle_data_frame(self, frame: Any) -> None:
            hs = frame.headers
            msg_id = _get_by_key(hs, HEADER_MESSAGE_ID)
            trace_id = _get_by_key(hs, HEADER_TRACE_ID)
            sum_ = _get_by_key(hs, HEADER_SUM)
            seq = _get_by_key(hs, HEADER_SEQ)
            type_ = _get_by_key(hs, HEADER_TYPE)

            pl = frame.payload
            if int(sum_) > 1:
                pl = self._combine(msg_id, int(sum_), int(seq), pl)
                if pl is None:
                    return

            message_type = MessageType(type_)
            resp = Response(code=http.HTTPStatus.OK)
            try:
                start = int(round(time.time() * 1000))
                if message_type in {MessageType.EVENT, MessageType.CARD}:
                    result = self._event_handler.do_without_validation(pl)
                else:
                    return
                end = int(round(time.time() * 1000))
                header = hs.add()
                header.key = HEADER_BIZ_RT
                header.value = str(end - start)
                if result is not None:
                    resp.data = base64.b64encode(JSON.marshal(result).encode(UTF_8))
            except Exception:
                resp = Response(code=http.HTTPStatus.INTERNAL_SERVER_ERROR)

            frame.payload = JSON.marshal(resp).encode(UTF_8)
            await self._write_message(frame.SerializeToString())
else:  # pragma: no cover
    PoCoLarkWsClient = None


def _get_by_key(headers: Any, key: str) -> str:
    for header in headers:
        if header.key == key:
            return header.value
    raise KeyError(key)
