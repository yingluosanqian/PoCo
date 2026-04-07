from __future__ import annotations

import hashlib
import json
import unittest

from poco.interaction.service import InteractionService
from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.platform.feishu.gateway import FeishuGateway
from poco.platform.feishu.verification import (
    FeishuRequestVerifier,
    FeishuVerificationError,
)
from poco.storage.memory import InMemoryTaskStore
from poco.task.controller import TaskController
from poco.task.dispatcher import AsyncTaskDispatcher
from poco.agent.runner import StubAgentRunner


class FakeMessageClient:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, str]] = []

    def send_text(self, *, receive_id: str, receive_id_type: str, text: str) -> None:
        self.sent_messages.append(
            {
                "receive_id": receive_id,
                "receive_id_type": receive_id_type,
                "text": text,
            }
        )


class FakeDispatcher(AsyncTaskDispatcher):
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []

    def dispatch_start(self, task_id: str) -> None:
        self.actions.append(("start", task_id))

    def dispatch_resume(self, task_id: str) -> None:
        self.actions.append(("resume", task_id))


class FeishuGatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        controller = TaskController(
            store=InMemoryTaskStore(),
            runner=StubAgentRunner(),
        )
        interaction = InteractionService(controller)
        self.message_client = FakeMessageClient()
        self.dispatcher = FakeDispatcher()
        self.debug_recorder = FeishuDebugRecorder()
        self.gateway = FeishuGateway(
            interaction,
            request_verifier=FeishuRequestVerifier(verification_token="verify-token"),
            message_client=self.message_client,
            dispatcher=self.dispatcher,
            debug_recorder=self.debug_recorder,
        )

    def test_challenge_round_trip_requires_valid_token(self) -> None:
        response = self.gateway.handle_event(
            {
                "token": "verify-token",
                "challenge": "challenge-value",
            },
            headers={},
            raw_body=b'{"token":"verify-token","challenge":"challenge-value"}',
        )
        self.assertEqual(response, {"challenge": "challenge-value"})

    def test_invalid_verification_token_is_rejected(self) -> None:
        with self.assertRaises(FeishuVerificationError):
            self.gateway.handle_event(
                {
                    "token": "bad-token",
                    "challenge": "challenge-value",
                },
                headers={},
                raw_body=b'{"token":"bad-token","challenge":"challenge-value"}',
            )

    def test_message_event_sends_reply_to_chat(self) -> None:
        payload = {
            "token": "verify-token",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_demo_user"}},
                "message": {
                    "chat_type": "group",
                    "chat_id": "oc_demo_chat",
                    "content": json.dumps({"text": "/help"}),
                },
            },
        }

        response = self.gateway.handle_event(
            payload,
            headers={},
            raw_body=json.dumps(payload).encode("utf-8"),
        )

        self.assertTrue(response["ok"])
        self.assertTrue(response["delivered"])
        self.assertEqual(len(self.message_client.sent_messages), 1)
        self.assertEqual(len(self.dispatcher.actions), 0)
        sent = self.message_client.sent_messages[0]
        self.assertEqual(sent["receive_id_type"], "chat_id")
        self.assertEqual(sent["receive_id"], "oc_demo_chat")
        self.assertIn("/run <prompt>", sent["text"])
        snapshot = self.debug_recorder.snapshot()
        self.assertEqual(len(snapshot["inbound_events"]), 1)
        self.assertEqual(snapshot["inbound_events"][0]["reply_receive_id_type"], "chat_id")

    def test_p2p_message_prefers_open_id_over_chat_id(self) -> None:
        payload = {
            "token": "verify-token",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_demo_user"}},
                "message": {
                    "chat_type": "p2p",
                    "chat_id": "oc_p2p_chat",
                    "content": json.dumps({"text": "/help"}),
                },
            },
        }

        response = self.gateway.handle_event(
            payload,
            headers={},
            raw_body=json.dumps(payload).encode("utf-8"),
        )

        self.assertTrue(response["ok"])
        self.assertEqual(len(self.message_client.sent_messages), 1)
        sent = self.message_client.sent_messages[0]
        self.assertEqual(sent["receive_id_type"], "open_id")
        self.assertEqual(sent["receive_id"], "ou_demo_user")

    def test_bot_sender_is_ignored(self) -> None:
        payload = {
            "token": "verify-token",
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_demo_bot"},
                    "sender_type": "bot",
                },
                "message": {
                    "chat_type": "p2p",
                    "content": json.dumps({"text": "/help"}),
                },
            },
        }

        response = self.gateway.handle_event(
            payload,
            headers={},
            raw_body=json.dumps(payload).encode("utf-8"),
        )

        self.assertTrue(response["ok"])
        self.assertTrue(response["ignored"])
        self.assertEqual(response["reason"], "non_user_sender")
        self.assertEqual(len(self.message_client.sent_messages), 0)

    def test_debug_recorder_tracks_gateway_reply_failure(self) -> None:
        class RaisingMessageClient(FakeMessageClient):
            def send_text(self, *, receive_id: str, receive_id_type: str, text: str) -> None:
                raise RuntimeError("simulated send failure")

        controller = TaskController(
            store=InMemoryTaskStore(),
            runner=StubAgentRunner(),
        )
        interaction = InteractionService(controller)
        recorder = FeishuDebugRecorder()
        gateway = FeishuGateway(
            interaction,
            request_verifier=FeishuRequestVerifier(verification_token="verify-token"),
            message_client=RaisingMessageClient(),
            debug_recorder=recorder,
        )
        payload = {
            "token": "verify-token",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_demo_user"}},
                "message": {
                    "chat_type": "p2p",
                    "content": json.dumps({"text": "/help"}),
                },
            },
        }

        with self.assertRaises(RuntimeError):
            gateway.handle_event(
                payload,
                headers={},
                raw_body=json.dumps(payload).encode("utf-8"),
            )

        snapshot = recorder.snapshot()
        self.assertEqual(len(snapshot["errors"]), 1)
        self.assertEqual(snapshot["errors"][0]["stage"], "gateway_reply")

    def test_run_command_dispatches_background_start(self) -> None:
        payload = {
            "token": "verify-token",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_demo_user"}},
                "message": {
                    "chat_id": "oc_demo_chat",
                    "content": json.dumps({"text": "/run summarize the repository"}),
                },
            },
        }

        response = self.gateway.handle_event(
            payload,
            headers={},
            raw_body=json.dumps(payload).encode("utf-8"),
        )

        self.assertTrue(response["ok"])
        self.assertEqual(len(self.dispatcher.actions), 1)
        action, task_id = self.dispatcher.actions[0]
        self.assertEqual(action, "start")
        self.assertEqual(task_id, response["task_id"])


class FeishuRequestVerifierTest(unittest.TestCase):
    def test_signature_validation(self) -> None:
        raw_body = b'{"event":{"message":{"content":"{\\"text\\":\\"/help\\"}"}}}'
        timestamp = "1712400000"
        nonce = "nonce-value"
        encrypt_key = "encrypt-key"
        signature = hashlib.sha256(
            f"{timestamp}{nonce}{encrypt_key}{raw_body.decode('utf-8')}".encode("utf-8")
        ).hexdigest()

        verifier = FeishuRequestVerifier(encrypt_key=encrypt_key)
        verifier.verify(
            payload={"event": {"message": {"content": '{"text":"/help"}'}}},
            headers={
                "X-Lark-Request-Timestamp": timestamp,
                "X-Lark-Request-Nonce": nonce,
                "X-Lark-Signature": signature,
            },
            raw_body=raw_body,
        )

    def test_encrypt_payload_is_not_supported_yet(self) -> None:
        verifier = FeishuRequestVerifier()
        with self.assertRaises(FeishuVerificationError):
            verifier.verify(
                payload={"encrypt": "encrypted-payload"},
                headers={},
                raw_body=b'{"encrypt":"encrypted-payload"}',
            )


if __name__ == "__main__":
    unittest.main()
