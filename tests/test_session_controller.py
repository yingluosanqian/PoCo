from __future__ import annotations

import unittest

from poco.session.controller import SessionController
from poco.storage.memory import InMemorySessionStore
from poco.task.models import Task, TaskStatus


class SessionControllerTest(unittest.TestCase):
    def test_get_or_create_active_session_reuses_existing_session(self) -> None:
        controller = SessionController(InMemorySessionStore())

        first = controller.get_or_create_active_session(
            project_id="proj_1",
            created_by="ou_demo",
        )
        second = controller.get_or_create_active_session(
            project_id="proj_1",
            created_by="ou_demo",
        )

        self.assertEqual(first.id, second.id)

    def test_attach_backend_session_creates_session_when_missing(self) -> None:
        controller = SessionController(InMemorySessionStore())

        session = controller.attach_backend_session(
            "proj_1",
            "thread_new",
            created_by="ou_demo",
        )

        self.assertEqual(session.project_id, "proj_1")
        self.assertEqual(session.backend_session_id, "thread_new")
        fetched = controller.get_active_session("proj_1")
        assert fetched is not None
        self.assertEqual(fetched.id, session.id)
        self.assertEqual(fetched.backend_session_id, "thread_new")

    def test_attach_backend_session_overwrites_existing_id(self) -> None:
        controller = SessionController(InMemorySessionStore())
        original = controller.create_session(project_id="proj_1", created_by="ou_demo")
        original.backend_session_id = "thread_old"
        controller._store.save(original)  # type: ignore[attr-defined]

        updated = controller.attach_backend_session(
            "proj_1",
            "thread_new",
            created_by="ou_demo",
        )

        self.assertEqual(updated.id, original.id)
        self.assertEqual(updated.backend_session_id, "thread_new")

    def test_attach_backend_session_with_none_clears_id(self) -> None:
        controller = SessionController(InMemorySessionStore())
        original = controller.create_session(project_id="proj_1", created_by="ou_demo")
        original.backend_session_id = "thread_old"
        controller._store.save(original)  # type: ignore[attr-defined]

        updated = controller.attach_backend_session(
            "proj_1",
            None,
            created_by="ou_demo",
        )

        self.assertEqual(updated.id, original.id)
        self.assertIsNone(updated.backend_session_id)

    def test_sync_from_task_updates_summary(self) -> None:
        controller = SessionController(InMemorySessionStore())
        session = controller.create_session(project_id="proj_1", created_by="ou_demo")
        task = Task(
            id="task_1",
            requester_id="ou_demo",
            prompt="fix the api handler",
            source="feishu_group_message",
            agent_backend="codex",
            backend_session_id="thread_123",
            project_id="proj_1",
            session_id=session.id,
            status=TaskStatus.COMPLETED,
            result_summary="patched and verified",
        )

        updated = controller.sync_from_task(task)

        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated.latest_task_id, "task_1")
        self.assertEqual(updated.latest_task_status, "completed")
        self.assertEqual(updated.backend_session_id, "thread_123")
        self.assertIn("patched", updated.summary_text())


if __name__ == "__main__":
    unittest.main()
