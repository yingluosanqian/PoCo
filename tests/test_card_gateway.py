from __future__ import annotations

import unittest

from poco.interaction.card_dispatcher import CardActionDispatcher
from poco.interaction.card_handlers import ProjectIntentHandler, TaskIntentHandler, WorkspaceIntentHandler
from poco.platform.feishu.card_gateway import FeishuCardActionGateway
from poco.platform.feishu.cards import FeishuCardRenderer
from poco.project.bootstrap import ProjectBootstrapError, ProjectBootstrapResult
from poco.project.controller import ProjectController
from poco.session.controller import SessionController
from poco.storage.memory import InMemoryProjectStore, InMemorySessionStore, InMemoryTaskStore, InMemoryWorkspaceContextStore
from poco.task.controller import TaskController
from poco.agent.runner import StubAgentRunner
from poco.workspace.controller import WorkspaceContextController


class FakeProjectBootstrapper:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.workspace_notifications: list[dict[str, str]] = []

    def bootstrap_project(self, *, project, actor_id: str) -> ProjectBootstrapResult:
        self.calls.append(
            {
                "project_id": project.id,
                "project_name": project.name,
                "actor_id": actor_id,
            }
        )
        return ProjectBootstrapResult(group_chat_id=f"oc_group_{project.id}")

    def notify_project_workspace(self, *, project, actor_id: str) -> None:
        self.workspace_notifications.append(
            {
                "project_id": project.id,
                "project_name": project.name,
                "group_chat_id": project.group_chat_id or "",
                "actor_id": actor_id,
            }
        )


class FailingProjectBootstrapper:
    def bootstrap_project(self, *, project, actor_id: str) -> ProjectBootstrapResult:
        raise ProjectBootstrapError("simulated bootstrap failure")

    def notify_project_workspace(self, *, project, actor_id: str) -> None:
        return None


class NotifyFailingProjectBootstrapper(FakeProjectBootstrapper):
    def notify_project_workspace(self, *, project, actor_id: str) -> None:
        raise RuntimeError("simulated workspace notification failure")


class FakeTaskDispatcher:
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []

    def dispatch_start(self, task_id: str) -> None:
        self.actions.append(("start", task_id))

    def dispatch_resume(self, task_id: str) -> None:
        self.actions.append(("resume", task_id))

    def dispatch_next_queued(self, project_id: str) -> None:
        self.actions.append(("next", project_id))


class FeishuCardGatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_controller = ProjectController(InMemoryProjectStore())
        self.workspace_controller = WorkspaceContextController(InMemoryWorkspaceContextStore())
        self.session_controller = SessionController(InMemorySessionStore())
        self.task_controller = TaskController(
            store=InMemoryTaskStore(),
            runner=StubAgentRunner(),
            session_controller=self.session_controller,
        )
        self.task_dispatcher = FakeTaskDispatcher()
        self.bootstrapper = FakeProjectBootstrapper()
        self.project_handler = ProjectIntentHandler(
            self.project_controller,
            bootstrapper=self.bootstrapper,
        )
        self.workspace_handler = WorkspaceIntentHandler(
            self.project_controller,
            self.workspace_controller,
            self.task_controller,
            self.session_controller,
        )
        self.task_handler = TaskIntentHandler(
            self.project_controller,
            self.workspace_controller,
            self.task_controller,
            self.session_controller,
            dispatcher=self.task_dispatcher,  # type: ignore[arg-type]
        )
        self.gateway = FeishuCardActionGateway(
            dispatcher=CardActionDispatcher(
                {
                    "project.home": self.project_handler,
                    "project.new": self.project_handler,
                    "project.manage": self.project_handler,
                    "project.list": self.project_handler,
                    "project.create": self.project_handler,
                    "project.open": self.project_handler,
                    "project.configure_agent": self.project_handler,
                    "project.configure_repo": self.project_handler,
                    "project.configure_default_dir": self.project_handler,
                    "project.manage_dir_presets": self.project_handler,
                    "project.add_dir_preset": self.project_handler,
                    "project.bind_group": self.project_handler,
                    "workspace.open": self.workspace_handler,
                    "workspace.use_default_dir": self.workspace_handler,
                    "workspace.choose_preset": self.workspace_handler,
                    "workspace.apply_preset_dir": self.workspace_handler,
                    "workspace.use_recent_dir": self.workspace_handler,
                    "workspace.enter_path": self.workspace_handler,
                    "workspace.apply_entered_path": self.workspace_handler,
                    "workspace.choose_model": self.workspace_handler,
                    "workspace.apply_model": self.workspace_handler,
                    "task.open_composer": self.task_handler,
                    "task.open": self.task_handler,
                    "task.submit": self.task_handler,
                    "task.stop": self.task_handler,
                    "task.approve": self.task_handler,
                    "task.reject": self.task_handler,
                }
            ),
            renderer=FeishuCardRenderer(),
            project_controller=self.project_controller,
        )

    def test_render_dm_project_list_returns_card(self) -> None:
        response = self.gateway.render_dm_project_list()

        self.assertEqual(response["instruction"]["template_key"], "project_home")
        self.assertEqual(response["card"]["schema"], "2.0")
        self.assertEqual(response["card"]["header"]["title"]["content"], "PoCo Projects")
        create_button = response["card"]["body"]["elements"][1]
        manage_button = response["card"]["body"]["elements"][2]
        self.assertEqual(create_button["tag"], "button")
        self.assertEqual(create_button["text"]["content"], "New")
        self.assertEqual(create_button["behaviors"][0]["type"], "callback")
        self.assertEqual(
            create_button["behaviors"][0]["value"]["intent_key"],
            "project.new",
        )
        self.assertEqual(manage_button["behaviors"][0]["value"]["intent_key"], "project.manage")

    def test_project_new_action_returns_project_create_card(self) -> None:
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_new_1"},
                "action": {
                    "value": {
                        "intent_key": "project.new",
                        "surface": "dm",
                        "request_id": "req_project_new_1",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "project_create")
        self.assertEqual(response["card"]["data"]["header"]["title"]["content"], "New Project")

    def test_project_create_action_returns_project_home_card(self) -> None:
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_1"},
                "action": {
                    "value": {
                        "intent_key": "project.create",
                        "surface": "dm",
                        "request_id": "req_project_create_1",
                    },
                    "form_value": {
                        "name": "PoCo",
                        "backend": "codex",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "project_home")
        self.assertEqual(response["card"]["data"]["schema"], "2.0")
        self.assertEqual(response["card"]["data"]["header"]["title"]["content"], "PoCo Projects")
        projects = self.project_controller.list_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].group_chat_id, f"oc_group_{projects[0].id}")
        self.assertEqual(len(self.bootstrapper.calls), 1)
        self.assertEqual(len(self.bootstrapper.workspace_notifications), 1)
        self.assertEqual(
            self.bootstrapper.workspace_notifications[0]["group_chat_id"],
            f"oc_group_{projects[0].id}",
        )
        self.assertEqual(
            response["card"]["data"]["body"]["elements"][1]["behaviors"][0]["value"]["intent_key"],
            "project.new",
        )

    def test_project_create_accepts_project_name_from_input_value(self) -> None:
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_create_input_1"},
                "action": {
                    "value": {
                        "intent_key": "project.create",
                        "surface": "dm",
                        "request_id": "req_project_create_input_1",
                        "backend": "codex",
                    },
                    "input_value": "PoCo Input",
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "project_home")
        self.assertEqual(response["card"]["data"]["header"]["title"]["content"], "PoCo Projects")

    def test_project_create_rolls_back_when_group_bootstrap_fails(self) -> None:
        failing_gateway = FeishuCardActionGateway(
            dispatcher=CardActionDispatcher(
                {
                    "project.create": ProjectIntentHandler(
                        self.project_controller,
                        bootstrapper=FailingProjectBootstrapper(),
                    ),
                }
            ),
            renderer=FeishuCardRenderer(),
            project_controller=self.project_controller,
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_fail_1"},
                "action": {
                    "value": {
                        "intent_key": "project.create",
                        "surface": "dm",
                        "request_id": "req_project_create_fail_1",
                    },
                    "form_value": {
                        "name": "PoCo",
                    },
                },
            }
        }

        response = failing_gateway.handle_action(payload)

        self.assertEqual(response["toast"]["type"], "warning")
        self.assertEqual(response["instruction"]["refresh_mode"], "ack_only")
        self.assertNotIn("card", response)
        self.assertEqual(self.project_controller.list_projects(), [])

    def test_project_create_keeps_project_when_workspace_notification_fails(self) -> None:
        gateway = FeishuCardActionGateway(
            dispatcher=CardActionDispatcher(
                {
                    "project.create": ProjectIntentHandler(
                        self.project_controller,
                        bootstrapper=NotifyFailingProjectBootstrapper(),
                    ),
                }
            ),
            renderer=FeishuCardRenderer(),
            project_controller=self.project_controller,
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_notify_fail_1"},
                "action": {
                    "value": {
                        "intent_key": "project.create",
                        "surface": "dm",
                        "request_id": "req_project_create_notify_fail_1",
                    },
                    "form_value": {
                        "name": "PoCo",
                    },
                },
            }
        }

        response = gateway.handle_action(payload)

        self.assertEqual(response["toast"]["type"], "success")
        self.assertEqual(len(self.project_controller.list_projects()), 1)
        self.assertIsNotNone(self.project_controller.list_projects()[0].group_chat_id)

    def test_workspace_open_action_returns_workspace_card(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_2"},
                "action": {
                    "value": {
                        "intent_key": "workspace.open",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_workspace_open_1",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "workspace_overview")
        self.assertEqual(response["card"]["data"]["schema"], "2.0")
        self.assertEqual(
            response["card"]["data"]["header"]["title"]["content"],
            f"[Idle] Workspace: {project.name} (codex, no working dir)",
        )
        stop_hint = response["card"]["data"]["body"]["elements"][0]
        self.assertIn("Stop is available only while a task is running.", stop_hint["text"]["content"])
        action_row = response["card"]["data"]["body"]["elements"][1]
        workdir_button = action_row["columns"][0]["elements"][0]
        self.assertEqual(
            workdir_button["behaviors"][0]["value"]["intent_key"],
            "workspace.enter_path",
        )
        self.assertEqual(workdir_button["text"]["content"], "Working Dir")
        change_model_button = action_row["columns"][1]["elements"][0]
        self.assertEqual(change_model_button["text"]["content"], "Model")
        self.assertEqual(
            change_model_button["behaviors"][0]["value"]["surface"],
            "group",
        )
        self.assertEqual(
            change_model_button["behaviors"][0]["value"]["intent_key"],
            "workspace.choose_model",
        )
        updated_project = self.project_controller.get_project(project.id)
        self.assertEqual(updated_project.workspace_message_id, "om_card_2")

    def test_workspace_open_title_includes_latest_task_summary(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        session = self.session_controller.create_session(
            project_id=project.id,
            created_by="ou_demo_user",
        )
        task = self.task_controller.create_task(
            requester_id="ou_demo_user",
            prompt="review the release plan",
            source="feishu_group_message",
            project_id=project.id,
            session_id=session.id,
        )
        task.set_status(task.status.COMPLETED)
        task.set_result("done")
        self.task_controller._store.save(task)  # type: ignore[attr-defined]
        self.session_controller.sync_from_task(task)
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_session_1"},
                "action": {
                    "value": {
                        "intent_key": "workspace.open",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_workspace_session_1",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        title = response["card"]["data"]["header"]["title"]["content"]
        self.assertIn(task.id, title)
        self.assertIn("[Complete]", title)

    def test_workspace_open_shows_latest_task_summary_when_task_exists(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_group_proj_1",
        )
        task = self.task_controller.create_task(
            requester_id="ou_demo_user",
            prompt="Summarize the current API module",
            source="feishu_card",
            project_id=project.id,
            effective_workdir="/srv/poco/api",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_2b"},
                "action": {
                    "value": {
                        "intent_key": "workspace.open",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_workspace_open_2",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertIn(task.id, response["card"]["data"]["header"]["title"]["content"])
        self.assertEqual(len(response["card"]["data"]["body"]["elements"]), 1)

    def test_workspace_open_enables_stop_when_latest_task_is_running(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_group_proj_1",
        )
        task = self.task_controller.create_task(
            requester_id="ou_demo_user",
            prompt="stream output",
            source="feishu_card",
            project_id=project.id,
            effective_workdir="/srv/poco/api",
        )
        task.set_status(task.status.RUNNING)
        self.task_controller._store.save(task)  # type: ignore[attr-defined]
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_running_workspace"},
                "action": {
                    "value": {
                        "intent_key": "workspace.open",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_workspace_open_running",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(
            response["card"]["data"]["header"]["title"]["content"],
            f"[Running] Workspace: {project.name} (stub, /srv/poco/api, {task.id})",
        )
        stop_button = response["card"]["data"]["body"]["elements"][0]
        self.assertEqual(stop_button["behaviors"][0]["value"]["intent_key"], "task.stop")
        self.assertEqual(stop_button["behaviors"][0]["value"]["task_id"], task.id)
        self.assertEqual(len(response["card"]["data"]["body"]["elements"]), 1)

    def test_task_composer_opens_from_workspace_card(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            workdir="/srv/poco/default",
            group_chat_id="oc_group_proj_1",
        )
        self.workspace_controller.set_active_workdir(
            project,
            workdir="/srv/poco/api",
            source="preset",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_task_composer_1"},
                "action": {
                    "value": {
                        "intent_key": "task.open_composer",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_task_composer_1",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "task_composer")
        card = response["card"]["data"]
        self.assertEqual(card["header"]["title"]["content"], "Run Task: PoCo")
        prompt_input = card["body"]["elements"][2]
        self.assertEqual(prompt_input["tag"], "input")
        self.assertEqual(prompt_input["name"], "prompt")
        submit_button = card["body"]["elements"][4]
        self.assertEqual(submit_button["behaviors"][0]["value"]["intent_key"], "task.submit")

    def test_task_submit_creates_task_and_inherits_active_workdir(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            workdir="/srv/poco/default",
            group_chat_id="oc_group_proj_1",
        )
        self.workspace_controller.set_active_workdir(
            project,
            workdir="/srv/poco/api",
            source="preset",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_task_submit_1"},
                "action": {
                    "value": {
                        "intent_key": "task.submit",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_task_submit_1",
                    },
                    "form_value": {
                        "prompt": "Summarize the current API module",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "task_status")
        tasks = self.task_controller.list_tasks()
        self.assertEqual(len(tasks), 1)
        task = tasks[0]
        self.assertEqual(task.project_id, project.id)
        self.assertIsNotNone(task.session_id)
        self.assertEqual(task.effective_workdir, "/srv/poco/api")
        self.assertEqual(task.notification_message_id, "om_task_submit_1")
        self.assertEqual(task.reply_receive_id, "oc_group_proj_1")
        self.assertEqual(task.reply_receive_id_type, "chat_id")
        self.assertEqual(self.task_dispatcher.actions, [("start", task.id)])
        self.assertEqual(
            response["card"]["data"]["header"]["title"]["content"],
            f"[Created] Task: {task.id} (stub, /srv/poco/api)",
        )

    def test_task_open_returns_existing_task_status_card(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        task = self.task_controller.create_task(
            requester_id="ou_demo_user",
            prompt="Summarize the current API module",
            source="feishu_card",
            project_id=project.id,
            effective_workdir="/srv/poco/api",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_task_open_1"},
                "action": {
                    "value": {
                        "intent_key": "task.open",
                        "surface": "group",
                        "project_id": project.id,
                        "task_id": task.id,
                        "request_id": "req_task_open_1",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "task_status")
        self.assertEqual(
            response["card"]["data"]["header"]["title"]["content"],
            f"[Created] Task: {task.id} (stub, /srv/poco/api)",
        )

    def test_task_submit_rejects_empty_prompt(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_task_submit_2"},
                "action": {
                    "value": {
                        "intent_key": "task.submit",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_task_submit_2",
                    },
                    "form_value": {
                        "prompt": "   ",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["toast"]["type"], "warning")
        self.assertEqual(response["instruction"]["refresh_mode"], "ack_only")
        self.assertEqual(self.task_controller.list_tasks(), [])

    def test_task_approve_replaces_card_and_dispatches_resume(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_group_proj_1",
        )
        task = self.task_controller.create_task(
            requester_id="ou_demo_user",
            prompt="confirm: deploy the patch",
            source="feishu_card",
            project_id=project.id,
            effective_workdir="/srv/poco/api",
            reply_receive_id="oc_group_proj_1",
            reply_receive_id_type="chat_id",
        )
        self.task_controller.start_task_execution(task.id)
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_task_approve_1"},
                "action": {
                    "value": {
                        "intent_key": "task.approve",
                        "surface": "group",
                        "project_id": project.id,
                        "task_id": task.id,
                        "request_id": "req_task_approve_1",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "task_status")
        self.assertEqual(
            response["card"]["data"]["header"]["title"]["content"],
            f"[Running] Task: {task.id} (stub, /srv/poco/api)",
        )
        updated = self.task_controller.get_task(task.id)
        self.assertEqual(updated.status.value, "running")
        self.assertIn(("resume", task.id), self.task_dispatcher.actions)

    def test_task_reject_replaces_card_with_cancelled_status(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_group_proj_1",
        )
        task = self.task_controller.create_task(
            requester_id="ou_demo_user",
            prompt="confirm: deploy the patch",
            source="feishu_card",
            project_id=project.id,
            effective_workdir="/srv/poco/api",
            reply_receive_id="oc_group_proj_1",
            reply_receive_id_type="chat_id",
        )
        self.task_controller.start_task_execution(task.id)
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_task_reject_1"},
                "action": {
                    "value": {
                        "intent_key": "task.reject",
                        "surface": "group",
                        "project_id": project.id,
                        "task_id": task.id,
                        "request_id": "req_task_reject_1",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "task_status")
        updated = self.task_controller.get_task(task.id)
        self.assertEqual(updated.status.value, "cancelled")

    def test_task_stop_replaces_card_with_cancelled_status(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_group_proj_1",
        )
        task = self.task_controller.create_task(
            requester_id="ou_demo_user",
            prompt="run the patch",
            source="feishu_card",
            project_id=project.id,
            effective_workdir="/srv/poco/api",
            reply_receive_id="oc_group_proj_1",
            reply_receive_id_type="chat_id",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_task_stop_1"},
                "action": {
                    "value": {
                        "intent_key": "task.stop",
                        "surface": "group",
                        "project_id": project.id,
                        "task_id": task.id,
                        "request_id": "req_task_stop_1",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "task_status")
        updated = self.task_controller.get_task(task.id)
        self.assertEqual(updated.status.value, "cancelled")

    def test_workspace_enter_path_card_opens_from_group(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            workdir="/srv/poco/demo",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_workdir_1"},
                "action": {
                    "value": {
                        "intent_key": "workspace.enter_path",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_workspace_enter_path_direct_1",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "workspace_enter_path")
        self.assertEqual(response["card"]["data"]["header"]["title"]["content"], "Enter Path: PoCo")
        input_box = response["card"]["data"]["body"]["elements"][1]
        self.assertEqual(input_box["tag"], "input")

    def test_workspace_use_default_dir_updates_context(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            workdir="/srv/poco/default",
        )
        self.workspace_controller.set_active_workdir(
            project,
            workdir="/srv/poco/manual",
            source="manual",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_workdir_3"},
                "action": {
                    "value": {
                        "intent_key": "workspace.use_default_dir",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_workspace_use_default_1",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "workspace_use_default_dir")
        summary = response["card"]["data"]["body"]["elements"][0]["content"]
        self.assertIn("/srv/poco/default", summary)
        context = self.workspace_controller.get_context(project)
        self.assertEqual(context.active_workdir, "/srv/poco/default")
        self.assertEqual(context.workdir_source, "default")

    def test_workspace_use_default_dir_rejects_when_not_configured(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_workdir_4"},
                "action": {
                    "value": {
                        "intent_key": "workspace.use_default_dir",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_workspace_use_default_2",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["toast"]["type"], "warning")
        self.assertEqual(response["instruction"]["refresh_mode"], "ack_only")

    def test_workspace_enter_path_subcard_returns_to_workspace(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_workdir_2"},
                "action": {
                    "value": {
                        "intent_key": "workspace.enter_path",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_workspace_enter_path_1",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "workspace_enter_path")
        input_box = response["card"]["data"]["body"]["elements"][1]
        self.assertEqual(input_box["tag"], "input")
        apply_button = response["card"]["data"]["body"]["elements"][3]
        self.assertEqual(
            apply_button["behaviors"][0]["value"]["intent_key"],
            "workspace.apply_entered_path",
        )
        back_button = response["card"]["data"]["body"]["elements"][4]
        self.assertEqual(
            back_button["behaviors"][0]["value"]["intent_key"],
            "workspace.open",
        )

    def test_workspace_apply_entered_path_updates_context(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            workdir="/srv/poco/default",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_workdir_5"},
                "action": {
                    "value": {
                        "intent_key": "workspace.apply_entered_path",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_workspace_apply_path_1",
                    },
                    "form_value": {
                        "workdir": "/srv/poco/manual",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "workspace_overview")
        context = self.workspace_controller.get_context(project)
        self.assertEqual(context.active_workdir, "/srv/poco/manual")
        self.assertEqual(context.workdir_source, "manual")
        self.assertIn("/srv/poco/manual", response["card"]["data"]["header"]["title"]["content"])

    def test_workspace_apply_entered_path_rejects_empty_path(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_workdir_6"},
                "action": {
                    "value": {
                        "intent_key": "workspace.apply_entered_path",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_workspace_apply_path_2",
                    },
                    "form_value": {
                        "workdir": "   ",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["toast"]["type"], "warning")
        self.assertEqual(response["instruction"]["refresh_mode"], "ack_only")

    def test_project_add_dir_preset_updates_project(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_preset_1"},
                "action": {
                    "value": {
                        "intent_key": "project.add_dir_preset",
                        "surface": "dm",
                        "project_id": project.id,
                        "request_id": "req_project_add_preset_1",
                    },
                    "form_value": {
                        "workdir": "/srv/poco/api",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "project_dir_presets")
        updated = self.project_controller.get_project(project.id)
        self.assertEqual(updated.workdir_presets, ["/srv/poco/api"])
        add_button = response["card"]["data"]["body"]["elements"][-1]
        self.assertEqual(add_button["behaviors"][0]["value"]["intent_key"], "project.add_dir_preset")

    def test_workspace_choose_preset_lists_and_applies_presets(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        self.project_controller.add_dir_preset(project.id, "/srv/poco/api")
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_workdir_preset_1"},
                "action": {
                    "value": {
                        "intent_key": "workspace.choose_preset",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_workspace_choose_preset_1",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "workspace_choose_preset")
        use_button = response["card"]["data"]["body"]["elements"][2]
        self.assertEqual(use_button["behaviors"][0]["value"]["intent_key"], "workspace.apply_preset_dir")
        self.assertEqual(use_button["behaviors"][0]["value"]["workdir"], "/srv/poco/api")

        apply_payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_workdir_preset_2"},
                "action": {
                    "value": {
                        "intent_key": "workspace.apply_preset_dir",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_workspace_apply_preset_1",
                        "workdir": "/srv/poco/api",
                    },
                },
            }
        }

        applied = self.gateway.handle_action(apply_payload)

        self.assertEqual(applied["instruction"]["template_key"], "workspace_enter_path")
        context = self.workspace_controller.get_context(project)
        self.assertEqual(context.active_workdir, "/srv/poco/api")
        self.assertEqual(context.workdir_source, "preset")

    def test_workspace_choose_model_opens_and_apply_returns_workspace(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        open_payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_choose_model_1"},
                "action": {
                    "value": {
                        "intent_key": "workspace.choose_model",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_choose_model_1",
                    },
                },
            }
        }

        opened = self.gateway.handle_action(open_payload)

        self.assertEqual(opened["instruction"]["template_key"], "workspace_choose_model")
        apply_payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_choose_model_1"},
                "action": {
                    "value": {
                        "intent_key": "workspace.apply_model",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_apply_model_1",
                        "model": "gpt-5.4",
                    },
                },
            }
        }

        applied = self.gateway.handle_action(apply_payload)

        self.assertEqual(applied["instruction"]["template_key"], "workspace_overview")
        updated = self.project_controller.get_project(project.id)
        self.assertEqual(updated.model, "gpt-5.4")

    def test_workspace_apply_preset_rejects_unknown_preset(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_workdir_preset_3"},
                "action": {
                    "value": {
                        "intent_key": "workspace.apply_preset_dir",
                        "surface": "group",
                        "project_id": project.id,
                        "request_id": "req_workspace_apply_preset_2",
                        "workdir": "/srv/poco/missing",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["toast"]["type"], "warning")
        self.assertEqual(response["instruction"]["refresh_mode"], "ack_only")

    def test_project_config_subcard_opens_agent_config(self) -> None:
        project = self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        payload = {
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_agent_1"},
                "action": {
                    "value": {
                        "intent_key": "project.configure_agent",
                        "surface": "dm",
                        "project_id": project.id,
                        "request_id": "req_project_agent_config_1",
                    },
                },
            }
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "project_agent_config")
        self.assertEqual(response["card"]["data"]["header"]["title"]["content"], "Agent: PoCo")
        self.assertEqual(len(response["card"]["data"]["body"]["elements"]), 2)

    def test_project_list_action_returns_project_list_card(self) -> None:
        self.project_controller.create_project(
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        payload = {
            "event_id": "evt_project_list_1",
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_3"},
                "action": {
                    "value": {
                        "intent_key": "project.list",
                        "surface": "dm",
                    },
                },
            },
        }

        response = self.gateway.handle_action(payload)

        self.assertEqual(response["instruction"]["template_key"], "project_manage")
        self.assertEqual(response["card"]["data"]["header"]["title"]["content"], "Manage Projects")

    def test_write_action_uses_top_level_event_id_for_idempotency(self) -> None:
        payload = {
            "event_id": "evt_project_create_idempotent_1",
            "event": {
                "operator": {"open_id": "ou_demo_user"},
                "context": {"open_message_id": "om_card_4"},
                "action": {
                    "value": {
                        "intent_key": "project.create",
                        "surface": "dm",
                    },
                    "form_value": {
                        "name": "PoCo",
                        "backend": "codex",
                    },
                },
            },
        }

        self.gateway.handle_action(payload)
        self.gateway.handle_action(payload)

        projects = self.project_controller.list_projects()
        self.assertEqual(len(projects), 1)


if __name__ == "__main__":
    unittest.main()
