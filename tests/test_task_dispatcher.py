from __future__ import annotations

import unittest

from poco.agent.runner import StubAgentRunner
from poco.storage.memory import InMemoryTaskStore
from poco.task.controller import TaskController
from poco.task.dispatcher import AsyncTaskDispatcher
from poco.task.models import Task


class FakeNotifier:
    def __init__(self) -> None:
        self.tasks: list[Task] = []

    def notify_task(self, task: Task) -> None:
        self.tasks.append(task)


class InlineDispatcher(AsyncTaskDispatcher):
    def _launch(self, target) -> None:  # type: ignore[no-untyped-def]
        target()


class TaskDispatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = TaskController(
            store=InMemoryTaskStore(),
            runner=StubAgentRunner(),
        )
        self.notifier = FakeNotifier()
        self.dispatcher = InlineDispatcher(self.controller, notifier=self.notifier)

    def test_dispatch_start_completes_and_notifies_terminal_task(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="summarize the repository",
            source="feishu",
            reply_receive_id="oc_demo_chat",
            reply_receive_id_type="chat_id",
        )
        self.dispatcher.dispatch_start(task.id)
        updated = self.controller.get_task(task.id)
        self.assertEqual(updated.status.value, "completed")
        self.assertEqual(len(self.notifier.tasks), 1)
        self.assertEqual(self.notifier.tasks[0].id, task.id)

    def test_dispatch_start_waiting_for_confirmation_notifies(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="confirm: deploy the patch",
            source="feishu",
            reply_receive_id="oc_demo_chat",
            reply_receive_id_type="chat_id",
        )
        self.dispatcher.dispatch_start(task.id)
        updated = self.controller.get_task(task.id)
        self.assertEqual(updated.status.value, "waiting_for_confirmation")
        self.assertEqual(len(self.notifier.tasks), 1)

    def test_dispatch_resume_completes_after_approval(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="confirm: deploy the patch",
            source="feishu",
            reply_receive_id="oc_demo_chat",
            reply_receive_id_type="chat_id",
        )
        self.dispatcher.dispatch_start(task.id)
        self.controller.resolve_confirmation(task.id, approved=True)
        self.dispatcher.dispatch_resume(task.id)
        updated = self.controller.get_task(task.id)
        self.assertEqual(updated.status.value, "completed")
        self.assertEqual(len(self.notifier.tasks), 2)


if __name__ == "__main__":
    unittest.main()
