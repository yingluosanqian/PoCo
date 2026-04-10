from __future__ import annotations

import unittest

from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.project.controller import ProjectController
from poco.project.models import Project
from poco.storage.memory import InMemoryProjectStore, InMemoryWorkspaceContextStore
from poco.task.models import Task, TaskStatus
from poco.task.notifier import FeishuTaskNotifier
from poco.workspace.controller import WorkspaceContextController


class FakeMessageClient:
    def __init__(self) -> None:
        self.sent_texts: list[dict[str, object]] = []
        self.sent_cards: list[dict[str, object]] = []
        self.updated_cards: list[dict[str, object]] = []

    def send_text(self, *, receive_id: str, receive_id_type: str, text: str) -> None:
        self.sent_texts.append(
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
            {"message_id": "om_task_status_1"},
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


class FeishuTaskNotifierTest(unittest.TestCase):
    def test_waiting_task_sends_interactive_card(self) -> None:
        client = FakeMessageClient()
        recorder = FeishuDebugRecorder()
        notifier = FeishuTaskNotifier(client, debug_recorder=recorder)  # type: ignore[arg-type]
        task = Task(
            id="task_wait",
            requester_id="ou_demo",
            prompt="confirm: deploy",
            source="feishu_card",
            agent_backend="codex",
            project_id="proj_1",
            effective_workdir="/srv/poco/api",
            reply_receive_id="oc_group_1",
            reply_receive_id_type="chat_id",
            status=TaskStatus.WAITING_FOR_CONFIRMATION,
            awaiting_confirmation_reason="Need explicit approval.",
        )

        notifier.notify_task(task)

        self.assertEqual(len(client.sent_cards), 1)
        self.assertEqual(len(client.sent_texts), 0)
        self.assertEqual(task.notification_message_id, "om_task_status_1")
        card = client.sent_cards[0]["card"]
        self.assertEqual(card["header"]["title"]["content"], "Task: task_wait")
        approve_button = card["body"]["elements"][6]
        self.assertEqual(approve_button["behaviors"][0]["value"]["intent_key"], "task.approve")
        snapshot = recorder.snapshot()
        self.assertEqual(snapshot["outbound_attempts"][0]["text_preview"], "[card] task_status:waiting_for_confirmation")

    def test_completed_task_sends_result_card(self) -> None:
        client = FakeMessageClient()
        notifier = FeishuTaskNotifier(client)  # type: ignore[arg-type]
        task = Task(
            id="task_done",
            requester_id="ou_demo",
            prompt="summarize",
            source="feishu_card",
            agent_backend="codex",
            project_id="proj_1",
            effective_workdir="/srv/poco/api",
            reply_receive_id="oc_group_1",
            reply_receive_id_type="chat_id",
            status=TaskStatus.COMPLETED,
            raw_result="Done.",
        )

        notifier.notify_task(task)

        self.assertEqual(len(client.sent_cards), 1)
        card = client.sent_cards[0]["card"]
        self.assertEqual(card["header"]["title"]["content"], "Task: task_done")
        result_block = card["body"]["elements"][6]
        self.assertIn("Done.", result_block["text"]["content"])

    def test_second_notification_updates_existing_task_card(self) -> None:
        client = FakeMessageClient()
        recorder = FeishuDebugRecorder()
        notifier = FeishuTaskNotifier(client, debug_recorder=recorder)  # type: ignore[arg-type]
        task = Task(
            id="task_update",
            requester_id="ou_demo",
            prompt="confirm: deploy",
            source="feishu_card",
            agent_backend="codex",
            project_id="proj_1",
            effective_workdir="/srv/poco/api",
            reply_receive_id="oc_group_1",
            reply_receive_id_type="chat_id",
            status=TaskStatus.WAITING_FOR_CONFIRMATION,
            awaiting_confirmation_reason="Need explicit approval.",
        )

        notifier.notify_task(task)
        task.awaiting_confirmation_reason = None
        task.set_status(TaskStatus.COMPLETED)
        task.set_result("Done.")
        notifier.notify_task(task)

        self.assertEqual(len(client.sent_cards), 1)
        self.assertEqual(len(client.updated_cards), 1)
        self.assertEqual(client.updated_cards[0]["message_id"], "om_task_status_1")
        snapshot = recorder.snapshot()
        self.assertEqual(snapshot["outbound_attempts"][0]["source"], "task_notifier_update")

    def test_task_notification_also_updates_bound_workspace_card(self) -> None:
        client = FakeMessageClient()
        recorder = FeishuDebugRecorder()
        project_controller = ProjectController(InMemoryProjectStore())
        workspace_controller = WorkspaceContextController(InMemoryWorkspaceContextStore())
        project = project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_group_1",
        )
        project_controller.bind_workspace_message(project.id, "om_workspace_1")
        workspace_controller.set_active_workdir(
            project,
            workdir="/srv/poco/api",
            source="preset",
        )
        notifier = FeishuTaskNotifier(
            client,  # type: ignore[arg-type]
            project_controller=project_controller,
            workspace_controller=workspace_controller,
            debug_recorder=recorder,
        )
        task = Task(
            id="task_workspace_sync",
            requester_id="ou_demo",
            prompt="confirm: deploy",
            source="feishu_card",
            agent_backend="codex",
            project_id=project.id,
            effective_workdir="/srv/poco/api",
            reply_receive_id="oc_group_1",
            reply_receive_id_type="chat_id",
            status=TaskStatus.WAITING_FOR_CONFIRMATION,
            awaiting_confirmation_reason="Need explicit approval.",
        )

        notifier.notify_task(task)

        self.assertEqual(len(client.sent_cards), 1)
        self.assertEqual(len(client.updated_cards), 1)
        self.assertEqual(client.updated_cards[0]["message_id"], "om_workspace_1")
        snapshot = recorder.snapshot()
        self.assertEqual(snapshot["outbound_attempts"][0]["source"], "workspace_notifier_update")


if __name__ == "__main__":
    unittest.main()
