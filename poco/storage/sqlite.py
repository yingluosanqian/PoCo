from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from poco.project.models import Project
from poco.session.models import Session, SessionStatus
from poco.task.models import Task, TaskEvent, TaskStatus
from poco.workspace.models import WorkspaceContext


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


class _SqliteStoreBase:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    repo TEXT,
                    workdir TEXT,
                    workdir_presets TEXT NOT NULL,
                    group_chat_id TEXT,
                    workspace_message_id TEXT,
                    archived INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_projects_group_chat_id
                ON projects(group_chat_id);

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    requester_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    agent_backend TEXT NOT NULL,
                    effective_model TEXT,
                    project_id TEXT,
                    session_id TEXT,
                    effective_workdir TEXT,
                    notification_message_id TEXT,
                    reply_receive_id TEXT,
                    reply_receive_id_type TEXT,
                    status TEXT NOT NULL,
                    awaiting_confirmation_reason TEXT,
                    live_output TEXT,
                    raw_result TEXT,
                    result_summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    events TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_project_id
                ON tasks(project_id);

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    status TEXT NOT NULL,
                    latest_task_id TEXT,
                    latest_prompt TEXT,
                    latest_result_preview TEXT,
                    latest_task_status TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_project_id
                ON sessions(project_id);

                CREATE TABLE IF NOT EXISTS workspace_contexts (
                    project_id TEXT PRIMARY KEY,
                    active_workdir TEXT,
                    workdir_source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            task_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if "session_id" not in task_columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN session_id TEXT")
            if "effective_model" not in task_columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN effective_model TEXT")


class SqliteProjectStore(_SqliteStoreBase):
    def save(self, project: Project) -> Project:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id, name, created_by, backend, repo, workdir, workdir_presets,
                    group_chat_id, workspace_message_id, archived, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    created_by = excluded.created_by,
                    backend = excluded.backend,
                    repo = excluded.repo,
                    workdir = excluded.workdir,
                    workdir_presets = excluded.workdir_presets,
                    group_chat_id = excluded.group_chat_id,
                    workspace_message_id = excluded.workspace_message_id,
                    archived = excluded.archived,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    project.id,
                    project.name,
                    project.created_by,
                    project.backend,
                    project.repo,
                    project.workdir,
                    json.dumps(project.workdir_presets, ensure_ascii=False),
                    project.group_chat_id,
                    project.workspace_message_id,
                    int(project.archived),
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                ),
            )
        return project

    def get(self, project_id: str) -> Project | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_project(row)

    def list_all(self) -> list[Project]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projects ORDER BY created_at ASC"
            ).fetchall()
        return [self._row_to_project(row) for row in rows]

    def delete(self, project_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def _row_to_project(self, row: sqlite3.Row) -> Project:
        presets = json.loads(row["workdir_presets"])
        return Project(
            id=row["id"],
            name=row["name"],
            created_by=row["created_by"],
            backend=row["backend"],
            repo=row["repo"],
            workdir=row["workdir"],
            workdir_presets=list(presets),
            group_chat_id=row["group_chat_id"],
            workspace_message_id=row["workspace_message_id"],
            archived=bool(row["archived"]),
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )


class SqliteTaskStore(_SqliteStoreBase):
    def save(self, task: Task) -> Task:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    id, source, requester_id, prompt, agent_backend, effective_model, project_id, session_id,
                    effective_workdir, notification_message_id, reply_receive_id,
                    reply_receive_id_type, status, awaiting_confirmation_reason,
                    live_output, raw_result, result_summary, created_at, updated_at, events
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source = excluded.source,
                    requester_id = excluded.requester_id,
                    prompt = excluded.prompt,
                    agent_backend = excluded.agent_backend,
                    effective_model = excluded.effective_model,
                    project_id = excluded.project_id,
                    session_id = excluded.session_id,
                    effective_workdir = excluded.effective_workdir,
                    notification_message_id = excluded.notification_message_id,
                    reply_receive_id = excluded.reply_receive_id,
                    reply_receive_id_type = excluded.reply_receive_id_type,
                    status = excluded.status,
                    awaiting_confirmation_reason = excluded.awaiting_confirmation_reason,
                    live_output = excluded.live_output,
                    raw_result = excluded.raw_result,
                    result_summary = excluded.result_summary,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    events = excluded.events
                """,
                (
                    task.id,
                    task.source,
                    task.requester_id,
                    task.prompt,
                    task.agent_backend,
                    task.effective_model,
                    task.project_id,
                    task.session_id,
                    task.effective_workdir,
                    task.notification_message_id,
                    task.reply_receive_id,
                    task.reply_receive_id_type,
                    task.status.value,
                    task.awaiting_confirmation_reason,
                    task.live_output,
                    task.raw_result,
                    task.result_summary,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                    json.dumps(
                        [
                            {
                                "kind": event.kind,
                                "message": event.message,
                                "created_at": event.created_at.isoformat(),
                            }
                            for event in task.events
                        ],
                        ensure_ascii=False,
                    ),
                ),
            )
        return task

    def get(self, task_id: str) -> Task | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    def list_all(self) -> list[Task]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY created_at ASC"
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        raw_events = json.loads(row["events"])
        events = [
            TaskEvent(
                kind=item["kind"],
                message=item["message"],
                created_at=_parse_datetime(item["created_at"]),
            )
            for item in raw_events
        ]
        return Task(
            id=row["id"],
            source=row["source"],
            requester_id=row["requester_id"],
            prompt=row["prompt"],
            agent_backend=row["agent_backend"],
            effective_model=row["effective_model"],
            project_id=row["project_id"],
            session_id=row["session_id"],
            effective_workdir=row["effective_workdir"],
            notification_message_id=row["notification_message_id"],
            reply_receive_id=row["reply_receive_id"],
            reply_receive_id_type=row["reply_receive_id_type"],
            status=TaskStatus(row["status"]),
            events=events,
            awaiting_confirmation_reason=row["awaiting_confirmation_reason"],
            live_output=row["live_output"],
            raw_result=row["raw_result"],
            result_summary=row["result_summary"],
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )


class SqliteWorkspaceContextStore(_SqliteStoreBase):
    def save(self, context: WorkspaceContext) -> WorkspaceContext:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workspace_contexts (
                    project_id, active_workdir, workdir_source, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    active_workdir = excluded.active_workdir,
                    workdir_source = excluded.workdir_source,
                    updated_at = excluded.updated_at
                """,
                (
                    context.project_id,
                    context.active_workdir,
                    context.workdir_source,
                    context.updated_at.isoformat(),
                ),
            )
        return context

    def get(self, project_id: str) -> WorkspaceContext | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workspace_contexts WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return WorkspaceContext(
            project_id=row["project_id"],
            active_workdir=row["active_workdir"],
            workdir_source=row["workdir_source"],
            updated_at=_parse_datetime(row["updated_at"]),
        )


class SqliteSessionStore(_SqliteStoreBase):
    def save(self, session: Session) -> Session:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    id, project_id, created_by, status, latest_task_id, latest_prompt,
                    latest_result_preview, latest_task_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_id = excluded.project_id,
                    created_by = excluded.created_by,
                    status = excluded.status,
                    latest_task_id = excluded.latest_task_id,
                    latest_prompt = excluded.latest_prompt,
                    latest_result_preview = excluded.latest_result_preview,
                    latest_task_status = excluded.latest_task_status,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    session.id,
                    session.project_id,
                    session.created_by,
                    session.status.value,
                    session.latest_task_id,
                    session.latest_prompt,
                    session.latest_result_preview,
                    session.latest_task_status,
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                ),
            )
        return session

    def get(self, session_id: str) -> Session | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def list_all(self) -> list[Session]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sessions ORDER BY created_at ASC"
            ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def _row_to_session(self, row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            project_id=row["project_id"],
            created_by=row["created_by"],
            status=SessionStatus(row["status"]),
            latest_task_id=row["latest_task_id"],
            latest_prompt=row["latest_prompt"],
            latest_result_preview=row["latest_result_preview"],
            latest_task_status=row["latest_task_status"],
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )
