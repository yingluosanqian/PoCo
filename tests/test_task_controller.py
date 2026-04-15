from __future__ import annotations

import tempfile
import unittest

from poco.agent.runner import CodexCliRunner, StubAgentRunner
from poco.session.controller import SessionController
from poco.storage.memory import InMemorySessionStore, InMemoryTaskStore
from poco.task.controller import TaskController
from poco.task.models import Task
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

    def test_task_creation_inherits_backend_session_id_from_session(self) -> None:
        session = self.session_controller.create_session(
            project_id="proj_demo",
            created_by="ou_demo",
        )
        session.backend_session_id = "thread_123"
        self.session_controller._store.save(session)  # type: ignore[attr-defined]

        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="continue",
            source="feishu",
            project_id="proj_demo",
            session_id=session.id,
        )

        self.assertEqual(task.backend_session_id, "thread_123")

    def test_queue_task_marks_task_queued(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="summarize the repository",
            source="feishu",
            project_id="proj_demo",
        )

        queued = self.controller.queue_task(task.id)

        self.assertEqual(queued.status, TaskStatus.QUEUED)

    def test_claim_next_queued_task_promotes_oldest_task(self) -> None:
        first = self.controller.create_task(
            requester_id="ou_demo",
            prompt="first",
            source="feishu",
            project_id="proj_demo",
        )
        second = self.controller.create_task(
            requester_id="ou_demo",
            prompt="second",
            source="feishu",
            project_id="proj_demo",
        )
        self.controller.queue_task(first.id)
        self.controller.queue_task(second.id)

        claimed = self.controller.claim_next_queued_task("proj_demo")

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.id, first.id)
        self.assertEqual(claimed.status, TaskStatus.CREATED)

    def test_get_queue_count_and_position(self) -> None:
        first = self.controller.create_task(
            requester_id="ou_demo",
            prompt="first",
            source="feishu",
            project_id="proj_demo",
        )
        second = self.controller.create_task(
            requester_id="ou_demo",
            prompt="second",
            source="feishu",
            project_id="proj_demo",
        )

        self.controller.queue_task(first.id)
        self.controller.queue_task(second.id)

        self.assertEqual(self.controller.get_queue_count("proj_demo"), 2)
        self.assertEqual(self.controller.get_queue_position(first.id), 1)
        self.assertEqual(self.controller.get_queue_position(second.id), 2)

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

    def test_cancelling_running_task_preserves_existing_output(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="write the next section",
            source="feishu",
        )
        task.set_status(TaskStatus.RUNNING)
        task.append_live_output("partial streamed output")
        self.controller._store.save(task)  # type: ignore[attr-defined]

        cancelled = self.controller.cancel_task(task.id)

        self.assertEqual(cancelled.status, TaskStatus.CANCELLED)
        self.assertEqual(cancelled.raw_result, "partial streamed output")
        self.assertEqual(cancelled.live_output, "partial streamed output")

    def test_mark_task_failed_preserves_existing_output(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="write the next section",
            source="feishu",
        )
        task.set_status(TaskStatus.RUNNING)
        task.append_live_output("partial streamed output")
        self.controller._store.save(task)  # type: ignore[attr-defined]

        failed = self.controller.mark_task_failed(task.id, "network dropped")

        self.assertEqual(failed.status, TaskStatus.FAILED)
        self.assertEqual(failed.raw_result, "partial streamed output")
        self.assertIsNone(failed.live_output)

    def test_steer_task_records_event(self) -> None:
        class SteerRunner(StubAgentRunner):
            def steer(self, task: Task, prompt: str) -> tuple[bool, str]:
                self.last = (task.id, prompt)
                return True, "Steer sent to Codex."

        runner = SteerRunner()
        controller = TaskController(
            store=InMemoryTaskStore(),
            runner=runner,
            session_controller=self.session_controller,
        )
        task = controller.create_task(
            requester_id="ou_demo",
            prompt="stream output",
            source="feishu",
            agent_backend="codex",
            backend_session_id="thread_123",
        )
        task.set_status(TaskStatus.RUNNING)
        controller._store.save(task)  # type: ignore[attr-defined]

        updated = controller.steer_task(task.id, "Focus on the failing test first.")

        self.assertEqual(runner.last, (task.id, "Focus on the failing test first."))
        self.assertEqual(updated.events[-1].kind, "task_steered")
        self.assertEqual(updated.events[-1].message, "Steer sent to Codex.")

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
            self.assertEqual(task.effective_sandbox, "workspace-write")
            self.assertEqual(task.effective_workdir, tmpdir)

    def test_runner_updates_are_closed_when_store_save_raises(self) -> None:
        class ClosingRunner:
            name = "closing"

            def __init__(self) -> None:
                self.closed = False

            def is_ready(self):
                return True, "ok"

            def resolve_execution_context(self, task: Task):
                return None, task.effective_workdir, task.effective_sandbox

            def cancel(self, task_id: str) -> bool:
                return False

            def start(self, task: Task):
                try:
                    yield type(
                        "Update",
                        (),
                        {
                            "kind": "progress",
                            "message": "runner progress",
                            "output_chunk": "x",
                            "backend_session_id": None,
                        },
                    )()
                finally:
                    self.closed = True

            def resume_after_confirmation(self, task: Task):
                return self.start(task)

        class FailingStore(InMemoryTaskStore):
            def __init__(self) -> None:
                super().__init__()
                self.save_calls = 0

            def save(self, task):
                self.save_calls += 1
                if self.save_calls >= 3:
                    raise RuntimeError("save failed")
                return super().save(task)

        runner = ClosingRunner()
        controller = TaskController(
            store=FailingStore(),
            runner=runner,
            session_controller=self.session_controller,
        )
        task = controller.create_task(
            requester_id="ou_demo",
            prompt="stream output",
            source="feishu",
        )

        with self.assertRaisesRegex(RuntimeError, "save failed"):
            controller.start_task_execution(task.id)

        self.assertTrue(runner.closed)


if __name__ == "__main__":
    unittest.main()
