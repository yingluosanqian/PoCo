from __future__ import annotations

from copy import deepcopy
import logging
from threading import Condition
from threading import Event
from threading import RLock
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
        running_reconcile_interval_seconds: float = 0.5,
    ) -> None:
        self._controller = controller
        self._notifier = notifier or NullTaskNotifier()
        self._running_reconcile_interval_seconds = max(0.0, running_reconcile_interval_seconds)
        self._running_notify_lock = RLock()
        self._running_notify_changed = Condition(self._running_notify_lock)
        self._running_notify_latest: dict[str, Task] = {}
        self._running_notify_active: set[str] = set()
        self._stop_event = Event()
        self._logger = logging.getLogger(__name__)
        if self._running_reconcile_interval_seconds > 0:
            Thread(target=self._run_reconcile_loop, daemon=True).start()

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
            self._enqueue_running_notification(task)
            return
        self._flush_running_notification(task.id)
        self._clear_running_notification(task.id)
        if task.status in {
            TaskStatus.QUEUED,
            TaskStatus.WAITING_FOR_CONFIRMATION,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            self._safe_notify_task(task)

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

    def _enqueue_running_notification(self, task: Task) -> None:
        snapshot = deepcopy(task)
        with self._running_notify_lock:
            self._running_notify_latest[task.id] = snapshot
            if task.id in self._running_notify_active:
                self._running_notify_changed.notify_all()
                return
            self._running_notify_active.add(task.id)
            self._running_notify_changed.notify_all()
        self._launch(lambda: self._drain_running_notifications(task.id))

    def _drain_running_notifications(self, task_id: str) -> None:
        while True:
            with self._running_notify_lock:
                snapshot = self._running_notify_latest.get(task_id)
            if snapshot is None:
                with self._running_notify_lock:
                    self._running_notify_active.discard(task_id)
                    self._running_notify_changed.notify_all()
                return
            self._safe_notify_task(snapshot)
            with self._running_notify_lock:
                latest = self._running_notify_latest.get(task_id)
                if latest is snapshot:
                    self._running_notify_latest.pop(task_id, None)
                    self._running_notify_active.discard(task_id)
                    self._running_notify_changed.notify_all()
                    return
                self._running_notify_changed.notify_all()

    def _flush_running_notification(self, task_id: str) -> None:
        while True:
            snapshot: Task | None = None
            with self._running_notify_lock:
                pending = self._running_notify_latest.get(task_id)
                active = task_id in self._running_notify_active
                if pending is None:
                    if not active:
                        return
                    self._running_notify_changed.wait(timeout=0.05)
                    continue
                if active:
                    self._running_notify_changed.wait(timeout=0.05)
                    continue
                snapshot = pending
                self._running_notify_active.add(task_id)

            self._safe_notify_task(snapshot)

            with self._running_notify_lock:
                latest = self._running_notify_latest.get(task_id)
                if latest is snapshot:
                    self._running_notify_latest.pop(task_id, None)
                self._running_notify_active.discard(task_id)
                self._running_notify_changed.notify_all()
                if task_id not in self._running_notify_latest:
                    return

    def _clear_running_notification(self, task_id: str) -> None:
        with self._running_notify_lock:
            self._running_notify_latest.pop(task_id, None)
            self._running_notify_changed.notify_all()

    def _safe_notify_task(self, task: Task) -> None:
        try:
            self._notifier.notify_task(task)
        except Exception as exc:
            self._logger.warning("Task notification failed for %s: %s", task.id, exc)

    def _run_reconcile_loop(self) -> None:
        while not self._stop_event.wait(self._running_reconcile_interval_seconds):
            self.reconcile_running_tasks_once()

    def reconcile_running_tasks_once(self) -> None:
        for task in self._controller.list_tasks():
            if task.status != TaskStatus.RUNNING:
                continue
            before_status = task.status
            before_updated_at = task.updated_at
            reconciled = self._controller.reconcile_task_execution(task.id)
            if (
                reconciled.status == before_status
                and reconciled.updated_at == before_updated_at
            ):
                continue
            self._notify_if_needed(reconciled)
            self._dispatch_next_if_possible(reconciled)
