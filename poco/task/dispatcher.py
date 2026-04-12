from __future__ import annotations

from threading import Thread

from poco.task.controller import TaskController
from poco.task.models import Task, TaskStatus
from poco.task.notifier import NullTaskNotifier, TaskNotifier


class AsyncTaskDispatcher:
    def __init__(
        self,
        controller: TaskController,
        *,
        notifier: TaskNotifier | None = None,
    ) -> None:
        self._controller = controller
        self._notifier = notifier or NullTaskNotifier()

    def dispatch_start(self, task_id: str) -> None:
        self._launch(lambda: self._run_start(task_id))

    def dispatch_resume(self, task_id: str) -> None:
        self._launch(lambda: self._run_resume(task_id))

    def dispatch_next_queued(self, project_id: str) -> None:
        next_task = self._controller.claim_next_queued_task(project_id)
        if next_task is None:
            return
        self.dispatch_start(next_task.id)

    def _launch(self, target) -> None:  # type: ignore[no-untyped-def]
        Thread(target=target, daemon=True).start()

    def _run_start(self, task_id: str) -> None:
        try:
            task = self._controller.start_task_execution_with_callback(
                task_id,
                on_update=self._notify_if_needed,
            )
        except Exception as exc:
            task = self._controller.mark_task_failed(
                task_id,
                f"Unhandled dispatcher error: {exc}",
            )
            self._notify_if_needed(task)
        self._dispatch_next_if_possible(task)

    def _run_resume(self, task_id: str) -> None:
        try:
            task = self._controller.resume_task_execution_with_callback(
                task_id,
                on_update=self._notify_if_needed,
            )
        except Exception as exc:
            task = self._controller.mark_task_failed(
                task_id,
                f"Unhandled dispatcher error: {exc}",
            )
            self._notify_if_needed(task)
        self._dispatch_next_if_possible(task)

    def notify_task(self, task: Task) -> None:
        self._notify_if_needed(task)

    def _notify_if_needed(self, task: Task) -> None:
        if task.status == TaskStatus.RUNNING:
            self._notifier.notify_task(task)
            return
        if task.status in {
            TaskStatus.QUEUED,
            TaskStatus.WAITING_FOR_CONFIRMATION,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            self._notifier.notify_task(task)

    def _dispatch_next_if_possible(self, task: Task) -> None:
        if task.status not in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            return
        if not task.project_id:
            return
        self.dispatch_next_queued(task.project_id)
