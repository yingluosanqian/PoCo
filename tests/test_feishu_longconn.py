from __future__ import annotations

import unittest

from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1

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


if __name__ == "__main__":
    unittest.main()
