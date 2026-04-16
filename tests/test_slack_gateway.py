from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any

from poco.agent.runner import StubAgentRunner
from poco.interaction.card_dispatcher import CardActionDispatcher
from poco.interaction.card_handlers import ProjectIntentHandler, WorkspaceIntentHandler
from poco.interaction.service import InteractionService
from poco.platform.common.message_client import MessageSendResult
from poco.platform.slack.card_gateway import SlackCardActionGateway
from poco.platform.slack.cards import SlackCardRenderer
from poco.platform.slack.debug import SlackDebugRecorder
from poco.platform.slack.gateway import SlackGateway
from poco.project.controller import ProjectController
from poco.session.controller import SessionController
from poco.storage.memory import (
    InMemoryProjectStore,
    InMemorySessionStore,
    InMemoryTaskStore,
    InMemoryWorkspaceContextStore,
)
from poco.task.controller import TaskController
from poco.task.dispatcher import AsyncTaskDispatcher
from poco.workspace.controller import WorkspaceContextController


class FakeSlackClient:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []
        self.sent_cards: list[dict[str, Any]] = []
        self.updated_cards: list[dict[str, Any]] = []

    def send_text(
        self, *, receive_id: str, receive_id_type: str, text: str
    ) -> MessageSendResult:
        self.sent_messages.append(
            {
                "receive_id": receive_id,
                "receive_id_type": receive_id_type,
                "text": text,
            }
        )
        ts = f"1700000000.00000{len(self.sent_messages)}"
        return MessageSendResult(message_id=ts, channel=receive_id)

    def send_interactive(
        self, *, receive_id: str, receive_id_type: str, card: dict[str, Any]
    ) -> MessageSendResult:
        self.sent_cards.append(
            {
                "receive_id": receive_id,
                "receive_id_type": receive_id_type,
                "card": card,
            }
        )
        ts = f"1700000100.00000{len(self.sent_cards)}"
        return MessageSendResult(message_id=ts, channel=receive_id)

    def update_interactive(
        self,
        *,
        message_id: str,
        card: dict[str, Any],
        channel: str | None = None,
    ) -> MessageSendResult:
        self.updated_cards.append(
            {"message_id": message_id, "channel": channel, "card": card}
        )
        return MessageSendResult(message_id=message_id, channel=channel)


@dataclass
class FakeDispatcher(AsyncTaskDispatcher):
    actions: list[tuple] = field(default_factory=list)

    def dispatch_start(self, task_id: str) -> None:
        self.actions.append(("start", task_id))

    def dispatch_resume(self, task_id: str) -> None:
        self.actions.append(("resume", task_id))

    def dispatch_next_queued(self, project_id: str) -> None:
        self.actions.append(("next", project_id))

    def notify_task(self, task) -> None:  # type: ignore[no-untyped-def]
        self.actions.append(("notify", task.id, task.status.value))


def _build_gateway() -> tuple[SlackGateway, FakeSlackClient, SlackDebugRecorder, ProjectController, TaskController]:
    session_controller = SessionController(InMemorySessionStore())
    task_controller = TaskController(
        store=InMemoryTaskStore(),
        runner=StubAgentRunner(),
        session_controller=session_controller,
    )
    interaction = InteractionService(task_controller, session_controller=session_controller)
    client = FakeSlackClient()
    dispatcher = FakeDispatcher()
    debug_recorder = SlackDebugRecorder()
    project_controller = ProjectController(InMemoryProjectStore())
    workspace_controller = WorkspaceContextController(InMemoryWorkspaceContextStore())
    project_handler = ProjectIntentHandler(project_controller)
    workspace_handler = WorkspaceIntentHandler(
        project_controller,
        workspace_controller,
        session_controller=session_controller,
    )
    card_gateway = SlackCardActionGateway(
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
        renderer=SlackCardRenderer(),
        project_controller=project_controller,
        debug_recorder=debug_recorder,
    )
    gateway = SlackGateway(
        interaction,
        message_client=client,
        dispatcher=dispatcher,
        card_gateway=card_gateway,
        task_controller=task_controller,
        card_renderer=SlackCardRenderer(),
        debug_recorder=debug_recorder,
        project_controller=project_controller,
        workspace_controller=workspace_controller,
    )
    return gateway, client, debug_recorder, project_controller, task_controller


