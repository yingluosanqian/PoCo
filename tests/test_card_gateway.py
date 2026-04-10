from __future__ import annotations

import unittest

from poco.interaction.card_dispatcher import CardActionDispatcher
from poco.interaction.card_handlers import ProjectIntentHandler, WorkspaceIntentHandler
from poco.platform.feishu.card_gateway import FeishuCardActionGateway
from poco.platform.feishu.cards import FeishuCardRenderer
from poco.project.bootstrap import ProjectBootstrapError, ProjectBootstrapResult
from poco.project.controller import ProjectController
from poco.storage.memory import InMemoryProjectStore


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


class FeishuCardGatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_controller = ProjectController(InMemoryProjectStore())
        self.bootstrapper = FakeProjectBootstrapper()
        self.project_handler = ProjectIntentHandler(
            self.project_controller,
            bootstrapper=self.bootstrapper,
        )
        self.gateway = FeishuCardActionGateway(
            dispatcher=CardActionDispatcher(
                {
                    "project.list": self.project_handler,
                    "project.create": self.project_handler,
                    "project.open": self.project_handler,
                    "project.configure_agent": self.project_handler,
                    "project.configure_repo": self.project_handler,
                    "project.configure_default_dir": self.project_handler,
                    "project.manage_dir_presets": self.project_handler,
                    "project.bind_group": self.project_handler,
                    "workspace.open": WorkspaceIntentHandler(self.project_controller),
                    "workspace.refresh": WorkspaceIntentHandler(self.project_controller),
                }
            ),
            renderer=FeishuCardRenderer(),
            project_controller=self.project_controller,
        )

    def test_render_dm_project_list_returns_card(self) -> None:
        response = self.gateway.render_dm_project_list()

        self.assertEqual(response["instruction"]["template_key"], "project_list")
        self.assertEqual(response["card"]["schema"], "2.0")
        self.assertEqual(response["card"]["header"]["title"]["content"], "PoCo Projects")
        create_button = response["card"]["body"]["elements"][1]
        self.assertEqual(create_button["tag"], "button")
        self.assertEqual(create_button["text"]["content"], "Create Project + Group")
        self.assertEqual(create_button["behaviors"][0]["type"], "callback")
        self.assertEqual(
            create_button["behaviors"][0]["value"]["intent_key"],
            "project.create",
        )

    def test_project_create_action_returns_project_config_card(self) -> None:
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

        self.assertEqual(response["instruction"]["template_key"], "project_config")
        self.assertEqual(response["card"]["data"]["schema"], "2.0")
        self.assertEqual(response["card"]["data"]["header"]["title"]["content"], "Project: PoCo")
        projects = self.project_controller.list_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].group_chat_id, f"oc_group_{projects[0].id}")
        self.assertEqual(len(self.bootstrapper.calls), 1)
        self.assertEqual(len(self.bootstrapper.workspace_notifications), 1)
        self.assertEqual(
            self.bootstrapper.workspace_notifications[0]["group_chat_id"],
            f"oc_group_{projects[0].id}",
        )
        configure_agent_button = response["card"]["data"]["body"]["elements"][2]
        self.assertEqual(
            configure_agent_button["behaviors"][0]["value"]["intent_key"],
            "project.configure_agent",
        )

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
            f"Workspace: {project.name}",
        )
        refresh_button = response["card"]["data"]["body"]["elements"][4]
        self.assertEqual(
            refresh_button["behaviors"][0]["value"]["surface"],
            "group",
        )

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
        back_button = response["card"]["data"]["body"]["elements"][2]
        self.assertEqual(back_button["behaviors"][0]["value"]["intent_key"], "project.open")

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

        self.assertEqual(response["instruction"]["template_key"], "project_list")
        self.assertEqual(response["card"]["data"]["header"]["title"]["content"], "PoCo Projects")

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
                },
            },
        }

        self.gateway.handle_action(payload)
        self.gateway.handle_action(payload)

        projects = self.project_controller.list_projects()
        self.assertEqual(len(projects), 1)


if __name__ == "__main__":
    unittest.main()
