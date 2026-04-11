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
from poco.project.controller import ProjectController
from poco.project.models import Project
from poco.storage.memory import InMemoryProjectStore


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
            patch("poco.platform.feishu.client._request_json") as request_json,
        ):
            request_json.return_value = {
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
        kwargs = request_json.call_args.kwargs
        self.assertEqual(kwargs["method"], "POST")
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

    def test_update_interactive_uses_patch_message_api(self) -> None:
        with (
            patch.object(self.token_provider, "get_token", return_value="tenant-token"),
            patch("poco.platform.feishu.client._request_json") as request_json,
        ):
            request_json.return_value = {
                "code": 0,
                "data": {
                    "message_id": "om_updated_123",
                },
            }

            result = self.client.update_interactive(
                message_id="om_original_123",
                card={"schema": "2.0"},
            )

        self.assertEqual(result.message_id, "om_updated_123")
        kwargs = request_json.call_args.kwargs
        self.assertEqual(kwargs["method"], "PATCH")
        self.assertIn("/open-apis/im/v1/messages/om_original_123", kwargs["url"])
        self.assertEqual(kwargs["payload"]["msg_type"], "interactive")

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

        change_workdir_button = card["body"]["elements"][5]
        change_model_button = card["body"]["elements"][6]
        self.assertEqual(
            change_workdir_button["behaviors"][0]["value"]["surface"],
            "group",
        )
        self.assertEqual(change_model_button["behaviors"][0]["value"]["surface"], "group")
        self.assertEqual(
            change_model_button["behaviors"][0]["value"]["intent_key"],
            "project.configure_agent",
        )

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
                return type(
                    "SendResult",
                    (),
                    {"message_id": "om_workspace_bootstrap_1"},
                )()

        project_controller = ProjectController(InMemoryProjectStore())
        project = project_controller.create_project(
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
            project_controller=project_controller,
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
        change_model_button = card["body"]["elements"][6]
        self.assertEqual(change_model_button["behaviors"][0]["value"]["surface"], "group")
        self.assertEqual(project.workspace_message_id, "om_workspace_bootstrap_1")
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

    def test_project_dir_presets_card_contains_input_and_add(self) -> None:
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
                    intent_key="project.manage_dir_presets",
                    resource_refs=ResourceRefs(project_id=project.id),
                    view_model=ViewModel(
                        "project_dir_presets",
                        {
                            "project": project.to_dict(),
                            "presets": ["/srv/poco/api"],
                            "note": "Dir presets are managed from DM.",
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.DM,
            )
        )

        input_box = card["body"]["elements"][2]
        add_button = card["body"]["elements"][4]
        self.assertEqual(input_box["tag"], "input")
        self.assertEqual(input_box["name"], "workdir")
        self.assertEqual(add_button["behaviors"][0]["value"]["intent_key"], "project.add_dir_preset")

    def test_workspace_choose_preset_card_contains_apply_buttons(self) -> None:
        project = Project(
            id="proj_1",
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            workdir_presets=["/srv/poco/api"],
        )
        card = FeishuCardRenderer().render(
            build_render_instruction(
                IntentDispatchResult(
                    status=DispatchStatus.OK,
                    intent_key="workspace.choose_preset",
                    resource_refs=ResourceRefs(project_id=project.id),
                    view_model=ViewModel(
                        "workspace_choose_preset",
                        {
                            "project": project.to_dict(),
                            "presets": list(project.workdir_presets),
                            "note": "Choose a preset.",
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.GROUP,
            )
        )

        use_button = card["body"]["elements"][2]
        self.assertEqual(use_button["behaviors"][0]["value"]["intent_key"], "workspace.apply_preset_dir")
        self.assertEqual(use_button["behaviors"][0]["value"]["workdir"], "/srv/poco/api")

    def test_task_composer_card_contains_prompt_input_and_submit(self) -> None:
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
                    intent_key="task.open_composer",
                    resource_refs=ResourceRefs(project_id=project.id),
                    view_model=ViewModel(
                        "task_composer",
                        {
                            "project": project.to_dict(),
                            "current_agent": "codex",
                            "current_workdir": "/srv/poco/api",
                            "note": "Task submit inherits the current workspace workdir.",
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.GROUP,
            )
        )

        prompt_input = card["body"]["elements"][2]
        submit_button = card["body"]["elements"][4]
        self.assertEqual(prompt_input["tag"], "input")
        self.assertEqual(prompt_input["name"], "prompt")
        self.assertEqual(submit_button["behaviors"][0]["value"]["intent_key"], "task.submit")
        self.assertEqual(submit_button["behaviors"][0]["value"]["surface"], "group")

    def test_task_status_card_contains_approve_reject_buttons_when_waiting(self) -> None:
        task = {
            "id": "task_1",
            "project_id": "proj_1",
            "agent_backend": "codex",
            "effective_workdir": "/srv/poco/api",
            "prompt": "confirm: deploy",
            "status": "waiting_for_confirmation",
            "awaiting_confirmation_reason": "Need approval before deploy.",
            "result_summary": None,
        }
        card = FeishuCardRenderer().render(
            build_render_instruction(
                IntentDispatchResult(
                    status=DispatchStatus.OK,
                    intent_key="task.status",
                    resource_refs=ResourceRefs(project_id="proj_1", task_id="task_1"),
                    view_model=ViewModel(
                        "task_status",
                        {
                            "task": task,
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.GROUP,
            )
        )

        self.assertEqual(
            card["header"]["title"]["content"],
            "[Waiting] Task: task_1 (codex, /srv/poco/api)",
        )
        self.assertEqual(card["body"]["elements"][0]["text"]["content"], "Need approval before deploy.")
        approve_button = card["body"]["elements"][1]
        stop_button = card["body"]["elements"][2]
        self.assertEqual(approve_button["behaviors"][0]["value"]["intent_key"], "task.approve")
        self.assertEqual(approve_button["behaviors"][0]["value"]["task_id"], "task_1")
        self.assertEqual(stop_button["behaviors"][0]["value"]["intent_key"], "task.stop")
        self.assertEqual(card["body"]["elements"][3]["behaviors"][0]["value"]["intent_key"], "workspace.open_workdir_switcher")
        self.assertEqual(card["body"]["elements"][4]["behaviors"][0]["value"]["intent_key"], "project.configure_agent")

    def test_task_status_card_contains_result_when_completed(self) -> None:
        task = {
            "id": "task_2",
            "project_id": "proj_1",
            "agent_backend": "codex",
            "effective_workdir": "/srv/poco/api",
            "prompt": "summarize",
            "status": "completed",
            "awaiting_confirmation_reason": None,
            "raw_result": "Done.",
        }
        card = FeishuCardRenderer().render(
            build_render_instruction(
                IntentDispatchResult(
                    status=DispatchStatus.OK,
                    intent_key="task.status",
                    resource_refs=ResourceRefs(project_id="proj_1", task_id="task_2"),
                    view_model=ViewModel(
                        "task_status",
                        {
                            "task": task,
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.GROUP,
            )
        )

        self.assertEqual(
            card["header"]["title"]["content"],
            "[Complete] Task: task_2 (codex, /srv/poco/api)",
        )
        result_block = card["body"]["elements"][0]
        self.assertIn("Done.", result_block["text"]["content"])
        self.assertEqual(card["body"]["elements"][1]["behaviors"][0]["value"]["intent_key"], "workspace.open_workdir_switcher")
        self.assertEqual(card["body"]["elements"][2]["behaviors"][0]["value"]["intent_key"], "project.configure_agent")

    def test_task_status_card_shows_live_output_when_running(self) -> None:
        task = {
            "id": "task_run_1",
            "project_id": "proj_1",
            "agent_backend": "codex",
            "effective_workdir": "/srv/poco/api",
            "prompt": "build project",
            "status": "running",
            "awaiting_confirmation_reason": None,
            "live_output": "Step 1\nStep 2",
        }
        card = FeishuCardRenderer().render(
            build_render_instruction(
                IntentDispatchResult(
                    status=DispatchStatus.OK,
                    intent_key="task.status",
                    resource_refs=ResourceRefs(project_id="proj_1", task_id="task_run_1"),
                    view_model=ViewModel(
                        "task_status",
                        {
                            "task": task,
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.GROUP,
            )
        )

        self.assertEqual(
            card["header"]["title"]["content"],
            "[Running] Task: task_run_1 (codex, /srv/poco/api)",
        )
        live_block = card["body"]["elements"][0]
        self.assertIn("Step 1", live_block["text"]["content"])
        self.assertEqual(card["body"]["elements"][1]["behaviors"][0]["value"]["intent_key"], "task.stop")
        self.assertEqual(card["body"]["elements"][2]["behaviors"][0]["value"]["intent_key"], "workspace.open_workdir_switcher")
        self.assertEqual(card["body"]["elements"][3]["behaviors"][0]["value"]["intent_key"], "project.configure_agent")

    def test_task_status_card_adds_pagination_for_long_raw_result(self) -> None:
        task = {
            "id": "task_3",
            "project_id": "proj_1",
            "agent_backend": "codex",
            "effective_workdir": "/srv/poco/api",
            "prompt": "summarize",
            "status": "completed",
            "awaiting_confirmation_reason": None,
            "raw_result": "A" * 5000,
        }
        card = FeishuCardRenderer().render(
            build_render_instruction(
                IntentDispatchResult(
                    status=DispatchStatus.OK,
                    intent_key="task.status",
                    resource_refs=ResourceRefs(project_id="proj_1", task_id="task_3"),
                    view_model=ViewModel(
                        "task_status",
                        {
                            "task": task,
                            "result_page": 1,
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.GROUP,
            )
        )

        self.assertEqual(
            card["header"]["title"]["content"],
            "[Complete] Task: task_3 (codex, /srv/poco/api) [1/3]",
        )
        next_button = card["body"]["elements"][1]
        self.assertEqual(next_button["behaviors"][0]["value"]["intent_key"], "task.open")
        self.assertEqual(next_button["behaviors"][0]["value"]["page"], "2")
        self.assertEqual(card["body"]["elements"][2]["behaviors"][0]["value"]["intent_key"], "workspace.open_workdir_switcher")
        self.assertEqual(card["body"]["elements"][3]["behaviors"][0]["value"]["intent_key"], "project.configure_agent")


if __name__ == "__main__":
    unittest.main()