class SlackGatewayEventTest(unittest.TestCase):
    def test_url_verification_returns_challenge(self) -> None:
        gateway, *_ = _build_gateway()
        response = gateway.handle_event(
            {"type": "url_verification", "challenge": "abc123"}
        )
        self.assertEqual(response, {"challenge": "abc123"})

    def test_bot_message_is_ignored(self) -> None:
        gateway, client, *_ = _build_gateway()
        response = gateway.handle_event(
            {
                "event": {
                    "type": "message",
                    "channel": "C1",
                    "user": "U1",
                    "text": "hi",
                    "bot_id": "B999",
                }
            }
        )
        self.assertTrue(response["ignored"])
        self.assertEqual(response["reason"], "bot_message")
        self.assertEqual(len(client.sent_cards), 0)

    def test_message_changed_is_ignored(self) -> None:
        gateway, client, *_ = _build_gateway()
        response = gateway.handle_event(
            {
                "event": {
                    "type": "message",
                    "subtype": "message_changed",
                    "channel": "C1",
                    "user": "U1",
                }
            }
        )
        self.assertTrue(response["ignored"])
        self.assertEqual(len(client.sent_cards), 0)

    def test_dm_message_sends_project_list_card(self) -> None:
        gateway, client, recorder, project_controller, _ = _build_gateway()
        project_controller.create_project(
            name="PoCo", created_by="U1", backend="codex"
        )
        response = gateway.handle_event(
            {
                "event": {
                    "type": "message",
                    "channel": "D1",
                    "channel_type": "im",
                    "user": "U1",
                    "text": "/help",
                }
            }
        )
        self.assertTrue(response["ok"])
        self.assertTrue(response["delivered"])
        self.assertEqual(len(client.sent_cards), 1)
        card = client.sent_cards[0]
        self.assertEqual(card["receive_id"], "D1")
        self.assertEqual(card["receive_id_type"], "channel")
        self.assertEqual(card["card"]["blocks"][0]["type"], "header")
        snapshot = recorder.snapshot()
        self.assertEqual(snapshot["outbound_attempts"][0]["source"], "gateway_dm_card")

    def test_group_message_without_project_replies_with_text(self) -> None:
        gateway, client, *_ = _build_gateway()
        response = gateway.handle_event(
            {
                "event": {
                    "type": "message",
                    "channel": "C99",
                    "channel_type": "channel",
                    "user": "U1",
                    "text": "/help",
                }
            }
        )
        self.assertTrue(response["delivered"])
        self.assertEqual(len(client.sent_messages), 1)
        sent = client.sent_messages[0]
        self.assertEqual(sent["receive_id"], "C99")
        self.assertIn("not bound to a project", sent["text"])

    def test_group_message_for_bound_project_submits_task(self) -> None:
        gateway, client, _recorder, project_controller, task_controller = _build_gateway()
        project = project_controller.create_project(
            name="PoCo", created_by="U1", backend="codex"
        )
        project_controller.bind_group(project.id, "C_project")

        response = gateway.handle_event(
            {
                "event": {
                    "type": "message",
                    "channel": "C_project",
                    "channel_type": "channel",
                    "user": "U1",
                    "text": "investigate the crash",
                }
            }
        )
        self.assertTrue(response["ok"])
        self.assertIsNotNone(response["task_id"])
        # New tasks are handed to the dispatcher asynchronously; the
        # actual task-status card is posted by TaskNotifier, not the
        # gateway, so the gateway only dispatches "start" here.
        self.assertIn(("start", response["task_id"]), gateway._dispatcher.actions)
        # Workspace card bootstrap still fires because the project had no
        # workspace message bound before this event.
        self.assertGreaterEqual(len(client.sent_cards), 1)
        self.assertEqual(client.sent_cards[0]["receive_id"], "C_project")

        task = task_controller.get_task(response["task_id"])
        self.assertEqual(task.project_id, project.id)
        self.assertEqual(task.prompt, "investigate the crash")

    def test_workspace_bootstrap_posts_card_on_first_group_message(self) -> None:
        gateway, client, _recorder, project_controller, _ = _build_gateway()
        project = project_controller.create_project(
            name="PoCo", created_by="U1", backend="codex"
        )
        project_controller.bind_group(project.id, "C_project")

        gateway.handle_event(
            {
                "event": {
                    "type": "message",
                    "channel": "C_project",
                    "channel_type": "channel",
                    "user": "U1",
                    "text": "run things",
                }
            }
        )
        # First interactive send should be the workspace card.
        self.assertGreaterEqual(len(client.sent_cards), 1)
        first_card = client.sent_cards[0]
        self.assertEqual(first_card["receive_id"], "C_project")
        refreshed = project_controller.get_project(project.id)
        self.assertTrue(refreshed.workspace_message_id)
        self.assertEqual(refreshed.workspace_message_channel, "C_project")

    def test_non_message_event_is_ignored(self) -> None:
        gateway, client, *_ = _build_gateway()
        response = gateway.handle_event(
            {"event": {"type": "reaction_added"}}
        )
        self.assertTrue(response["ignored"])
        self.assertEqual(len(client.sent_cards), 0)


class SlackGatewaySlashCommandTest(unittest.TestCase):
    def test_unknown_command_returns_ephemeral_error(self) -> None:
        gateway, *_ = _build_gateway()
        response = gateway.handle_slash_command(
            {"command": "/nope", "user_id": "U1"}
        )
        self.assertEqual(response["response_type"], "ephemeral")
        self.assertIn("Unknown command", response["text"])

    def test_poco_command_renders_project_list_blocks(self) -> None:
        gateway, _client, _recorder, project_controller, _ = _build_gateway()
        project_controller.create_project(
            name="PoCo", created_by="U1", backend="codex"
        )
        response = gateway.handle_slash_command(
            {"command": "/poco", "user_id": "U1"}
        )
        self.assertEqual(response["response_type"], "ephemeral")
        self.assertTrue(response["blocks"])
        self.assertEqual(response["blocks"][0]["type"], "header")


if __name__ == "__main__":
    unittest.main()
