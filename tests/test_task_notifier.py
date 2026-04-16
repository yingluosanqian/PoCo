from __future__ import annotations

import os
import tempfile
import unittest

from poco.interaction.card_models import Surface
from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.project.controller import ProjectController
from poco.project.models import Project
from poco.storage.memory import InMemoryProjectStore, InMemoryWorkspaceContextStore
from poco.storage.sqlite import SqliteTaskStore
from poco.task.controller import TaskController
from poco.task.models import Task, TaskStatus
from poco.task.notifier import FeishuTaskNotifier
from poco.agent.runner import StubAgentRunner
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


class FailingUpdateMessageClient(FakeMessageClient):
    def update_interactive(
        self,
        *,
        message_id: str,
        card: dict[str, object],
    ) -> None:
        raise RuntimeError("update failed")


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
            reply_surface=Surface.GROUP,
            status=TaskStatus.WAITING_FOR_CONFIRMATION,
            awaiting_confirmation_reason="Need explicit approval.",
        )

        notifier.notify_task(task)

        self.assertEqual(len(client.sent_cards), 1)
        self.assertEqual(len(client.sent_texts), 0)
        self.assertEqual(task.notification_message_id, "om_task_status_1")
        card = client.sent_cards[0]["card"]
        self.assertEqual(
            card["header"]["title"]["content"],
            "[Waiting] Task: task_wait (codex, /srv/poco/api)",
        )
        approve_button = card["body"]["elements"][1]
        self.assertEqual(approve_button["behaviors"][0]["value"]["intent_key"], "task.approve")
        self.assertEqual(card["body"]["elements"][2]["behaviors"][0]["value"]["intent_key"], "task.stop")
        snapshot = recorder.snapshot()
        self.assertEqual(snapshot["outbound_attempts"][0]["text_preview"], "[card] task_status:waiting_for_confirmation")

    def test_running_task_sends_interactive_card_with_live_output(self) -> None:
        client = FakeMessageClient()
        notifier = FeishuTaskNotifier(client)  # type: ignore[arg-type]
        task = Task(
            id="task_running",
            requester_id="ou_demo",
            prompt="build",
            source="feishu_card",
            agent_backend="codex",
            project_id="proj_1",
            effective_workdir="/srv/poco/api",
            reply_receive_id="oc_group_1",
            reply_surface=Surface.GROUP,
            status=TaskStatus.RUNNING,
            live_output="line 1\nline 2",
        )

        notifier.notify_task(task)

        self.assertEqual(len(client.sent_cards), 1)
        card = client.sent_cards[0]["card"]
        self.assertEqual(
            card["header"]["title"]["content"],
            "[Running] Task: task_running (codex, /srv/poco/api)",
        )
        live_block = card["body"]["elements"][0]
        self.assertEqual(live_block["tag"], "markdown")
        self.assertIn("line 1", live_block["content"])
        self.assertEqual(card["body"]["elements"][1]["behaviors"][0]["value"]["intent_key"], "task.stop")

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
            reply_surface=Surface.GROUP,
            status=TaskStatus.COMPLETED,
            raw_result="Done.",
        )

        notifier.notify_task(task)

        self.assertEqual(len(client.sent_cards), 1)
        card = client.sent_cards[0]["card"]
        self.assertEqual(
            card["header"]["title"]["content"],
            "[Complete] Task: task_done (codex, /srv/poco/api)",
        )
        result_block = card["body"]["elements"][0]
        action_row = card["body"]["elements"][1]
        change_workdir_button = action_row["columns"][0]["elements"][0]
        change_model_button = action_row["columns"][1]["elements"][0]
        self.assertEqual(result_block["tag"], "markdown")
        self.assertIn("Done.", result_block["content"])
        self.assertEqual(change_workdir_button["behaviors"][0]["value"]["intent_key"], "workspace.enter_path")
        self.assertEqual(change_model_button["behaviors"][0]["value"]["intent_key"], "workspace.choose_agent")

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
            reply_surface=Surface.GROUP,
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

    def test_running_updates_are_forwarded_without_time_throttling(self) -> None:
        client = FakeMessageClient()
        notifier = FeishuTaskNotifier(client)  # type: ignore[arg-type]
        task = Task(
            id="task_running_updates",
            requester_id="ou_demo",
            prompt="build",
            source="feishu_card",
            agent_backend="codex",
            project_id="proj_1",
            effective_workdir="/srv/poco/api",
            notification_message_id="om_task_status_1",
            reply_receive_id="oc_group_1",
            reply_surface=Surface.GROUP,
            status=TaskStatus.RUNNING,
            live_output="line 1",
        )

        notifier.notify_task(task)
        task.append_live_output("\nline 2")
        notifier.notify_task(task)

        self.assertEqual(len(client.sent_cards), 0)
        self.assertEqual(len(client.updated_cards), 2)
        self.assertEqual(client.updated_cards[0]["message_id"], "om_task_status_1")
        self.assertEqual(client.updated_cards[1]["message_id"], "om_task_status_1")
        self.assertIn("line 2", client.updated_cards[1]["card"]["body"]["elements"][0]["content"])

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
            reply_surface=Surface.GROUP,
            status=TaskStatus.WAITING_FOR_CONFIRMATION,
            awaiting_confirmation_reason="Need explicit approval.",
        )

        notifier.notify_task(task)

        self.assertEqual(len(client.sent_cards), 1)
        self.assertEqual(len(client.updated_cards), 1)
        self.assertEqual(client.updated_cards[0]["message_id"], "om_workspace_1")
        snapshot = recorder.snapshot()
        self.assertEqual(snapshot["outbound_attempts"][0]["source"], "workspace_notifier_update")

    def test_running_stream_updates_do_not_resync_workspace_card_every_chunk(self) -> None:
        client = FakeMessageClient()
        project_controller = ProjectController(InMemoryProjectStore())
        workspace_controller = WorkspaceContextController(InMemoryWorkspaceContextStore())
        project = project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_group_1",
        )
        project_controller.bind_workspace_message(project.id, "om_workspace_1")
        notifier = FeishuTaskNotifier(
            client,  # type: ignore[arg-type]
            project_controller=project_controller,
            workspace_controller=workspace_controller,
        )
        task = Task(
            id="task_running_workspace",
            requester_id="ou_demo",
            prompt="build",
            source="feishu_group_message",
            agent_backend="codex",
            project_id=project.id,
            effective_workdir="/srv/poco/api",
            notification_message_id="om_existing_card",
            reply_receive_id="oc_group_1",
            reply_surface=Surface.GROUP,
            status=TaskStatus.RUNNING,
            live_output="line 1",
        )

        notifier.notify_task(task)
        task.append_live_output("\nline 2")
        notifier.notify_task(task)

        self.assertEqual(
            [item["message_id"] for item in client.updated_cards],
            ["om_existing_card", "om_workspace_1", "om_existing_card"],
        )

    def test_running_update_failure_does_not_fallback_to_new_card(self) -> None:
        client = FailingUpdateMessageClient()
        recorder = FeishuDebugRecorder()
        notifier = FeishuTaskNotifier(client, debug_recorder=recorder)  # type: ignore[arg-type]
        task = Task(
            id="task_running_existing_card",
            requester_id="ou_demo",
            prompt="build",
            source="feishu_group_message",
            agent_backend="codex",
            project_id="proj_1",
            effective_workdir="/srv/poco/api",
            notification_message_id="om_existing_card",
            reply_receive_id="oc_group_1",
            reply_surface=Surface.GROUP,
            status=TaskStatus.RUNNING,
            live_output="streaming line",
        )

        notifier.notify_task(task)

        self.assertEqual(len(client.sent_cards), 0)
        snapshot = recorder.snapshot()
        self.assertEqual(snapshot["errors"][0]["stage"], "task_notifier_update")

    def test_workspace_update_failure_bootstraps_new_workspace_card(self) -> None:
        client = FailingUpdateMessageClient()
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
        notifier = FeishuTaskNotifier(
            client,  # type: ignore[arg-type]
            project_controller=project_controller,
            workspace_controller=workspace_controller,
            debug_recorder=recorder,
        )
        task = Task(
            id="task_workspace_restore",
            requester_id="ou_demo",
            prompt="summarize",
            source="feishu_card",
            agent_backend="codex",
            project_id=project.id,
            effective_workdir="/srv/poco/api",
            reply_receive_id="oc_group_1",
            reply_surface=Surface.GROUP,
            status=TaskStatus.COMPLETED,
            raw_result="Done.",
        )

        notifier.notify_task(task)

        self.assertEqual(len(client.sent_cards), 2)
        refreshed = project_controller.get_project(project.id)
        self.assertEqual(refreshed.workspace_message_id, "om_task_status_1")

    def test_notification_message_id_is_persisted_for_sqlite_backed_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            controller = TaskController(
                store=SqliteTaskStore(os.path.join(tempdir, "poco.db")),
                runner=StubAgentRunner(),
            )
            client = FakeMessageClient()
            notifier = FeishuTaskNotifier(
                client,  # type: ignore[arg-type]
                task_controller=controller,
            )
            task = controller.create_task(
                requester_id="ou_demo",
                prompt="confirm: deploy",
                source="feishu_card",
                project_id="proj_1",
                effective_workdir="/srv/poco/api",
                reply_receive_id="oc_group_1",
                reply_surface=Surface.GROUP,
            )
            task.set_status(TaskStatus.WAITING_FOR_CONFIRMATION)
            task.awaiting_confirmation_reason = "Need explicit approval."
            controller._store.save(task)  # type: ignore[attr-defined]

            notifier.notify_task(controller.get_task(task.id))
            reloaded = controller.get_task(task.id)
            self.assertEqual(reloaded.notification_message_id, "om_task_status_1")

            reloaded.awaiting_confirmation_reason = None
            reloaded.set_status(TaskStatus.COMPLETED)
            reloaded.set_result("Done.")
            controller._store.save(reloaded)  # type: ignore[attr-defined]
            notifier.notify_task(controller.get_task(task.id))

            self.assertEqual(len(client.sent_cards), 1)
            self.assertEqual(len(client.updated_cards), 1)

    def test_stale_running_snapshot_does_not_override_completed_card(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            controller = TaskController(
                store=SqliteTaskStore(os.path.join(tempdir, "poco.db")),
                runner=StubAgentRunner(),
            )
            client = FakeMessageClient()
            notifier = FeishuTaskNotifier(
                client,  # type: ignore[arg-type]
                task_controller=controller,
            )
            task = controller.create_task(
                requester_id="ou_demo",
                prompt="write a report",
                source="feishu_group_message",
                project_id="proj_1",
                effective_workdir="/srv/poco/api",
                reply_receive_id="oc_group_1",
                reply_surface=Surface.GROUP,
                notification_message_id="om_existing_card",
            )
            stale_running = controller.get_task(task.id)
            stale_running.set_status(TaskStatus.RUNNING)
            stale_running.append_live_output("partial output")
            controller._store.save(stale_running)  # type: ignore[attr-defined]

            completed = controller.get_task(task.id)
            completed.set_result("Done.")
            completed.clear_live_output()
            completed.set_status(TaskStatus.COMPLETED)
            controller._store.save(completed)  # type: ignore[attr-defined]

            notifier.notify_task(stale_running)

            self.assertEqual(len(client.sent_cards), 0)
            self.assertEqual(len(client.updated_cards), 1)
            card = client.updated_cards[0]["card"]
            self.assertEqual(
                card["header"]["title"]["content"],
                f"[Complete] Task: {task.id} (stub, /srv/poco/api)",
            )


if __name__ == "__main__":
    unittest.main()
