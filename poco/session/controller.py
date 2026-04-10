from __future__ import annotations

from threading import RLock
from uuid import uuid4

from poco.session.models import Session, SessionStatus
from poco.storage.protocols import SessionStore
from poco.task.models import Task


class SessionNotFoundError(ValueError):
    pass


class SessionController:
    def __init__(self, store: SessionStore) -> None:
        self._store = store
        self._lock = RLock()

    def create_session(self, *, project_id: str, created_by: str) -> Session:
        with self._lock:
            for session in self._store.list_all():
                if session.project_id == project_id and session.status == SessionStatus.ACTIVE:
                    session.status = SessionStatus.CLOSED
                    self._store.save(session)
            session = Session(
                id=uuid4().hex[:8],
                project_id=project_id,
                created_by=created_by,
            )
            self._store.save(session)
            return session

    def get_session(self, session_id: str) -> Session:
        with self._lock:
            session = self._store.get(session_id)
            if session is None:
                raise SessionNotFoundError(f"Session not found: {session_id}")
            return session

    def get_active_session(self, project_id: str) -> Session | None:
        with self._lock:
            active: Session | None = None
            for session in self._store.list_all():
                if session.project_id != project_id or session.status != SessionStatus.ACTIVE:
                    continue
                if active is None or session.updated_at > active.updated_at:
                    active = session
            return active

    def get_or_create_active_session(self, *, project_id: str, created_by: str) -> Session:
        existing = self.get_active_session(project_id)
        if existing is not None:
            return existing
        return self.create_session(project_id=project_id, created_by=created_by)

    def sync_from_task(self, task: Task) -> Session | None:
        if not task.session_id:
            return None
        with self._lock:
            session = self._store.get(task.session_id)
            if session is None:
                return None
            session.update_from_task(
                task_id=task.id,
                prompt=task.prompt,
                status=task.status.value,
                result_preview=task.result_summary,
            )
            self._store.save(session)
            return session
