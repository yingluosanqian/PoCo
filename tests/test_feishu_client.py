from __future__ import annotations

import unittest
from unittest.mock import patch

from poco.interaction.card_dispatcher import build_render_instruction
from poco.interaction.card_handlers import build_workspace_overview_result
from poco.interaction.card_models import DispatchStatus, IntentDispatchResult, RefreshMode, ResourceRefs, Surface, ViewModel
from poco.platform.feishu.client import (
    FeishuAccessTokenProvider,
    FeishuMessageClient,
)
from poco.platform.feishu.cards import FeishuCardRenderer
from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.platform.feishu.project_bootstrap import FeishuProjectBootstrapper
from poco.project.models import Project


class FeishuClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.token_provider = FeishuAccessTokenProvider(
            base_url="https://open.feishu.cn",
            app_id="cli_test",
            app_secret="secret",
        )
        self.client = FeishuMessageClient(
            base_url="https://open.feishu.cn",
            token_provider=self.token_provider,
        )

    def test_create_group_chat_uses_feishu_chat_api(self) -> None:
        with (
            patch.object(self.token_provider, "get_token", return_value="tenant-token"),
            patch("poco.platform.feishu.client._post_json") as post_json,
        ):
            post_json.return_value = {
                "code": 0,
                "data": {
                    "chat_id": "oc_group_123",
                    "name": "PoCo | Demo",
                },
            }

            result = self.client.create_group_chat(
                name="PoCo | Demo",
                owner_open_id="ou_demo_user",
            )

        self.assertEqual(result.chat_id, "oc_group_123")
        self.assertEqual(result.name, "PoCo | Demo")
        kwargs = post_json.call_args.kwargs
        self.assertIn("/open-apis/im/v1/chats?", kwargs["url"])
        self.assertIn("user_id_type=open_id", kwargs["url"])
        self.assertIn("set_bot_manager=true", kwargs["url"])
        self.assertEqual(kwargs["payload"]["name"], "PoCo | Demo")
        self.assertEqual(kwargs["payload"]["owner_id"], "ou_demo_user")
        self.assertEqual(kwargs["payload"]["chat_mode"], "group")
        self.assertEqual(kwargs["payload"]["chat_type"], "private")
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer tenant-token",
        )

    def test_workspace_renderer_uses_group_surface_for_workspace_cards(self) -> None:
        project = Project(
            id="proj_1",
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_group_proj_1",
        )
        instruction = build_render_instruction(
            build_workspace_overview_result(project),
            surface=Surface.GROUP,
        )

        card = FeishuCardRenderer().render(instruction)

        change_workdir_button = card["body"]["elements"][6]
        refresh_button = card["body"]["elements"][7]
        back_button = card["body"]["elements"][8]
        self.assertEqual(
            change_workdir_button["behaviors"][0]["value"]["surface"],
            "group",
        )
        self.assertEqual(refresh_button["behaviors"][0]["value"]["surface"], "group")
        self.assertEqual(back_button["behaviors"][0]["value"]["surface"], "group")

    def test_project_bootstrapper_sends_workspace_card_to_created_group(self) -> None:
        class FakeMessageClient:
            def __init__(self) -> None:
                self.sent_cards: list[dict[str, object]] = []

            def send_interactive(
                self,
                *,
                receive_id: str,
                receive_id_type: str,
                card: dict[str, object],
            ) -> None:
                self.sent_cards.append(
                    {
                        "receive_id": receive_id,
                        "receive_id_type": receive_id_type,
                        "card": card,
                    }
                )

        project = Project(
            id="proj_1",
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            group_chat_id="oc_group_proj_1",
        )
        message_client = FakeMessageClient()
        recorder = FeishuDebugRecorder()
        bootstrapper = FeishuProjectBootstrapper(
            message_client,  # type: ignore[arg-type]
            renderer=FeishuCardRenderer(),
            debug_recorder=recorder,
        )

        bootstrapper.notify_project_workspace(
            project=project,
            actor_id="ou_demo_user",
        )

        self.assertEqual(len(message_client.sent_cards), 1)
        sent = message_client.sent_cards[0]
        self.assertEqual(sent["receive_id"], "oc_group_proj_1")
        self.assertEqual(sent["receive_id_type"], "chat_id")
        card = sent["card"]
        self.assertEqual(card["header"]["title"]["content"], "Workspace: PoCo")
        refresh_button = card["body"]["elements"][7]
        self.assertEqual(refresh_button["behaviors"][0]["value"]["surface"], "group")
        snapshot = recorder.snapshot()
        self.assertEqual(snapshot["outbound_attempts"][0]["source"], "project_workspace_bootstrap")

    def test_workspace_enter_path_card_contains_input_and_apply(self) -> None:
        project = Project(
            id="proj_1",
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        card = FeishuCardRenderer().render(
            build_render_instruction(
                IntentDispatchResult(
                    status=DispatchStatus.OK,
                    intent_key="workspace.enter_path",
                    resource_refs=ResourceRefs(project_id=project.id),
                    view_model=ViewModel(
                        "workspace_enter_path",
                        {
                            "project": project.to_dict(),
                            "current_workdir": "/srv/poco/manual",
                            "note": "Manual path entry is a fallback path.",
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.GROUP,
            )
        )

        input_box = card["body"]["elements"][1]
        apply_button = card["body"]["elements"][3]
        self.assertEqual(input_box["tag"], "input")
        self.assertEqual(input_box["name"], "workdir")
        self.assertEqual(apply_button["behaviors"][0]["value"]["intent_key"], "workspace.apply_entered_path")
        self.assertEqual(apply_button["behaviors"][0]["value"]["surface"], "group")


if __name__ == "__main__":
    unittest.main()
