from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock, Thread
from typing import Any

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError:  # pragma: no cover - exercised indirectly
    websockets = None  # type: ignore[assignment]
    ConnectionClosed = Exception  # type: ignore[misc,assignment]


EventHandler = Callable[[dict[str, Any]], dict[str, Any] | None]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SlackSocketModeError(RuntimeError):
    pass


class SlackSocketModeListener:
    """Background WebSocket listener for Slack Socket Mode.

    Slack's Socket Mode replaces HTTP webhooks with a single long-lived
    WebSocket (obtained via ``apps.connections.open``) that the app authenticates
    with an ``xapp-`` token. Each envelope carries one of four ``type`` values
    — ``hello``, ``events_api``, ``interactive``, ``slash_commands`` (plus
    ``disconnect``). The server expects an ack with the same ``envelope_id``
    within three seconds.

    Mirrors :class:`poco.platform.feishu.longconn.FeishuLongconnListener` so
    the orchestration layer can manage both listeners with the same
    ``readiness``/``snapshot``/``start_background`` shape.
    """

    def __init__(
        self,
        *,
        app_token: str | None,
        delivery_mode: str,
        event_handler: EventHandler | None = None,
        interactive_handler: EventHandler | None = None,
        command_handler: EventHandler | None = None,
        open_socket_url: Callable[[], str] | None = None,
        error_recorder: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._app_token = app_token or ""
        self._delivery_mode = delivery_mode
        self._event_handler = event_handler
        self._interactive_handler = interactive_handler
        self._command_handler = command_handler
        self._open_socket_url = open_socket_url or self._default_open_socket_url
        self._error_recorder = error_recorder
        self._lock = RLock()
        self._thread: Thread | None = None
        self._start_attempted = False
        self._running = False
        self._started_at: str | None = None
        self._last_event_at: str | None = None
        self._last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self._delivery_mode in {"socket", "socket_mode"}

    def start_background(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._thread is not None:
                return
            missing = self._missing_dependency_detail()
            if missing is not None:
                self._start_attempted = True
                self._last_error = missing
                return
            self._start_attempted = True
            self._thread = Thread(
                target=self._run_forever,
                name="poco-slack-socket-mode",
                daemon=True,
            )
            self._thread.start()

    def readiness(self) -> tuple[bool, str]:
        if not self.enabled:
            return True, "Slack socket mode is not the active delivery mode."
        missing = self._missing_dependency_detail()
        if missing is not None:
            return False, missing
        with self._lock:
            if self._running and self._thread is not None and self._thread.is_alive():
                return True, "Slack socket mode listener is running."
            if self._thread is not None and self._thread.is_alive():
                return False, "Slack socket mode listener is starting."
            if self._last_error and self._start_attempted:
                return False, self._last_error
            if self._start_attempted:
                return True, "Slack socket mode listener has been started."
        return True, "Slack socket mode is configured and ready to start."

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

    # Core envelope dispatch -------------------------------------------------
    #
    # ``handle_envelope`` is the sync-friendly core that tests exercise: it
    # takes a decoded envelope and returns the ack payload that should be
    # written back onto the WebSocket. The WebSocket loop is a thin shell
    # around this method.

    def handle_envelope(self, envelope: dict[str, Any]) -> dict[str, Any] | None:
        envelope_type = envelope.get("type")
        if envelope_type == "hello":
            self._mark_event()
            return None
        if envelope_type == "disconnect":
            return None
        envelope_id = envelope.get("envelope_id")
        if not envelope_id:
            return None

        self._mark_event()
        try:
            payload_response = self._dispatch_envelope(envelope_type, envelope)
        except Exception as exc:
            self._record_error(
                stage="slack_socket_dispatch",
                message=str(exc),
                context={"envelope_type": envelope_type or "unknown"},
            )
            payload_response = None

        ack: dict[str, Any] = {"envelope_id": envelope_id}
        if payload_response is not None:
            ack["payload"] = payload_response
        return ack

    def _dispatch_envelope(
        self,
        envelope_type: str | None,
        envelope: dict[str, Any],
    ) -> dict[str, Any] | None:
        payload = envelope.get("payload") or {}
        if envelope_type == "events_api" and self._event_handler is not None:
            return self._event_handler(payload)
        if envelope_type == "interactive" and self._interactive_handler is not None:
            return self._interactive_handler(payload)
        if envelope_type == "slash_commands" and self._command_handler is not None:
            return self._command_handler(payload)
        return None

    # WebSocket loop ---------------------------------------------------------

    def _run_forever(self) -> None:
        self._set_running(True)
        try:
            asyncio.run(self._connect_and_stream())
        except Exception as exc:
            self._record_error(
                stage="slack_socket_listener",
                message=str(exc),
                context={"delivery_mode": self._delivery_mode},
            )
        finally:
            self._set_running(False)

    async def _connect_and_stream(self) -> None:
        if websockets is None:
            raise SlackSocketModeError("websockets dependency is unavailable.")
        url = self._open_socket_url()
        async with websockets.connect(url, max_size=None) as connection:
            await self._stream_connection(connection)

    async def _stream_connection(self, connection: Any) -> None:
        while True:
            try:
                raw = await connection.recv()
            except ConnectionClosed:
                return
            try:
                envelope = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(envelope, dict):
                continue
            ack = self.handle_envelope(envelope)
            if ack is not None:
                await connection.send(json.dumps(ack, ensure_ascii=False))

    def _default_open_socket_url(self) -> str:
        # Imported lazily so unit tests do not hit the network even via imports.
        from urllib.request import Request, urlopen

        request = Request(
            url="https://slack.com/api/apps.connections.open",
            data=b"",
            headers={
                "Authorization": f"Bearer {self._app_token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
        if not body.get("ok"):
            raise SlackSocketModeError(
                f"apps.connections.open failed: {body.get('error', 'unknown')}"
            )
        url = body.get("url")
        if not isinstance(url, str) or not url:
            raise SlackSocketModeError("apps.connections.open returned no URL.")
        return url

    # Internal bookkeeping ---------------------------------------------------

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
        if self._error_recorder is not None:
            try:
                self._error_recorder(stage, message, context)
            except Exception:
                # Never let a failing recorder take down the listener loop.
                pass

    def _missing_dependency_detail(self) -> str | None:
        if not self._app_token:
            return "Slack socket mode requires an xapp- app-level token."
        if websockets is None:
            return "Slack socket mode requires the websockets dependency."
        return None
