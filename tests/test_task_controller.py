from __future__ import annotations

import unittest

from poco.agent.runner import StubAgentRunner
from poco.storage.memory import InMemoryTaskStore
from poco.task.controller import TaskController
from poco.task.models import TaskStatus


class TaskControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = TaskController(
            store=InMemoryTaskStore(),
            runner=StubAgentRunner(),
        )

    def test_run_command_without_confirmation_completes(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="summarize the repository",
            source="feishu",
        )
        self.assertEqual(task.agent_backend, "stub")
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertIsNotNone(task.result_summary)

    def test_confirm_prefix_moves_task_to_waiting_state(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="confirm: deploy the patch",
            source="feishu",
        )
        self.assertEqual(task.status, TaskStatus.WAITING_FOR_CONFIRMATION)
        self.assertIsNotNone(task.awaiting_confirmation_reason)

    def test_approving_waiting_task_completes_it(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="confirm: deploy the patch",
            source="feishu",
        )
        approved = self.controller.resolve_confirmation(task.id, approved=True)
        self.assertEqual(approved.status, TaskStatus.COMPLETED)
        self.assertIsNotNone(approved.result_summary)


if __name__ == "__main__":
    unittest.main()
