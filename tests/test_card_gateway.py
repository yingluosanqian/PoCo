from __future__ import annotations

import unittest

from poco.interaction.card_dispatcher import CardActionDispatcher
from poco.interaction.card_handlers import ProjectIntentHandler, WorkspaceIntentHandler
from poco.platform.feishu.card_gateway import FeishuCardActionGateway
from poco.platform.feishu.cards import FeishuCardRenderer
from poco.project.controller import ProjectController
from poco.storage.memory import InMemoryProjectStore


class FeishuCardGatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_controller = ProjectController(InMemoryProjectStore())
        self.gateway = FeishuCardActionGateway(
            dispatcher=CardActionDispatcher(
                {
                    "project.create": ProjectIntentHandler(self.project_controller),
                    "project.open": ProjectIntentHandler(self.project_controller),
                    "project.bind_group": ProjectIntentHandler(self.project_controller),
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
        self.assertEqual(response["card"]["view"], "project_list")

    def test_project_create_action_returns_project_detail_card(self) -> None:
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

        self.assertEqual(response["instruction"]["template_key"], "project_detail")
        self.assertEqual(response["card"]["data"]["view"], "project_detail")
        self.assertEqual(response["card"]["data"]["project"]["name"], "PoCo")
        projects = self.project_controller.list_projects()
        self.assertEqual(len(projects), 1)

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
        self.assertEqual(response["card"]["data"]["view"], "workspace_overview")
        self.assertEqual(response["card"]["data"]["project"]["id"], project.id)


if __name__ == "__main__":
    unittest.main()
