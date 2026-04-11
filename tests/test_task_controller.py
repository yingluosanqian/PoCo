from __future__ import annotations

import tempfile
import unittest

from poco.agent.runner import CodexCliRunner, StubAgentRunner
from poco.session.controller import SessionController
from poco.storage.memory import InMemorySessionStore, InMemoryTaskStore
from poco.task.controller import TaskController
from poco.task.models import TaskStatus


class TaskControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session_controller = SessionController(InMemorySessionStore())
        self.controller = TaskController(
            store=InMemoryTaskStore(),
            runner=StubAgentRunner(),
            session_controller=self.session_controller,
        )

    def test_run_command_without_confirmation_completes(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="summarize the repository",
            source="feishu",
        )
        task = self.controller.start_task_execution(task.id)
        self.assertEqual(task.agent_backend, "stub")
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertIsNotNone(task.result_summary)

    def test_task_creation_preserves_project_workdir_context(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="summarize the repository",
            source="feishu",
            project_id="proj_demo",
            effective_workdir="/srv/poco/api",
        )
        self.assertEqual(task.project_id, "proj_demo")
        self.assertEqual(task.effective_workdir, "/srv/poco/api")

    def test_task_creation_updates_session_summary(self) -> None:
        session = self.session_controller.create_session(
            project_id="proj_demo",
            created_by="ou_demo",
        )
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="summarize the repository",
            source="feishu",
            project_id="proj_demo",
            session_id=session.id,
        )
        updated = self.session_controller.get_session(session.id)
        self.assertEqual(task.session_id, session.id)
        self.assertEqual(updated.latest_task_id, task.id)

    def test_confirm_prefix_moves_task_to_waiting_state(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="confirm: deploy the patch",
            source="feishu",
        )
        task = self.controller.start_task_execution(task.id)
        self.assertEqual(task.status, TaskStatus.WAITING_FOR_CONFIRMATION)
        self.assertIsNotNone(task.awaiting_confirmation_reason)

    def test_approving_waiting_task_completes_it(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="confirm: deploy the patch",
            source="feishu",
        )
        task = self.controller.start_task_execution(task.id)
        approved = self.controller.resolve_confirmation(task.id, approved=True)
        approved = self.controller.resume_task_execution(approved.id)
        self.assertEqual(approved.status, TaskStatus.COMPLETED)
        self.assertIsNotNone(approved.result_summary)

    def test_cancelling_waiting_task_marks_it_cancelled(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="confirm: deploy the patch",
            source="feishu",
        )
        task = self.controller.start_task_execution(task.id)

        cancelled = self.controller.cancel_task(task.id)

        self.assertEqual(cancelled.status, TaskStatus.CANCELLED)
        self.assertIsNone(cancelled.awaiting_confirmation_reason)

    def test_codex_task_creation_resolves_default_execution_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = TaskController(
                store=InMemoryTaskStore(),
                runner=CodexCliRunner(
                    command="codex",
                    workdir=tmpdir,
                    model="gpt-5.4",
                ),
                session_controller=self.session_controller,
            )

            task = controller.create_task(
                requester_id="ou_demo",
                prompt="summarize the repository",
                source="feishu",
            )

            self.assertEqual(task.effective_model, "gpt-5.4")
            self.assertEqual(task.effective_workdir, tmpdir)


if __name__ == "__main__":
    unittest.main()
