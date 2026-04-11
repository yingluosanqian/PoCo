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
