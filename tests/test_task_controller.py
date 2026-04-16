from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime

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

    def test_reconcile_task_execution_marks_orphan_running_task_failed(self) -> None:
        class InactiveRunner(StubAgentRunner):
            name = "cursor_agent"

            def is_task_active(self, task: Task) -> bool | None:
                return False

        controller = TaskController(
            store=InMemoryTaskStore(),
            runner=InactiveRunner(),
            session_controller=self.session_controller,
            running_reconcile_grace_seconds=0.0,
        )
        task = controller.create_task(
            requester_id="ou_demo",
            prompt="stream output",
            source="feishu",
            agent_backend="cursor_agent",
        )
        task.set_status(TaskStatus.RUNNING)
        controller._store.save(task)  # type: ignore[attr-defined]

        reconciled = controller.reconcile_task_execution(task.id)

        self.assertEqual(reconciled.status, TaskStatus.FAILED)
        self.assertEqual(
            reconciled.events[-1].message,
            "Task execution ended unexpectedly because the runner process is no longer active.",
        )

    def test_reconcile_task_execution_recovers_completed_task_from_streamed_output(self) -> None:
        class InactiveRunner(StubAgentRunner):
            def is_task_active(self, task: Task) -> bool | None:
                return False

        controller = TaskController(
            store=InMemoryTaskStore(),
            runner=InactiveRunner(),
            session_controller=self.session_controller,
            running_reconcile_grace_seconds=0.0,
        )
        task = controller.create_task(
            requester_id="ou_demo",
            prompt="stream output",
            source="feishu",
            project_id="proj_demo",
        )
        task.set_status(TaskStatus.RUNNING)
        task.append_live_output("final streamed answer")
        controller._store.save(task)  # type: ignore[attr-defined]

        reconciled = controller.reconcile_task_execution(task.id)

        self.assertEqual(reconciled.status, TaskStatus.COMPLETED)
        self.assertEqual(reconciled.raw_result, "final streamed answer")
        self.assertEqual(
            reconciled.events[-1].message,
            "Task completion was recovered from streamed output after the runner process became inactive.",
        )

    def test_reconcile_task_execution_keeps_recent_running_task_during_grace_period(self) -> None:
        class InactiveRunner(StubAgentRunner):
            name = "cursor_agent"

            def is_task_active(self, task: Task) -> bool | None:
                return False

        controller = TaskController(
            store=InMemoryTaskStore(),
            runner=InactiveRunner(),
            session_controller=self.session_controller,
            running_reconcile_grace_seconds=60.0,
        )
        task = controller.create_task(
            requester_id="ou_demo",
            prompt="stream output",
            source="feishu",
            agent_backend="cursor_agent",
        )
        task.set_status(TaskStatus.RUNNING)
        controller._store.save(task)  # type: ignore[attr-defined]

        reconciled = controller.reconcile_task_execution(task.id)

        self.assertEqual(reconciled.status, TaskStatus.RUNNING)

    def test_reconcile_project_execution_updates_all_orphan_running_tasks(self) -> None:
        class InactiveRunner(StubAgentRunner):
            def is_task_active(self, task: Task) -> bool | None:
                return False

        controller = TaskController(
            store=InMemoryTaskStore(),
            runner=InactiveRunner(),
            session_controller=self.session_controller,
            running_reconcile_grace_seconds=0.0,
        )
        first = controller.create_task(
            requester_id="ou_demo",
            prompt="first",
            source="feishu",
            project_id="proj_demo",
        )
        second = controller.create_task(
            requester_id="ou_demo",
            prompt="second",
            source="feishu",
            project_id="proj_demo",
        )
        first.set_status(TaskStatus.RUNNING)
        second.set_status(TaskStatus.RUNNING)
        controller._store.save(first)  # type: ignore[attr-defined]
        controller._store.save(second)  # type: ignore[attr-defined]

        reconciled = controller.reconcile_project_execution("proj_demo")

        self.assertEqual(len(reconciled), 2)
        self.assertTrue(all(task.status == TaskStatus.FAILED for task in reconciled))

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

    def test_progress_without_output_still_triggers_callback(self) -> None:
        class ProgressRunner:
            name = "progress"

            def is_ready(self):
                return True, "ok"

            def steer(self, task: Task, prompt: str):
                return False, "unsupported"

            def resolve_execution_context(self, task: Task):
                return None, task.effective_workdir, task.effective_sandbox

            def cancel(self, task_id: str) -> bool:
                return False

            def start(self, task: Task):
                yield type(
                    "Update",
                    (),
                    {
                        "kind": "progress",
                        "message": "Codex is thinking.",
                        "output_chunk": None,
                        "backend_session_id": "thread_123",
                    },
                )()
                yield type(
                    "Update",
                    (),
                    {
                        "kind": "completed",
                        "message": "done",
                        "raw_result": "final answer",
                        "backend_session_id": "thread_123",
                    },
                )()

            def resume_after_confirmation(self, task: Task):
                return self.start(task)

        controller = TaskController(
            store=InMemoryTaskStore(),
            runner=ProgressRunner(),
            session_controller=self.session_controller,
        )
        task = controller.create_task(
            requester_id="ou_demo",
            prompt="stream output",
            source="feishu",
        )
        seen: list[tuple[TaskStatus, str, str | None]] = []

        completed = controller.start_task_execution_with_callback(
            task.id,
            on_update=lambda current: seen.append(
                (
                    current.status,
                    current.events[-1].message,
                    current.backend_session_id,
                )
            ),
        )

        self.assertEqual(completed.status, TaskStatus.COMPLETED)
        self.assertGreaterEqual(len(seen), 2)
        self.assertIn((TaskStatus.RUNNING, "Codex is thinking.", "thread_123"), seen)

    def test_callback_exception_does_not_abort_task_completion(self) -> None:
        class ProgressRunner:
            name = "progress"

            def is_ready(self):
                return True, "ok"

            def steer(self, task: Task, prompt: str):
                return False, "unsupported"

            def resolve_execution_context(self, task: Task):
                return None, task.effective_workdir, task.effective_sandbox

            def cancel(self, task_id: str) -> bool:
                return False

            def start(self, task: Task):
                yield type(
                    "Update",
                    (),
                    {
                        "kind": "progress",
                        "message": "still running",
                        "output_chunk": "hi",
                        "backend_session_id": None,
                    },
                )()
                yield type(
                    "Update",
                    (),
                    {
                        "kind": "completed",
                        "message": "done",
                        "raw_result": "done",
                        "backend_session_id": None,
                    },
                )()

            def resume_after_confirmation(self, task: Task):
                return self.start(task)

        controller = TaskController(
            store=InMemoryTaskStore(),
            runner=ProgressRunner(),
            session_controller=self.session_controller,
        )
        task = controller.create_task(
            requester_id="ou_demo",
            prompt="stream output",
            source="feishu",
        )

        completed = controller.start_task_execution_with_callback(
            task.id,
            on_update=lambda current: (_ for _ in ()).throw(RuntimeError("notify failed")),
        )

        self.assertEqual(completed.status, TaskStatus.COMPLETED)
        self.assertEqual(completed.raw_result, "done")

    def test_list_known_backend_sessions_empty_history(self) -> None:
        self.assertEqual(self.controller.list_known_backend_sessions(backend="codex"), [])

    def test_list_known_backend_sessions_single_session(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="fix the api",
            source="feishu",
            agent_backend="codex",
            backend_session_id="thread_abc",
            project_id="proj_demo",
        )
        del task

        sessions = self.controller.list_known_backend_sessions(
            backend="codex",
            project_name_resolver=lambda _: "Demo",
        )

        self.assertEqual(len(sessions), 1)
        entry = sessions[0]
        self.assertEqual(entry.backend_session_id, "thread_abc")
        self.assertEqual(entry.project_id, "proj_demo")
        self.assertEqual(entry.project_name, "Demo")
        self.assertEqual(entry.first_prompt_preview, "fix the api")

    def test_list_known_backend_sessions_dedupes_multiple_tasks_same_id(self) -> None:
        first = self.controller.create_task(
            requester_id="ou_demo",
            prompt="first prompt",
            source="feishu",
            agent_backend="codex",
            backend_session_id="thread_abc",
            project_id="proj_demo",
        )
        first.created_at = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)
        first.updated_at = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)
        self.controller._store.save(first)  # type: ignore[attr-defined]

        second = self.controller.create_task(
            requester_id="ou_demo",
            prompt="second prompt",
            source="feishu",
            agent_backend="codex",
            backend_session_id="thread_abc",
            project_id="proj_demo",
        )
        second.created_at = datetime(2026, 4, 2, 10, 0, tzinfo=UTC)
        second.updated_at = datetime(2026, 4, 2, 10, 0, tzinfo=UTC)
        self.controller._store.save(second)  # type: ignore[attr-defined]

        sessions = self.controller.list_known_backend_sessions(backend="codex")

        self.assertEqual(len(sessions), 1)
        entry = sessions[0]
        self.assertEqual(entry.backend_session_id, "thread_abc")
        # first_prompt_preview comes from the FIRST (oldest) task
        self.assertEqual(entry.first_prompt_preview, "first prompt")
        self.assertEqual(entry.last_used_at, datetime(2026, 4, 2, 10, 0, tzinfo=UTC))

    def test_list_known_backend_sessions_sorted_by_recency(self) -> None:
        older = self.controller.create_task(
            requester_id="ou_demo",
            prompt="older session",
            source="feishu",
            agent_backend="codex",
            backend_session_id="thread_old",
            project_id="proj_demo",
        )
        older.updated_at = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)
        self.controller._store.save(older)  # type: ignore[attr-defined]

        newer = self.controller.create_task(
            requester_id="ou_demo",
            prompt="newer session",
            source="feishu",
            agent_backend="codex",
            backend_session_id="thread_new",
            project_id="proj_demo",
        )
        newer.updated_at = datetime(2026, 4, 10, 10, 0, tzinfo=UTC)
        self.controller._store.save(newer)  # type: ignore[attr-defined]

        sessions = self.controller.list_known_backend_sessions(backend="codex")

        self.assertEqual([s.backend_session_id for s in sessions], ["thread_new", "thread_old"])

    def test_list_known_backend_sessions_filters_by_backend(self) -> None:
        self.controller.create_task(
            requester_id="ou_demo",
            prompt="coco prompt",
            source="feishu",
            agent_backend="coco",
            backend_session_id="coco_thread",
            project_id="proj_demo",
        )
        self.controller.create_task(
            requester_id="ou_demo",
            prompt="codex prompt",
            source="feishu",
            agent_backend="codex",
            backend_session_id="codex_thread",
            project_id="proj_demo",
        )

        codex_only = self.controller.list_known_backend_sessions(backend="codex")
        coco_only = self.controller.list_known_backend_sessions(backend="coco")

        self.assertEqual([s.backend_session_id for s in codex_only], ["codex_thread"])
        self.assertEqual([s.backend_session_id for s in coco_only], ["coco_thread"])

    def test_list_known_backend_sessions_skips_tasks_without_backend_session_id(self) -> None:
        self.controller.create_task(
            requester_id="ou_demo",
            prompt="no session",
            source="feishu",
            agent_backend="codex",
            project_id="proj_demo",
        )

        sessions = self.controller.list_known_backend_sessions(backend="codex")

        self.assertEqual(sessions, [])


if __name__ == "__main__":
    unittest.main()
