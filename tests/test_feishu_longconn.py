from __future__ import annotations

import importlib
import unittest
from threading import Event

from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTrigger

from poco.platform.feishu.longconn import FeishuLongconnListener


class FakeGateway:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def handle_event(
        self,
        payload: dict[str, object],
        *,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> dict[str, object]:
        self.payloads.append(payload)
        return {"ok": True}


class FakeCardGateway:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def handle_action(
        self,
        payload: dict[str, object],
        *,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> dict[str, object]:
        self.payloads.append(payload)
        return {"toast": {"type": "success", "content": "ok"}}


class FeishuLongconnListenerTest(unittest.TestCase):
    def test_message_event_is_forwarded_to_gateway(self) -> None:
        gateway = FakeGateway()
        listener = FeishuLongconnListener(
            app_id="cli_demo",
            app_secret="secret",
            gateway=gateway,
            delivery_mode="longconn",
        )
        event = P2ImMessageReceiveV1(
            {
                "schema": "2.0",
                "header": {
                    "event_id": "evt_demo",
                    "token": "token",
                    "create_time": "1",
                    "event_type": "im.message.receive_v1",
                    "tenant_key": "tenant",
                    "app_id": "cli_demo",
                },
                "event": {
                    "sender": {
                        "sender_id": {"open_id": "ou_demo_user"},
                        "sender_type": "user",
                        "tenant_key": "tenant",
                    },
                    "message": {
                        "message_id": "om_demo",
                        "root_id": "",
                        "parent_id": "",
                        "create_time": "1",
                        "chat_id": "oc_demo_chat",
                        "chat_type": "p2p",
                        "message_type": "text",
                        "content": "{\"text\":\"/help\"}",
                    },
                },
            }
        )

        listener.handle_message_receive_event(event)

        self.assertEqual(len(gateway.payloads), 1)
        payload = gateway.payloads[0]
        self.assertEqual(payload["header"]["event_type"], "im.message.receive_v1")
        self.assertEqual(payload["event"]["message"]["chat_type"], "p2p")
        snapshot = listener.snapshot()
        self.assertTrue(snapshot["enabled"])
        self.assertIsNotNone(snapshot["last_event_at"])

    def test_card_action_event_is_forwarded_to_card_gateway(self) -> None:
        gateway = FakeGateway()
        card_gateway = FakeCardGateway()
        listener = FeishuLongconnListener(
            app_id="cli_demo",
            app_secret="secret",
            gateway=gateway,
            card_gateway=card_gateway,
            delivery_mode="longconn",
        )
        event = P2CardActionTrigger(
            {
                "schema": "2.0",
                "event_id": "evt_card_demo",
                "token": "token",
                "create_time": "1",
                "event_type": "card.action.trigger",
                "tenant_key": "tenant",
                "app_id": "cli_demo",
                "event": {
                    "operator": {"open_id": "ou_demo_user"},
                    "action": {
                        "value": {
                            "intent_key": "project.create",
                            "surface": "dm",
                        },
                        "tag": "button",
                    },
                    "context": {"open_message_id": "om_card_demo"},
                },
            }
        )

        listener.handle_card_action_event(event)

        self.assertEqual(len(card_gateway.payloads), 1)
        payload = card_gateway.payloads[0]
        self.assertEqual(payload["event"]["action"]["value"]["intent_key"], "project.create")
        self.assertEqual(payload["event"]["context"]["open_message_id"], "om_card_demo")
        snapshot = listener.snapshot()
        self.assertIsNotNone(snapshot["last_event_at"])

    def test_disabled_listener_reports_webhook_mode(self) -> None:
        listener = FeishuLongconnListener(
            app_id=None,
            app_secret=None,
            gateway=FakeGateway(),
            delivery_mode="webhook",
        )

        ready, detail = listener.readiness()

        self.assertTrue(ready)
        self.assertIn("webhook", detail.lower())

    def test_start_background_creates_thread_when_ready(self) -> None:
        started = Event()

        class TestListener(FeishuLongconnListener):
            def _build_client(self) -> object:
                started.set()

                class FakeClient:
                    def start(self) -> None:
                        return None

                return FakeClient()

        listener = TestListener(
            app_id="cli_demo",
            app_secret="secret",
            gateway=FakeGateway(),
            card_gateway=FakeCardGateway(),
            delivery_mode="longconn",
        )

        listener.start_background()
        self.assertTrue(started.wait(timeout=2))

        ready, detail = listener.readiness()
        self.assertTrue(ready)
        self.assertIn(detail.lower(), {"feishu long connection listener has been started.", "feishu long connection listener is running."})

    def test_prepare_sdk_event_loop_rebinds_sdk_global_loop(self) -> None:
        listener = FeishuLongconnListener(
            app_id="cli_demo",
            app_secret="secret",
            gateway=FakeGateway(),
            card_gateway=FakeCardGateway(),
            delivery_mode="longconn",
        )

        loop = listener._prepare_sdk_event_loop()
        client_module = importlib.import_module("lark_oapi.ws.client")

        self.assertIs(client_module.loop, loop)
        self.assertFalse(loop.is_closed())
        loop.close()


if __name__ == "__main__":
    unittest.main()
