from __future__ import annotations

from collections.abc import Callable, Iterable
import logging
from datetime import UTC, datetime, timedelta
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
        running_reconcile_grace_seconds: float = 3.0,
    ) -> None:
        self._store = store
        self._runner = runner
        self._session_controller = session_controller
        self._lock = RLock()
        self._logger = logging.getLogger(__name__)
        self._running_reconcile_grace = timedelta(seconds=max(0.0, running_reconcile_grace_seconds))

    def create_task(
        self,
        requester_id: str,
        prompt: str,
        source: str,
        *,
        agent_backend: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        effective_backend_config: dict[str, object] | None = None,
        effective_model: str | None = None,
        effective_sandbox: str | None = None,
        effective_workdir: str | None = None,
        backend_session_id: str | None = None,
        notification_message_id: str | None = None,
        reply_receive_id: str | None = None,
        reply_receive_id_type: str | None = None,
    ) -> Task:
        with self._lock:
            resolved_backend_session_id = backend_session_id
            if resolved_backend_session_id is None and session_id and self._session_controller is not None:
                try:
                    resolved_backend_session_id = self._session_controller.get_session(session_id).backend_session_id
                except ValueError:
                    resolved_backend_session_id = None
            effective_model, resolved_workdir, resolved_sandbox = self._runner.resolve_execution_context(
                Task(
                    id="preview",
                    requester_id=requester_id,
                    prompt=prompt,
                    source=source,
                    agent_backend=agent_backend or self._runner.name,
                    effective_backend_config=effective_backend_config or {},
                    effective_model=effective_model,
                    effective_sandbox=effective_sandbox,
                    backend_session_id=resolved_backend_session_id,
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
                agent_backend=agent_backend or self._runner.name,
                effective_backend_config=effective_backend_config or {},
                effective_model=effective_model,
                effective_sandbox=resolved_sandbox,
                backend_session_id=resolved_backend_session_id,
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

    def warm_runner(
        self,
        *,
        backend: str,
        workdir: str,
        reasoning_effort: str | None = None,
    ) -> bool:
        """Best-effort pre-warm of the underlying runner. Returns True if a
        warm was actually scheduled; False if the runner does not support
        warm, the parameters are incomplete, or the attempt raised.
        """
        if not backend or not workdir:
            return False
        warm = getattr(self._runner, "warm", None)
        if not callable(warm):
            return False
        try:
            return bool(
                warm(
                    backend=backend,
                    workdir=workdir,
                    reasoning_effort=reasoning_effort,
                )
            )
        except Exception:
            self._logger.info(
                "warm_runner raised for backend=%s workdir=%s",
                backend,
                workdir,
                exc_info=True,
            )
            return False

    def list_tasks_for_project(self, project_id: str) -> list[Task]:
        with self._lock:
            return [
                task
                for task in self._store.list_all()
                if task.project_id == project_id
            ]

    def has_active_task_for_project(
        self,
        project_id: str,
        *,
        exclude_task_id: str | None = None,
    ) -> bool:
        with self._lock:
            for task in self._store.list_all():
                if task.project_id != project_id:
                    continue
                if exclude_task_id and task.id == exclude_task_id:
                    continue
                if task.status in {
                    TaskStatus.CREATED,
                    TaskStatus.RUNNING,
                    TaskStatus.WAITING_FOR_CONFIRMATION,
                }:
                    return True
            return False

    def queue_task(
        self,
        task_id: str,
        *,
        reason: str = "Queued behind the current running task.",
    ) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            if task.status != TaskStatus.CREATED:
                raise TaskStateError(f"Task {task_id} is not in a queueable state.")
            task.set_status(TaskStatus.QUEUED)
            task.add_event("task_queued", reason)
            self._store.save(task)
            self._sync_session(task)
            return task

    def claim_next_queued_task(self, project_id: str) -> Task | None:
        with self._lock:
            if self.has_active_task_for_project(project_id):
                return None
            queued = sorted(
                (
                    task
                    for task in self._store.list_all()
                    if task.project_id == project_id and task.status == TaskStatus.QUEUED
                ),
                key=lambda task: task.created_at,
            )
            if not queued:
                return None
            task = queued[0]
            task.set_status(TaskStatus.CREATED)
            task.add_event("task_dequeued", "Task left the queue and is ready to start.")
            self._store.save(task)
            self._sync_session(task)
            return task

    def get_queue_count(self, project_id: str) -> int:
        with self._lock:
            return sum(
                1
                for task in self._store.list_all()
                if task.project_id == project_id and task.status == TaskStatus.QUEUED
            )

    def get_queue_position(self, task_id: str) -> int | None:
        with self._lock:
            task = self.get_task(task_id)
            if task.project_id is None or task.status != TaskStatus.QUEUED:
                return None
            queued = sorted(
                (
                    item
                    for item in self._store.list_all()
                    if item.project_id == task.project_id and item.status == TaskStatus.QUEUED
                ),
                key=lambda item: item.created_at,
            )
            for index, item in enumerate(queued, start=1):
                if item.id == task.id:
                    return index
            return None

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
            if task.live_output and not task.raw_result:
                task.set_result(task.live_output)
            task.set_status(TaskStatus.CANCELLED)
            task.add_event("task_cancelled", reason)
            self._store.save(task)
            self._sync_session(task)
            return task

    def steer_task(self, task_id: str, prompt: str) -> Task:
        instruction = prompt.strip()
        if not instruction:
            raise TaskStateError("Steer prompt cannot be empty.")
        with self._lock:
            task = self.get_task(task_id)
            if task.status != TaskStatus.RUNNING:
                raise TaskStateError(f"Task {task_id} is not in a steerable state.")
            steer_runner = getattr(self._runner, "steer", None)
            if not callable(steer_runner):
                raise TaskStateError(f"Steer is not supported by backend: {task.agent_backend}")
        success, detail = steer_runner(task, instruction)
        if not success:
            raise TaskStateError(detail)
        with self._lock:
            task = self.get_task(task_id)
            task.add_event("task_steered", detail)
            self._store.save(task)
            self._sync_session(task)
            return task

    def bind_backend_session(self, task_id: str, backend_session_id: str) -> Task:
        session_id = backend_session_id.strip()
        if not session_id:
            raise ValueError("Backend session id cannot be empty.")
        with self._lock:
            task = self.get_task(task_id)
            task.set_execution_context(
                effective_backend_config=dict(task.effective_backend_config),
                effective_model=task.effective_model,
                effective_sandbox=task.effective_sandbox,
                effective_workdir=task.effective_workdir,
                backend_session_id=session_id,
            )
            self._store.save(task)
            self._sync_session(task)
            return task

    def add_task_event(self, task_id: str, kind: str, message: str) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            task.add_event(kind, message)
            self._store.save(task)
            self._sync_session(task)
            return task

    def reconcile_task_execution(self, task_id: str) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            if task.status != TaskStatus.RUNNING:
                return task
            age = datetime.now(UTC) - task.updated_at
            if age < self._running_reconcile_grace:
                return task
            active_probe = getattr(self._runner, "is_task_active", None)
            if not callable(active_probe):
                return task
            is_active = active_probe(task)
            if is_active is not False:
                return task
            recovered_output = task.raw_result or task.live_output
            if recovered_output:
                task.set_result(recovered_output)
                task.clear_live_output()
                task.set_status(TaskStatus.COMPLETED)
                task.add_event(
                    "task_completed",
                    "Task completion was recovered from streamed output after the runner process became inactive.",
                )
            else:
                task.clear_live_output()
                task.set_status(TaskStatus.FAILED)
                task.add_event(
                    "task_failed",
                    "Task execution ended unexpectedly because the runner process is no longer active.",
                )
            self._store.save(task)
            self._sync_session(task)
            return task

    def reconcile_project_execution(self, project_id: str) -> list[Task]:
        with self._lock:
            running_task_ids = [
                task.id
                for task in self._store.list_all()
                if task.project_id == project_id and task.status == TaskStatus.RUNNING
            ]
        reconciled: list[Task] = []
        for task_id in running_task_ids:
            before = self.get_task(task_id)
            before_status = before.status
            before_updated_at = before.updated_at
            after = self.reconcile_task_execution(task_id)
            if after.status != before_status or after.updated_at != before_updated_at:
                reconciled.append(after)
        return reconciled

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
            if task.live_output and not task.raw_result:
                task.set_result(task.live_output)
                task.clear_live_output()
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
            effective_model, effective_workdir, effective_sandbox = self._runner.resolve_execution_context(task)
            task.set_execution_context(
                effective_backend_config=task.effective_backend_config,
                effective_model=effective_model,
                effective_sandbox=effective_sandbox,
                effective_workdir=effective_workdir,
                backend_session_id=task.backend_session_id,
            )
            if mode == "start":
                task.set_status(TaskStatus.RUNNING)
                task.add_event("task_started", "Task dispatched to the server-side runner.")
                self._store.save(task)
                started_task = task
            else:
                started_task = None

        if started_task is not None and on_update is not None:
            try:
                on_update(started_task)
            except Exception as exc:
                self._logger.warning("Task start callback failed for %s: %s", started_task.id, exc)

        updates = self._runner.start(task) if mode == "start" else self._runner.resume_after_confirmation(task)
        return self._apply_runner_updates(task_id, updates, on_update=on_update)

    def _apply_runner_updates(
        self,
        task_id: str,
        updates: Iterable,
        *,
        on_update: Callable[[Task], None] | None = None,
    ) -> Task:
        close_updates = getattr(updates, "close", None)
        try:
            for update in updates:
                with self._lock:
                    task = self.get_task(task_id)
                    if task.status == TaskStatus.CANCELLED:
                        continue
                    if update.kind == "progress":
                        if getattr(update, "backend_session_id", None):
                            task.set_execution_context(
                                effective_backend_config=task.effective_backend_config,
                                effective_model=task.effective_model,
                                effective_sandbox=task.effective_sandbox,
                                effective_workdir=task.effective_workdir,
                                backend_session_id=update.backend_session_id,
                            )
                        if getattr(update, "output_chunk", None):
                            task.append_live_output(update.output_chunk)
                        task.add_event("runner_progress", update.message)
                    elif update.kind == "confirmation_required":
                        task.awaiting_confirmation_reason = update.message
                        task.set_status(TaskStatus.WAITING_FOR_CONFIRMATION)
                        task.add_event("confirmation_required", update.message)
                    elif update.kind == "completed":
                        if getattr(update, "backend_session_id", None):
                            task.set_execution_context(
                                effective_backend_config=task.effective_backend_config,
                                effective_model=task.effective_model,
                                effective_sandbox=task.effective_sandbox,
                                effective_workdir=task.effective_workdir,
                                backend_session_id=update.backend_session_id,
                            )
                        task.set_result(update.raw_result)
                        task.clear_live_output()
                        task.set_status(TaskStatus.COMPLETED)
                        task.add_event("task_completed", update.message)
                    elif update.kind == "failed":
                        if getattr(update, "backend_session_id", None):
                            task.set_execution_context(
                                effective_backend_config=task.effective_backend_config,
                                effective_model=task.effective_model,
                                effective_sandbox=task.effective_sandbox,
                                effective_workdir=task.effective_workdir,
                                backend_session_id=update.backend_session_id,
                            )
                        if task.live_output and not task.raw_result:
                            task.set_result(task.live_output)
                        task.clear_live_output()
                        task.set_status(TaskStatus.FAILED)
                        task.add_event("task_failed", update.message)
                    else:
                        raise TaskStateError(f"Unsupported runner update kind: {update.kind}")
                    self._store.save(task)
                    self._sync_session(task)
                if on_update is not None:
                    try:
                        on_update(task)
                    except Exception as exc:
                        self._logger.warning("Task update callback failed for %s: %s", task.id, exc)

            with self._lock:
                return self.get_task(task_id)
        finally:
            if callable(close_updates):
                close_updates()

    def _sync_session(self, task: Task) -> None:
        if self._session_controller is None:
            return
        self._session_controller.sync_from_task(task)
