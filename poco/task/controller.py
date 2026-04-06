from __future__ import annotations

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

    def create_task(self, requester_id: str, prompt: str, source: str) -> Task:
        task = Task(
            id=uuid4().hex[:8],
            requester_id=requester_id,
            prompt=prompt,
            source=source,
            agent_backend=self._runner.name,
        )
        task.add_event("task_created", f"Task created from {source}.")
        self._store.save(task)
        return self._start_task(task)

    def get_task(self, task_id: str) -> Task:
        task = self._store.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task not found: {task_id}")
        return task

    def list_tasks(self) -> list[Task]:
        return self._store.list_all()

    def resolve_confirmation(self, task_id: str, approved: bool) -> Task:
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
        return self._apply_runner_updates(
            task,
            self._runner.resume_after_confirmation(task),
        )

    def _start_task(self, task: Task) -> Task:
        task.set_status(TaskStatus.RUNNING)
        task.add_event("task_started", "Task dispatched to the server-side runner.")
        self._store.save(task)
        return self._apply_runner_updates(task, self._runner.start(task))

    def _apply_runner_updates(self, task: Task, updates: list) -> Task:
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
