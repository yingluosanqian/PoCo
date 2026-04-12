from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest

from poco.interaction.service import InteractionService
from poco.interaction.card_dispatcher import CardActionDispatcher
from poco.interaction.card_handlers import ProjectIntentHandler, WorkspaceIntentHandler
from poco.platform.feishu.card_gateway import FeishuCardActionGateway
from poco.platform.feishu.cards import FeishuCardRenderer
from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.platform.feishu.gateway import FeishuGateway
from poco.platform.feishu.verification import (
    FeishuRequestVerifier,
    FeishuVerificationError,
)
from poco.project.controller import ProjectController
from poco.session.controller import SessionController
from poco.storage.memory import InMemoryProjectStore, InMemorySessionStore, InMemoryTaskStore, InMemoryWorkspaceContextStore
from poco.storage.sqlite import SqliteTaskStore
from poco.task.controller import TaskController
from poco.task.dispatcher import AsyncTaskDispatcher
from poco.agent.runner import StubAgentRunner
from poco.workspace.controller import WorkspaceContextController


class FakeMessageClient:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, str]] = []
        self.sent_cards: list[dict[str, object]] = []
        self.updated_cards: list[dict[str, object]] = []

    def send_text(self, *, receive_id: str, receive_id_type: str, text: str) -> None:
        self.sent_messages.append(
            {
                "receive_id": receive_id,
                "receive_id_type": receive_id_type,
                "text": text,
            }
        )

    def send_interactive(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        card: dict[str, object],
    ):
        self.sent_cards.append(
            {
                "receive_id": receive_id,
                "receive_id_type": receive_id_type,
                "card": card,
            }
        )
        return type(
            "SendResult",
            (),
            {"message_id": f"om_{len(self.sent_cards)}"},
        )()

    def update_interactive(
        self,
        *,
        message_id: str,
        card: dict[str, object],
    ) -> None:
        self.updated_cards.append(
            {
                "message_id": message_id,
                "card": card,
            }
        )


class FakeDispatcher(AsyncTaskDispatcher):
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []

    def dispatch_start(self, task_id: str) -> None:
        self.actions.append(("start", task_id))

    def dispatch_resume(self, task_id: str) -> None:
        self.actions.append(("resume", task_id))

    def dispatch_next_queued(self, project_id: str) -> None:
        self.actions.append(("next", project_id))


class FeishuGatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session_controller = SessionController(InMemorySessionStore())
        self.controller = TaskController(
            store=InMemoryTaskStore(),
            runner=StubAgentRunner(),
            session_controller=self.session_controller,
        )
        interaction = InteractionService(self.controller, session_controller=self.session_controller)
        self.message_client = FakeMessageClient()
        self.dispatcher = FakeDispatcher()
        self.debug_recorder = FeishuDebugRecorder()
        self.project_controller = ProjectController(InMemoryProjectStore())
        self.workspace_controller = WorkspaceContextController(InMemoryWorkspaceContextStore())
        project_handler = ProjectIntentHandler(self.project_controller)
        workspace_handler = WorkspaceIntentHandler(
            self.project_controller,
            self.workspace_controller,
            session_controller=self.session_controller,
        )
        self.card_gateway = FeishuCardActionGateway(
            dispatcher=CardActionDispatcher(
                {
                    "project.home": project_handler,
                    "project.new": project_handler,
                    "project.manage": project_handler,
                    "project.create": project_handler,
                    "project.open": project_handler,
                    "project.bind_group": project_handler,
                    "workspace.open": workspace_handler,
                }
            ),
            renderer=FeishuCardRenderer(),
            project_controller=self.project_controller,
        )
        self.gateway = FeishuGateway(
            interaction,
            request_verifier=FeishuRequestVerifier(verification_token="verify-token"),
            message_client=self.message_client,
            dispatcher=self.dispatcher,
            card_gateway=self.card_gateway,
            task_controller=self.controller,
            card_renderer=FeishuCardRenderer(),
            debug_recorder=self.debug_recorder,
            project_controller=self.project_controller,
            workspace_controller=self.workspace_controller,
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
        self.assertEqual(len(self.message_client.sent_cards), 0)
        self.assertEqual(len(self.dispatcher.actions), 0)
        sent = self.message_client.sent_messages[0]
        self.assertEqual(sent["receive_id_type"], "chat_id")
        self.assertEqual(sent["receive_id"], "oc_demo_chat")
        self.assertIn("This group is not bound to a project yet.", sent["text"])
        snapshot = self.debug_recorder.snapshot()
        self.assertEqual(len(snapshot["inbound_events"]), 1)
        self.assertEqual(snapshot["inbound_events"][0]["reply_receive_id_type"], "chat_id")

    def test_p2p_message_sends_dm_project_card(self) -> None:
        self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
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
        self.assertEqual(len(self.message_client.sent_messages), 0)
        self.assertEqual(len(self.message_client.sent_cards), 1)
        sent = self.message_client.sent_cards[0]
        self.assertEqual(sent["receive_id_type"], "open_id")
        self.assertEqual(sent["receive_id"], "ou_demo_user")
        card = sent["card"]
        self.assertEqual(card["schema"], "2.0")
        self.assertEqual(card["header"]["title"]["content"], "PoCo Projects")
        new_button = card["body"]["elements"][1]
        manage_button = card["body"]["elements"][2]
        self.assertEqual(new_button["tag"], "button")
        self.assertEqual(new_button["behaviors"][0]["type"], "callback")
        self.assertEqual(new_button["behaviors"][0]["value"]["intent_key"], "project.new")
        self.assertEqual(manage_button["behaviors"][0]["value"]["intent_key"], "project.manage")
        snapshot = self.debug_recorder.snapshot()
        self.assertEqual(snapshot["outbound_attempts"][0]["source"], "gateway_dm_card")

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
        self.assertEqual(len(self.message_client.sent_cards), 0)

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
            task_controller=controller,
            card_renderer=FeishuCardRenderer(),
            debug_recorder=recorder,
        )
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
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_demo_chat",
        )
        self.workspace_controller.set_active_workdir(
            project,
            workdir="/srv/poco/api",
            source="manual",
        )
        payload = {
            "token": "verify-token",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_demo_user"}},
                "message": {
                    "chat_type": "group",
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
        self.assertEqual(len(self.message_client.sent_messages), 0)
        self.assertEqual(len(self.message_client.sent_cards), 2)
        self.assertEqual(len(self.dispatcher.actions), 1)
        action, task_id = self.dispatcher.actions[0]
        self.assertEqual(action, "start")
        self.assertEqual(task_id, response["task_id"])
        task = self.controller.get_task(task_id)
        self.assertEqual(task.project_id, project.id)
        self.assertEqual(task.effective_workdir, "/srv/poco/api")
        self.assertIsNotNone(task.notification_message_id)
        self.assertEqual(response["reply_preview"], "[card] task_status:created")

    def test_plain_group_message_dispatches_background_start(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_demo_chat",
        )
        self.workspace_controller.set_active_workdir(
            project,
            workdir="/srv/poco/api",
            source="manual",
        )
        payload = {
            "token": "verify-token",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_demo_user"}},
                "message": {
                    "chat_type": "group",
                    "chat_id": "oc_demo_chat",
                    "content": json.dumps({"text": "summarize the repository"}),
                },
            },
        }

        response = self.gateway.handle_event(
            payload,
            headers={},
            raw_body=json.dumps(payload).encode("utf-8"),
        )

        self.assertTrue(response["ok"])
        self.assertEqual(len(self.message_client.sent_messages), 0)
        self.assertEqual(len(self.message_client.sent_cards), 2)
        self.assertEqual(len(self.dispatcher.actions), 1)
        action, task_id = self.dispatcher.actions[0]
        self.assertEqual(action, "start")
        self.assertEqual(task_id, response["task_id"])
        task = self.controller.get_task(task_id)
        self.assertEqual(task.prompt, "summarize the repository")
        self.assertEqual(task.project_id, project.id)
        self.assertEqual(task.effective_workdir, "/srv/poco/api")
        self.assertIsNotNone(task.notification_message_id)
        self.assertEqual(response["reply_preview"], "[card] task_status:created")

    def test_group_message_recreates_missing_workspace_card(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_demo_chat",
        )
        payload = {
            "token": "verify-token",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_demo_user"}},
                "message": {
                    "chat_type": "group",
                    "chat_id": "oc_demo_chat",
                    "content": json.dumps({"text": "hello"}),
                },
            },
        }

        self.gateway.handle_event(
            payload,
            headers={},
            raw_body=json.dumps(payload).encode("utf-8"),
        )

        self.assertGreaterEqual(len(self.message_client.sent_cards), 2)
        updated_project = self.project_controller.get_project(project.id)
        self.assertIsNotNone(updated_project.workspace_message_id)

    def test_second_group_message_queues_when_first_is_still_active(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_demo_chat",
        )
        self.workspace_controller.set_active_workdir(
            project,
            workdir="/srv/poco/api",
            source="manual",
        )
        first_payload = {
            "token": "verify-token",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_demo_user"}},
                "message": {
                    "chat_type": "group",
                    "chat_id": "oc_demo_chat",
                    "content": json.dumps({"text": "first prompt"}),
                },
            },
        }
        second_payload = {
            "token": "verify-token",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_demo_user"}},
                "message": {
                    "chat_type": "group",
                    "chat_id": "oc_demo_chat",
                    "content": json.dumps({"text": "second prompt"}),
                },
            },
        }

        first = self.gateway.handle_event(
            first_payload,
            headers={},
            raw_body=json.dumps(first_payload).encode("utf-8"),
        )
        second = self.gateway.handle_event(
            second_payload,
            headers={},
            raw_body=json.dumps(second_payload).encode("utf-8"),
        )

        self.assertEqual(len(self.dispatcher.actions), 1)
        self.assertEqual(self.dispatcher.actions[0][0], "start")
        first_task = self.controller.get_task(first["task_id"])
        second_task = self.controller.get_task(second["task_id"])
        self.assertEqual(first_task.status.value, "created")
        self.assertEqual(second_task.status.value, "queued")
        self.assertEqual(second["reply_preview"], "[card] task_status:queued")

    def test_plain_group_message_persists_notification_message_id_with_sqlite_store(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            controller = TaskController(
                store=SqliteTaskStore(os.path.join(tempdir, "poco.db")),
                runner=StubAgentRunner(),
                session_controller=self.session_controller,
            )
            interaction = InteractionService(controller, session_controller=self.session_controller)
            gateway = FeishuGateway(
                interaction,
                request_verifier=FeishuRequestVerifier(verification_token="verify-token"),
                message_client=self.message_client,
                dispatcher=self.dispatcher,
                card_gateway=self.card_gateway,
                task_controller=controller,
                card_renderer=FeishuCardRenderer(),
                debug_recorder=self.debug_recorder,
                project_controller=self.project_controller,
                workspace_controller=self.workspace_controller,
            )
            project = self.project_controller.create_project(
                name="PoCo",
                created_by="ou_demo_user",
                backend="codex",
                group_chat_id="oc_demo_chat",
            )
            self.workspace_controller.set_active_workdir(
                project,
                workdir="/srv/poco/api",
                source="manual",
            )
            payload = {
                "token": "verify-token",
                "event": {
                    "sender": {"sender_id": {"open_id": "ou_demo_user"}},
                    "message": {
                        "chat_type": "group",
                        "chat_id": "oc_demo_chat",
                        "content": json.dumps({"text": "summarize the repository"}),
                    },
                },
            }

            response = gateway.handle_event(
                payload,
                headers={},
                raw_body=json.dumps(payload).encode("utf-8"),
            )

            task = controller.get_task(response["task_id"])
            self.assertEqual(task.notification_message_id, "om_2")

    def test_unknown_slash_command_in_group_returns_help_instead_of_task(self) -> None:
        self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_demo_chat",
        )
        payload = {
            "token": "verify-token",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_demo_user"}},
                "message": {
                    "chat_type": "group",
                    "chat_id": "oc_demo_chat",
                    "content": json.dumps({"text": "/unknown do something"}),
                },
            },
        }

        response = self.gateway.handle_event(
            payload,
            headers={},
            raw_body=json.dumps(payload).encode("utf-8"),
        )

        self.assertTrue(response["ok"])
        self.assertEqual(len(self.dispatcher.actions), 0)
        self.assertIsNone(response["task_id"])
        self.assertIn("Send any plain text message to create a task in this project.", response["reply_preview"])


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
