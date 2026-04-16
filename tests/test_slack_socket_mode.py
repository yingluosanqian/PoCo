from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any

from poco.platform.slack.socket_mode import SlackSocketModeListener


class _FakeConnection:
    def __init__(self, incoming: list[str]) -> None:
        self._incoming = list(incoming)
        self.sent: list[str] = []

    async def recv(self) -> str:
        if not self._incoming:
            # Simulate Slack closing the connection after the scripted messages.
            raise _FakeConnectionClosed()
        return self._incoming.pop(0)

    async def send(self, data: str) -> None:
        self.sent.append(data)


class _FakeConnectionClosed(Exception):
    pass


def _drive_stream(listener: SlackSocketModeListener, connection: _FakeConnection) -> None:
    # Patch the listener's ConnectionClosed recognition for this test.
    import poco.platform.slack.socket_mode as module

    original = module.ConnectionClosed
    module.ConnectionClosed = _FakeConnectionClosed  # type: ignore[attr-defined]
    try:
        asyncio.run(listener._stream_connection(connection))
    finally:
        module.ConnectionClosed = original  # type: ignore[attr-defined]


class SlackSocketModeListenerTest(unittest.TestCase):
    def test_enabled_flag_tracks_delivery_mode(self) -> None:
        off = SlackSocketModeListener(app_token=None, delivery_mode="webhook")
        on = SlackSocketModeListener(app_token="xapp-1", delivery_mode="socket_mode")
        self.assertFalse(off.enabled)
        self.assertTrue(on.enabled)

    def test_readiness_reports_missing_token(self) -> None:
        listener = SlackSocketModeListener(app_token=None, delivery_mode="socket_mode")
        ready, detail = listener.readiness()
        self.assertFalse(ready)
        self.assertIn("xapp", detail)

    def test_hello_envelope_marks_event_but_emits_no_ack(self) -> None:
        listener = SlackSocketModeListener(app_token="xapp-1", delivery_mode="socket_mode")
        ack = listener.handle_envelope({"type": "hello"})
        self.assertIsNone(ack)
        self.assertIsNotNone(listener.snapshot()["last_event_at"])

    def test_events_api_envelope_invokes_event_handler_and_acks(self) -> None:
        seen: list[dict[str, Any]] = []

        def event_handler(payload: dict[str, Any]) -> dict[str, Any] | None:
            seen.append(payload)
            return None

        listener = SlackSocketModeListener(
            app_token="xapp-1",
            delivery_mode="socket_mode",
            event_handler=event_handler,
        )
        ack = listener.handle_envelope(
            {
                "type": "events_api",
                "envelope_id": "env-1",
                "payload": {"event": {"type": "app_mention"}},
            }
        )
        self.assertEqual(ack, {"envelope_id": "env-1"})
        self.assertEqual(seen, [{"event": {"type": "app_mention"}}])

    def test_interactive_handler_response_included_in_ack_payload(self) -> None:
        def interactive_handler(payload: dict[str, Any]) -> dict[str, Any]:
            return {"ok": True, "payload_keys": sorted(payload.keys())}

        listener = SlackSocketModeListener(
            app_token="xapp-1",
            delivery_mode="socket_mode",
            interactive_handler=interactive_handler,
        )
        ack = listener.handle_envelope(
            {
                "type": "interactive",
                "envelope_id": "env-2",
                "payload": {"actions": [], "user": {"id": "U1"}},
            }
        )
        self.assertEqual(ack["envelope_id"], "env-2")
        self.assertEqual(ack["payload"]["ok"], True)
        self.assertEqual(ack["payload"]["payload_keys"], ["actions", "user"])

    def test_slash_command_handler_invoked(self) -> None:
        seen: list[dict[str, Any]] = []

        def command_handler(payload: dict[str, Any]) -> dict[str, Any]:
            seen.append(payload)
            return {"response_type": "ephemeral", "text": "ok"}

        listener = SlackSocketModeListener(
            app_token="xapp-1",
            delivery_mode="socket_mode",
            command_handler=command_handler,
        )
        ack = listener.handle_envelope(
            {
                "type": "slash_commands",
                "envelope_id": "env-3",
                "payload": {"command": "/poco", "text": "status"},
            }
        )
        self.assertEqual(ack["envelope_id"], "env-3")
        self.assertEqual(ack["payload"]["text"], "ok")
        self.assertEqual(len(seen), 1)

    def test_handler_exception_records_error_and_still_acks(self) -> None:
        errors: list[tuple[str, str, dict[str, Any]]] = []

        def failing_handler(_payload: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("boom")

        listener = SlackSocketModeListener(
            app_token="xapp-1",
            delivery_mode="socket_mode",
            interactive_handler=failing_handler,
            error_recorder=lambda stage, msg, ctx: errors.append((stage, msg, ctx)),
        )
        ack = listener.handle_envelope(
            {
                "type": "interactive",
                "envelope_id": "env-4",
                "payload": {"actions": []},
            }
        )
        self.assertEqual(ack, {"envelope_id": "env-4"})
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][0], "slack_socket_dispatch")
        self.assertIn("boom", errors[0][1])

    def test_envelope_without_envelope_id_is_ignored(self) -> None:
        listener = SlackSocketModeListener(
            app_token="xapp-1",
            delivery_mode="socket_mode",
            interactive_handler=lambda _p: {"ok": True},
        )
        ack = listener.handle_envelope({"type": "interactive", "payload": {}})
        self.assertIsNone(ack)

    def test_unknown_envelope_type_acks_without_payload(self) -> None:
        listener = SlackSocketModeListener(
            app_token="xapp-1",
            delivery_mode="socket_mode",
        )
        ack = listener.handle_envelope({"type": "other", "envelope_id": "env-5"})
        self.assertEqual(ack, {"envelope_id": "env-5"})

    def test_stream_loop_writes_ack_back_to_connection(self) -> None:
        def event_handler(_payload: dict[str, Any]) -> dict[str, Any] | None:
            return None

        listener = SlackSocketModeListener(
            app_token="xapp-1",
            delivery_mode="socket_mode",
            event_handler=event_handler,
        )
        connection = _FakeConnection(
            [
                json.dumps({"type": "hello"}),
                json.dumps(
                    {
                        "type": "events_api",
                        "envelope_id": "env-6",
                        "payload": {"event": {"type": "message"}},
                    }
                ),
                "not-json",
            ]
        )
        _drive_stream(listener, connection)
        self.assertEqual(len(connection.sent), 1)
        ack = json.loads(connection.sent[0])
        self.assertEqual(ack, {"envelope_id": "env-6"})

    def test_snapshot_has_expected_shape(self) -> None:
        listener = SlackSocketModeListener(
            app_token="xapp-1",
            delivery_mode="socket_mode",
        )
        snapshot = listener.snapshot()
        self.assertIn("enabled", snapshot)
        self.assertIn("ready", snapshot)
        self.assertIn("detail", snapshot)
        self.assertIn("last_error", snapshot)
        self.assertTrue(snapshot["enabled"])


if __name__ == "__main__":
    unittest.main()
