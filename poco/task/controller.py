from __future__ import annotations

from collections.abc import Callable, Iterable
from threading import RLock
from uuid import uuid4

from poco.agent.runner import AgentRunner
from poco.session.controller import SessionController
from poco.storage.protocols import TaskStore
from poco.task.models import Task, TaskStatus


class TaskNotFoundError(ValueError):
    pass


class TaskStateError(ValueError):
    pass


class TaskController:
    def __init__(
        self,
        store: TaskStore,
        runner: AgentRunner,
        session_controller: SessionController | None = None,
    ) -> None:
        self._store = store
        self._runner = runner
        self._session_controller = session_controller
        self._lock = RLock()

    def create_task(
        self,
        requester_id: str,
        prompt: str,
        source: str,
        *,
        project_id: str | None = None,
        session_id: str | None = None,
        effective_model: str | None = None,
        effective_workdir: str | None = None,
        notification_message_id: str | None = None,
        reply_receive_id: str | None = None,
        reply_receive_id_type: str | None = None,
    ) -> Task:
        with self._lock:
            effective_model, resolved_workdir = self._runner.resolve_execution_context(
                Task(
                    id="preview",
                    requester_id=requester_id,
                    prompt=prompt,
                    source=source,
                    agent_backend=self._runner.name,
                    effective_model=effective_model,
                    project_id=project_id,
                    session_id=session_id,
                    effective_workdir=effective_workdir,
                    notification_message_id=notification_message_id,
                    reply_receive_id=reply_receive_id,
                    reply_receive_id_type=reply_receive_id_type,
                )
            )
            task = Task(
                id=uuid4().hex[:8],
                requester_id=requester_id,
                prompt=prompt,
                source=source,
                agent_backend=self._runner.name,
                effective_model=effective_model,
                project_id=project_id,
                session_id=session_id,
                effective_workdir=resolved_workdir,
                notification_message_id=notification_message_id,
                reply_receive_id=reply_receive_id,
                reply_receive_id_type=reply_receive_id_type,
            )
            task.add_event("task_created", f"Task created from {source}.")
            self._store.save(task)
            self._sync_session(task)
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

    def list_tasks_for_project(self, project_id: str) -> list[Task]:
        with self._lock:
            return [
                task
                for task in self._store.list_all()
                if task.project_id == project_id
            ]

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
                self._sync_session(task)
                return task

            task.awaiting_confirmation_reason = None
            task.set_status(TaskStatus.RUNNING)
            task.add_event("confirmation_approved", "User approved the checkpoint.")
            self._store.save(task)
            self._sync_session(task)
            return task

    def cancel_task(self, task_id: str, *, reason: str = "Task stopped by user.") -> Task:
        with self._lock:
            task = self.get_task(task_id)
            if task.status in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }:
                raise TaskStateError(f"Task {task_id} is already terminal.")

            cancel_runner = getattr(self._runner, "cancel", None)
            if callable(cancel_runner):
                cancel_runner(task.id)

            task.awaiting_confirmation_reason = None
            task.clear_live_output()
            task.set_status(TaskStatus.CANCELLED)
            task.add_event("task_cancelled", reason)
            self._store.save(task)
            self._sync_session(task)
            return task

    def start_task_execution(self, task_id: str) -> Task:
        return self._start_or_resume(task_id, mode="start")

    def resume_task_execution(self, task_id: str) -> Task:
        return self._start_or_resume(task_id, mode="resume")

    def start_task_execution_with_callback(
        self,
        task_id: str,
        *,
        on_update: Callable[[Task], None] | None = None,
    ) -> Task:
        return self._start_or_resume(task_id, mode="start", on_update=on_update)

    def resume_task_execution_with_callback(
        self,
        task_id: str,
        *,
        on_update: Callable[[Task], None] | None = None,
    ) -> Task:
        return self._start_or_resume(task_id, mode="resume", on_update=on_update)

    def mark_task_failed(self, task_id: str, message: str) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            task.set_status(TaskStatus.FAILED)
            task.add_event("task_failed", message)
            self._store.save(task)
            self._sync_session(task)
            return task

    def bind_notification_message(self, task_id: str, message_id: str | None) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            task.set_notification_message_id(message_id)
            self._store.save(task)
            return task

    def recover_interrupted_tasks(self) -> list[Task]:
        recovered: list[Task] = []
        with self._lock:
            for task in self._store.list_all():
                if task.status not in {TaskStatus.CREATED, TaskStatus.RUNNING}:
                    continue
                task.clear_live_output()
                task.set_status(TaskStatus.FAILED)
                task.add_event(
                    "task_interrupted",
                    "Task execution was interrupted by a server restart.",
                )
                self._store.save(task)
                self._sync_session(task)
                recovered.append(task)
        return recovered

    def _start_or_resume(
        self,
        task_id: str,
        *,
        mode: str,
        on_update: Callable[[Task], None] | None = None,
    ) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            if mode == "start" and task.status != TaskStatus.CREATED:
                raise TaskStateError(f"Task {task_id} is not in a startable state.")
            if mode == "resume" and task.status != TaskStatus.RUNNING:
                raise TaskStateError(f"Task {task_id} is not in a resumable state.")
            effective_model, effective_workdir = self._runner.resolve_execution_context(task)
            task.set_execution_context(
                effective_model=effective_model,
                effective_workdir=effective_workdir,
            )
            if mode == "start":
                task.set_status(TaskStatus.RUNNING)
                task.add_event("task_started", "Task dispatched to the server-side runner.")
                self._store.save(task)

        updates = self._runner.start(task) if mode == "start" else self._runner.resume_after_confirmation(task)
        return self._apply_runner_updates(task_id, updates, on_update=on_update)

    def _apply_runner_updates(
        self,
        task_id: str,
        updates: Iterable,
        *,
        on_update: Callable[[Task], None] | None = None,
    ) -> Task:
        for update in updates:
            with self._lock:
                task = self.get_task(task_id)
                if task.status == TaskStatus.CANCELLED:
                    continue
                if update.kind == "progress":
                    if getattr(update, "output_chunk", None):
                        task.append_live_output(update.output_chunk)
                    task.add_event("runner_progress", update.message)
                elif update.kind == "confirmation_required":
                    task.awaiting_confirmation_reason = update.message
                    task.set_status(TaskStatus.WAITING_FOR_CONFIRMATION)
                    task.add_event("confirmation_required", update.message)
                elif update.kind == "completed":
                    task.set_result(update.raw_result)
                    task.clear_live_output()
                    task.set_status(TaskStatus.COMPLETED)
                    task.add_event("task_completed", update.message)
                elif update.kind == "failed":
                    task.clear_live_output()
                    task.set_status(TaskStatus.FAILED)
                    task.add_event("task_failed", update.message)
                else:
                    raise TaskStateError(f"Unsupported runner update kind: {update.kind}")
                self._store.save(task)
                self._sync_session(task)
            if on_update is not None:
                on_update(task)

        with self._lock:
            return self.get_task(task_id)

    def _sync_session(self, task: Task) -> None:
        if self._session_controller is None:
            return
        self._session_controller.sync_from_task(task)
