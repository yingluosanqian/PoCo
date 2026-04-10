from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from poco.main import create_app


class StatePersistenceTest(unittest.TestCase):
    def test_sqlite_backend_recovers_project_workspace_and_tasks_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = os.path.join(tempdir, "poco.db")
            with patch.dict(
                os.environ,
                {
                    "POCO_STATE_BACKEND": "sqlite",
                    "POCO_STATE_DB_PATH": db_path,
                },
            ):
                app1 = create_app()
                project_controller1 = app1.state.project_controller
                session_controller1 = app1.state.session_controller
                workspace_controller1 = app1.state.workspace_controller
                task_controller1 = app1.state.task_controller

                project = project_controller1.create_project(
                    name="PoCo",
                    created_by="ou_demo_user",
                    backend="codex",
                    group_chat_id="oc_group_demo",
                )
                project_controller1.bind_workspace_message(project.id, "om_workspace_demo")
                project_controller1.add_dir_preset(project.id, "/srv/poco/api")
                workspace_controller1.use_manual_workdir(project, "/srv/poco/api")
                session = session_controller1.create_session(
                    project_id=project.id,
                    created_by="ou_demo_user",
                )
                task = task_controller1.create_task(
                    requester_id="ou_demo_user",
                    prompt="ship it",
                    source="feishu_group_message",
                    project_id=project.id,
                    session_id=session.id,
                    effective_workdir="/srv/poco/api",
                    notification_message_id="om_task_demo",
                    reply_receive_id="oc_group_demo",
                    reply_receive_id_type="chat_id",
                )
                task.add_event("task_completed", "done")
                task.set_result("done")
                task.set_status(task.status.COMPLETED)
                task_controller1._store.save(task)  # type: ignore[attr-defined]

                app2 = create_app()
                project_controller2 = app2.state.project_controller
                session_controller2 = app2.state.session_controller
                workspace_controller2 = app2.state.workspace_controller
                task_controller2 = app2.state.task_controller

                recovered_project = project_controller2.get_project_by_group_chat_id("oc_group_demo")
                self.assertIsNotNone(recovered_project)
                assert recovered_project is not None
                self.assertEqual(recovered_project.workspace_message_id, "om_workspace_demo")
                self.assertIn("/srv/poco/api", recovered_project.workdir_presets)

                recovered_context = workspace_controller2.get_context(recovered_project)
                self.assertEqual(recovered_context.active_workdir, "/srv/poco/api")
                self.assertEqual(recovered_context.workdir_source, "manual")

                recovered_task = task_controller2.get_task(task.id)
                self.assertEqual(recovered_task.notification_message_id, "om_task_demo")
                self.assertEqual(recovered_task.project_id, recovered_project.id)
                self.assertEqual(recovered_task.session_id, session.id)
                self.assertEqual(recovered_task.raw_result, "done")
                recovered_session = session_controller2.get_session(session.id)
                self.assertEqual(recovered_session.latest_task_id, task.id)


if __name__ == "__main__":
    unittest.main()
