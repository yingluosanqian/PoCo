from __future__ import annotations

from threading import RLock
from uuid import uuid4

from poco.agent.runner import AgentRunner
from poco.storage.memory import InMemoryTaskStore
from poco.task.models import Task, TaskStatus


class TaskNotFoundError(ValueError):
    pass


class TaskStateError(ValueError):
    pass


class TaskController:
    def __init__(
        self,
        store: InMemoryTaskStore,
        runner: AgentRunner,
    ) -> None:
        self._store = store
        self._runner = runner
        self._lock = RLock()

    def create_task(
        self,
        requester_id: str,
        prompt: str,
        source: str,
        *,
        project_id: str | None = None,
        effective_workdir: str | None = None,
        reply_receive_id: str | None = None,
        reply_receive_id_type: str | None = None,
    ) -> Task:
        with self._lock:
            task = Task(
                id=uuid4().hex[:8],
                requester_id=requester_id,
                prompt=prompt,
                source=source,
                agent_backend=self._runner.name,
                project_id=project_id,
                effective_workdir=effective_workdir,
                reply_receive_id=reply_receive_id,
                reply_receive_id_type=reply_receive_id_type,
            )
            task.add_event("task_created", f"Task created from {source}.")
            self._store.save(task)
            return task

    def get_task(self, task_id: str) -> Task:
        with self._lock:
            task = self._store.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")
            return task

    def list_tasks(self) -> list[Task]:
        with self._lock:
            return self._store.list_all()

    def resolve_confirmation(self, task_id: str, approved: bool) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            if task.status != TaskStatus.WAITING_FOR_CONFIRMATION:
                raise TaskStateError(
                    f"Task {task_id} is not waiting for confirmation."
                )

            if not approved:
                task.awaiting_confirmation_reason = None
                task.set_status(TaskStatus.CANCELLED)
                task.add_event("confirmation_rejected", "User rejected the checkpoint.")
                self._store.save(task)
                return task

            task.awaiting_confirmation_reason = None
            task.set_status(TaskStatus.RUNNING)
            task.add_event("confirmation_approved", "User approved the checkpoint.")
            self._store.save(task)
            return task

    def start_task_execution(self, task_id: str) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            if task.status != TaskStatus.CREATED:
                raise TaskStateError(
                    f"Task {task_id} is not in a startable state."
                )
            return self._start_task_locked(task)

    def resume_task_execution(self, task_id: str) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            if task.status != TaskStatus.RUNNING:
                raise TaskStateError(
                    f"Task {task_id} is not in a resumable state."
                )
            return self._apply_runner_updates_locked(
                task,
                self._runner.resume_after_confirmation(task),
            )

    def mark_task_failed(self, task_id: str, message: str) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            task.set_status(TaskStatus.FAILED)
            task.add_event("task_failed", message)
            self._store.save(task)
            return task

    def _start_task_locked(self, task: Task) -> Task:
        task.set_status(TaskStatus.RUNNING)
        task.add_event("task_started", "Task dispatched to the server-side runner.")
        self._store.save(task)
        return self._apply_runner_updates_locked(task, self._runner.start(task))

    def _apply_runner_updates_locked(self, task: Task, updates: list) -> Task:
        for update in updates:
            if update.kind == "progress":
                task.add_event("runner_progress", update.message)
            elif update.kind == "confirmation_required":
                task.awaiting_confirmation_reason = update.message
                task.set_status(TaskStatus.WAITING_FOR_CONFIRMATION)
                task.add_event("confirmation_required", update.message)
            elif update.kind == "completed":
                task.result_summary = update.result_summary
                task.set_status(TaskStatus.COMPLETED)
                task.add_event("task_completed", update.message)
            elif update.kind == "failed":
                task.set_status(TaskStatus.FAILED)
                task.add_event("task_failed", update.message)
            else:
                raise TaskStateError(f"Unsupported runner update kind: {update.kind}")

        self._store.save(task)
        return task
