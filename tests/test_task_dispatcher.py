from __future__ import annotations

from copy import deepcopy
from threading import Event
from threading import Thread
from time import sleep
import unittest

from poco.agent.runner import AgentRunUpdate, StubAgentRunner
from poco.interaction.card_models import Surface
from poco.storage.memory import InMemoryTaskStore
from poco.task.controller import TaskController
from poco.task.dispatcher import AsyncTaskDispatcher
from poco.task.models import Task
from poco.task.models import TaskStatus


class FakeNotifier:
    def __init__(self) -> None:
        self.tasks: list[Task] = []

    def notify_task(self, task: Task) -> None:
        self.tasks.append(deepcopy(task))


class InlineDispatcher(AsyncTaskDispatcher):
    def _launch(self, target) -> None:  # type: ignore[no-untyped-def]
        target()


class GatedRunningDispatcher(AsyncTaskDispatcher):
    def __init__(self, controller: TaskController, *, notifier: FakeNotifier, gate: Event) -> None:
        super().__init__(controller, notifier=notifier)
        self._gate = gate

    def _drain_running_notifications(self, task_id: str) -> None:
        self._gate.wait(timeout=1)
        super()._drain_running_notifications(task_id)


class StreamingRunner:
    name = "codex"

    def is_ready(self) -> tuple[bool, str]:
        return True, "ready"

    def resolve_execution_context(self, task: Task) -> tuple[str | None, str | None, str | None]:
        return task.effective_model, task.effective_workdir, task.effective_sandbox

    def start(self, task: Task):
        yield AgentRunUpdate(
            kind="progress",
            message="streaming",
            output_chunk="line 1\n",
        )
        yield AgentRunUpdate(
            kind="completed",
            message="done",
            raw_result="line 1\nfinal result",
        )

    def resume_after_confirmation(self, task: Task):
        return iter(())


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
            reply_surface=Surface.GROUP,
        )
        self.dispatcher.dispatch_start(task.id)
        updated = self.controller.get_task(task.id)
        self.assertEqual(updated.status.value, "completed")
        self.assertGreaterEqual(len(self.notifier.tasks), 2)
        self.assertEqual(self.notifier.tasks[0].status.value, "running")
        self.assertEqual(self.notifier.tasks[-1].status.value, "completed")
        self.assertEqual(self.notifier.tasks[-1].id, task.id)

    def test_dispatch_start_waiting_for_confirmation_notifies(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="confirm: deploy the patch",
            source="feishu",
            reply_receive_id="oc_demo_chat",
            reply_surface=Surface.GROUP,
        )
        self.dispatcher.dispatch_start(task.id)
        updated = self.controller.get_task(task.id)
        self.assertEqual(updated.status.value, "waiting_for_confirmation")
        self.assertGreaterEqual(len(self.notifier.tasks), 2)
        self.assertEqual(self.notifier.tasks[0].status.value, "running")
        self.assertEqual(self.notifier.tasks[-1].status.value, "waiting_for_confirmation")

    def test_dispatch_resume_completes_after_approval(self) -> None:
        task = self.controller.create_task(
            requester_id="ou_demo",
            prompt="confirm: deploy the patch",
            source="feishu",
            reply_receive_id="oc_demo_chat",
            reply_surface=Surface.GROUP,
        )
        self.dispatcher.dispatch_start(task.id)
        self.controller.resolve_confirmation(task.id, approved=True)
        self.dispatcher.dispatch_resume(task.id)
        updated = self.controller.get_task(task.id)
        self.assertEqual(updated.status.value, "completed")
        self.assertGreaterEqual(len(self.notifier.tasks), 2)

    def test_dispatch_start_notifies_running_stream_updates(self) -> None:
        controller = TaskController(
            store=InMemoryTaskStore(),
            runner=StreamingRunner(),
        )
        notifier = FakeNotifier()
        dispatcher = InlineDispatcher(controller, notifier=notifier)
        task = controller.create_task(
            requester_id="ou_demo",
            prompt="stream output",
            source="feishu",
            reply_receive_id="oc_demo_chat",
            reply_surface=Surface.GROUP,
        )

        dispatcher.dispatch_start(task.id)

        updated = controller.get_task(task.id)
        self.assertEqual(updated.status.value, "completed")
        self.assertGreaterEqual(len(notifier.tasks), 2)
        self.assertEqual(notifier.tasks[0].status.value, "running")
        self.assertEqual(notifier.tasks[-1].status.value, "completed")
        running_with_output = [task for task in notifier.tasks if task.status.value == "running" and task.live_output]
        self.assertTrue(running_with_output)
        self.assertIn("line 1", running_with_output[-1].live_output or "")

    def test_terminal_update_flushes_pending_running_stream_before_completion(self) -> None:
        controller = TaskController(
            store=InMemoryTaskStore(),
            runner=StreamingRunner(),
        )
        notifier = FakeNotifier()
        gate = Event()
        dispatcher = GatedRunningDispatcher(controller, notifier=notifier, gate=gate)
        task = controller.create_task(
            requester_id="ou_demo",
            prompt="stream output",
            source="feishu",
            reply_receive_id="oc_demo_chat",
            reply_surface=Surface.GROUP,
        )

        def release_gate() -> None:
            sleep(0.05)
            gate.set()

        releaser = Thread(target=release_gate, daemon=True)
        releaser.start()
        updated = controller.start_task_execution_with_callback(
            task.id,
            on_update=dispatcher._notify_if_needed,
        )
        releaser.join(timeout=1)

        self.assertEqual(updated.status.value, "completed")
        self.assertGreaterEqual(len(notifier.tasks), 2)
        self.assertEqual(notifier.tasks[-2].status.value, "running")
        self.assertIn("line 1", notifier.tasks[-2].live_output or "")
        self.assertEqual(notifier.tasks[-1].status.value, "completed")

    def test_dispatch_start_starts_next_queued_task_after_completion(self) -> None:
        first = self.controller.create_task(
            requester_id="ou_demo",
            prompt="first task",
            source="feishu",
            project_id="proj_demo",
            reply_receive_id="oc_demo_chat",
            reply_surface=Surface.GROUP,
        )
        second = self.controller.create_task(
            requester_id="ou_demo",
            prompt="second task",
            source="feishu",
            project_id="proj_demo",
            reply_receive_id="oc_demo_chat",
            reply_surface=Surface.GROUP,
        )
        self.controller.queue_task(second.id)

        self.dispatcher.dispatch_start(first.id)

        updated_first = self.controller.get_task(first.id)
        updated_second = self.controller.get_task(second.id)
        self.assertEqual(updated_first.status.value, "completed")
        self.assertEqual(updated_second.status.value, "completed")

    def test_reconcile_running_tasks_once_completes_stale_running_task_with_output(self) -> None:
        class InactiveRunner(StubAgentRunner):
            def is_task_active(self, task: Task) -> bool | None:
                return False

        controller = TaskController(
            store=InMemoryTaskStore(),
            runner=InactiveRunner(),
            running_reconcile_grace_seconds=0.0,
        )
        notifier = FakeNotifier()
        dispatcher = InlineDispatcher(
            controller,
            notifier=notifier,
            running_reconcile_interval_seconds=0.0,
        )
        task = controller.create_task(
            requester_id="ou_demo",
            prompt="stream output",
            source="feishu",
            project_id="proj_demo",
            reply_receive_id="oc_demo_chat",
            reply_surface=Surface.GROUP,
        )
        task.set_status(TaskStatus.RUNNING)
        task.append_live_output("final answer")
        controller._store.save(task)  # type: ignore[attr-defined]

        dispatcher.reconcile_running_tasks_once()

        updated = controller.get_task(task.id)
        self.assertEqual(updated.status.value, "completed")
        self.assertEqual(notifier.tasks[-1].status.value, "completed")


if __name__ == "__main__":
    unittest.main()
