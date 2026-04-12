from __future__ import annotations

import unittest
from unittest.mock import patch

from poco.interaction.card_dispatcher import build_render_instruction
from poco.interaction.card_handlers import build_workspace_overview_result
from poco.interaction.card_models import DispatchStatus, IntentDispatchResult, RefreshMode, ResourceRefs, Surface, ViewModel
from poco.platform.feishu.client import (
    FeishuAccessTokenProvider,
    FeishuChatDeleteForbiddenError,
    FeishuChatNotFoundError,
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

    def test_delete_group_chat_uses_delete_chat_api(self) -> None:
        with (
            patch.object(self.token_provider, "get_token", return_value="tenant-token"),
            patch("poco.platform.feishu.client._request_json") as request_json,
        ):
            request_json.return_value = {
                "code": 0,
                "data": {},
            }

            self.client.delete_group_chat(chat_id="oc_group_123")

        kwargs = request_json.call_args.kwargs
        self.assertEqual(kwargs["method"], "DELETE")
        self.assertIn("/open-apis/im/v1/chats/oc_group_123", kwargs["url"])

    def test_delete_group_chat_raises_not_found_for_missing_group(self) -> None:
        with (
            patch.object(self.token_provider, "get_token", return_value="tenant-token"),
            patch("poco.platform.feishu.client._request_json") as request_json,
        ):
            request_json.return_value = {
                "code": 232006,
                "msg": "chat not found",
            }

            with self.assertRaises(FeishuChatNotFoundError):
                self.client.delete_group_chat(chat_id="oc_group_missing")

    def test_delete_group_chat_raises_forbidden_for_permission_denied(self) -> None:
        with (
            patch.object(self.token_provider, "get_token", return_value="tenant-token"),
            patch("poco.platform.feishu.client._request_json") as request_json,
        ):
            request_json.return_value = {
                "code": 232017,
                "msg": "forbidden",
            }

            with self.assertRaises(FeishuChatDeleteForbiddenError):
                self.client.delete_group_chat(chat_id="oc_group_forbidden")

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

        self.assertEqual(
            card["header"]["title"]["content"],
            "[Idle] Workspace: PoCo (codex, no working dir)",
        )
        idle_hint = card["body"]["elements"][0]
        action_row = card["body"]["elements"][1]
        change_workdir_button = action_row["columns"][0]["elements"][0]
        change_model_button = action_row["columns"][1]["elements"][0]
        self.assertIn("Stop is available only while a task is running.", idle_hint["text"]["content"])
        self.assertEqual(action_row["tag"], "column_set")
        self.assertEqual(
            change_workdir_button["behaviors"][0]["value"]["intent_key"],
            "workspace.enter_path",
        )
        self.assertEqual(change_workdir_button["text"]["content"], "Working Dir")
        self.assertEqual(change_model_button["text"]["content"], "Agent")
        self.assertEqual(change_model_button["behaviors"][0]["value"]["surface"], "group")
        self.assertEqual(
            change_model_button["behaviors"][0]["value"]["intent_key"],
            "workspace.choose_agent",
        )

    def test_workspace_renderer_shows_queue_count_in_title(self) -> None:
        project = Project(
            id="proj_queue",
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
        )
        instruction = build_render_instruction(
            IntentDispatchResult(
                status=DispatchStatus.OK,
                intent_key="workspace.open",
                resource_refs=ResourceRefs(project_id=project.id),
                view_model=ViewModel(
                    "workspace_overview",
                    {
                        "project": project.to_dict(),
                        "latest_task_status": "running",
                        "latest_task_id": "task_run_1",
                        "current_agent": "codex",
                        "current_model": None,
                        "stop_enabled": True,
                        "pending_approvals": 0,
                        "current_workdir": "/srv/poco/api",
                        "workdir_source": "manual",
                        "queue_count": 2,
                    },
                ),
                refresh_mode=RefreshMode.REPLACE_CURRENT,
            ),
            surface=Surface.GROUP,
        )

        card = FeishuCardRenderer().render(instruction)

        self.assertEqual(
            card["header"]["title"]["content"],
            "[Running] Workspace: PoCo (codex, /srv/poco/api, task_run_1, queue 2)",
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
        self.assertEqual(card["header"]["title"]["content"], "[Idle] Workspace: PoCo (codex, no working dir)")
        action_row = card["body"]["elements"][1]
        change_workdir_button = action_row["columns"][0]["elements"][0]
        change_model_button = action_row["columns"][1]["elements"][0]
        self.assertEqual(
            change_workdir_button["behaviors"][0]["value"]["intent_key"],
            "workspace.enter_path",
        )
        self.assertEqual(change_model_button["behaviors"][0]["value"]["surface"], "group")
        self.assertEqual(project.workspace_message_id, "om_workspace_bootstrap_1")
        snapshot = recorder.snapshot()
        self.assertEqual(snapshot["outbound_attempts"][0]["source"], "project_workspace_bootstrap")

    def test_workspace_enter_path_card_contains_browse_controls(self) -> None:
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
                            "browse_path": "/srv/poco",
                            "parent_path": "/srv",
                            "child_dirs": ["/srv/poco/api", "/srv/poco/web"],
                            "mode": "browse",
                            "error": "",
                            "note": "Manual path entry is a fallback path.",
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.GROUP,
            )
        )

        self.assertEqual(card["header"]["title"]["content"], "Working Dir: PoCo")
        browse_summary = card["body"]["elements"][0]
        browse_form = card["body"]["elements"][1]
        select_box = browse_form["elements"][0]
        action_row = browse_form["elements"][1]
        open_button = action_row["columns"][0]["elements"][0]
        apply_button = action_row["columns"][1]["elements"][0]
        manual_shortcut = action_row["columns"][2]["elements"][0]
        cancel_button = action_row["columns"][3]["elements"][0]
        self.assertEqual(browse_summary["tag"], "markdown")
        self.assertEqual(select_box["tag"], "select_static")
        self.assertEqual(select_box["name"], "browse_path")
        self.assertEqual(select_box["options"][0]["value"], "/srv")
        self.assertEqual(select_box["options"][0]["text"]["content"], "..")
        self.assertEqual(select_box["options"][1]["value"], "/srv/poco/api")
        self.assertEqual(action_row["tag"], "column_set")
        self.assertEqual(open_button["form_action_type"], "submit")
        self.assertEqual(open_button["behaviors"][0]["value"]["intent_key"], "workspace.enter_path")
        self.assertEqual(open_button["behaviors"][0]["value"]["mode"], "browse")
        self.assertEqual(apply_button["behaviors"][0]["value"]["intent_key"], "workspace.apply_entered_path")
        self.assertEqual(apply_button["behaviors"][0]["value"]["mode"], "browse")
        self.assertEqual(apply_button["behaviors"][0]["value"]["browse_path"], "/srv/poco")
        self.assertEqual(manual_shortcut["behaviors"][0]["value"]["intent_key"], "workspace.enter_path_manual")
        self.assertEqual(manual_shortcut["behaviors"][0]["value"]["mode"], "manual")
        self.assertEqual(cancel_button["behaviors"][0]["value"]["intent_key"], "workspace.open")
        self.assertEqual(cancel_button["behaviors"][0]["value"]["mode"], "browse")

    def test_workspace_manual_path_card_contains_input_and_back_to_browse(self) -> None:
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
                    intent_key="workspace.enter_path_manual",
                    resource_refs=ResourceRefs(project_id=project.id),
                    view_model=ViewModel(
                        "workspace_enter_path",
                        {
                            "project": project.to_dict(),
                            "current_workdir": "/srv/poco/manual",
                            "browse_path": "/srv/poco",
                            "parent_path": "/srv",
                            "child_dirs": ["/srv/poco/api", "/srv/poco/web"],
                            "mode": "manual",
                            "error": "",
                            "note": "Manual path entry is a fallback path.",
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.GROUP,
            )
        )

        self.assertEqual(card["header"]["title"]["content"], "Working Dir: PoCo")
        form = card["body"]["elements"][1]
        self.assertIn("Or enter path manually", form["elements"][0]["content"])
        input_box = form["elements"][1]
        action_row = form["elements"][2]
        apply_button = action_row["columns"][0]["elements"][0]
        back_button = action_row["columns"][1]["elements"][0]
        cancel_button = action_row["columns"][2]["elements"][0]
        self.assertEqual(input_box["tag"], "input")
        self.assertEqual(apply_button["behaviors"][0]["value"]["intent_key"], "workspace.apply_entered_path")
        self.assertEqual(apply_button["behaviors"][0]["value"]["mode"], "manual")
        self.assertEqual(back_button["behaviors"][0]["value"]["intent_key"], "workspace.enter_path")
        self.assertEqual(back_button["behaviors"][0]["value"]["mode"], "browse")
        self.assertEqual(cancel_button["behaviors"][0]["value"]["intent_key"], "workspace.open")
        self.assertEqual(cancel_button["behaviors"][0]["value"]["mode"], "manual")

    def test_workspace_choose_agent_card_contains_model_and_access_dropdowns(self) -> None:
        project = Project(
            id="proj_1",
            name="PoCo",
            created_by="ou_demo_user",
            backend="codex",
            model="gpt-5.4",
            sandbox="workspace-write",
        )
        card = FeishuCardRenderer().render(
            build_render_instruction(
                IntentDispatchResult(
                    status=DispatchStatus.OK,
                    intent_key="workspace.choose_agent",
                    resource_refs=ResourceRefs(project_id=project.id),
                    view_model=ViewModel(
                        "workspace_choose_agent",
                        {
                            "project": project.to_dict(),
                            "agent_label": "Codex",
                            "current_model": "gpt-5.4",
                            "model_options": [
                                {"label": "gpt-5.4", "value": "gpt-5.4"},
                                {"label": "gpt-5.4-mini", "value": "gpt-5.4-mini"},
                            ],
                            "config_fields": [
                                {
                                    "key": "sandbox",
                                    "label": "Access",
                                    "current_value": "workspace-write",
                                    "options": [
                                        {"label": "Read Only", "value": "read-only"},
                                        {"label": "Project Only", "value": "workspace-write"},
                                        {"label": "Full Access", "value": "danger-full-access"},
                                    ],
                                }
                            ],
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.GROUP,
            )
        )

        self.assertEqual(card["header"]["title"]["content"], "Config Agent: PoCo")
        form = card["body"]["elements"][1]
        self.assertEqual(form["tag"], "form")
        self.assertEqual(form["elements"][0]["tag"], "select_static")
        self.assertEqual(form["elements"][0]["name"], "model")
        self.assertEqual(form["elements"][0]["value"], "gpt-5.4")
        self.assertEqual(form["elements"][1]["tag"], "select_static")
        self.assertEqual(form["elements"][1]["name"], "sandbox")
        self.assertEqual(form["elements"][1]["value"], "workspace-write")
        action_row = form["elements"][2]
        self.assertEqual(action_row["tag"], "column_set")
        self.assertEqual(
            action_row["columns"][0]["elements"][0]["behaviors"][0]["value"]["intent_key"],
            "workspace.apply_agent",
        )
        self.assertEqual(
            action_row["columns"][1]["elements"][0]["behaviors"][0]["value"]["intent_key"],
            "workspace.open",
        )

    def test_workspace_choose_agent_card_contains_cursor_specific_dropdowns(self) -> None:
        project = Project(
            id="proj_cursor",
            name="PoCo Cursor",
            created_by="ou_demo_user",
            backend="cursor_agent",
            backend_config={"model": "gpt-5", "mode": "plan", "sandbox": "enabled"},
        )
        card = FeishuCardRenderer().render(
            build_render_instruction(
                IntentDispatchResult(
                    status=DispatchStatus.OK,
                    intent_key="workspace.choose_agent",
                    resource_refs=ResourceRefs(project_id=project.id),
                    view_model=ViewModel(
                        "workspace_choose_agent",
                        {
                            "project": project.to_dict(),
                            "agent_label": "Cursor Agent",
                            "current_model": "gpt-5",
                            "model_options": [
                                {"label": "gpt-5", "value": "gpt-5"},
                                {"label": "sonnet-4", "value": "sonnet-4"},
                            ],
                            "config_fields": [
                                {
                                    "key": "mode",
                                    "label": "Mode",
                                    "current_value": "plan",
                                    "options": [
                                        {"label": "Default", "value": "default"},
                                        {"label": "Plan", "value": "plan"},
                                        {"label": "Ask", "value": "ask"},
                                    ],
                                },
                                {
                                    "key": "sandbox",
                                    "label": "Sandbox",
                                    "current_value": "enabled",
                                    "options": [
                                        {"label": "Default", "value": "default"},
                                        {"label": "Enabled", "value": "enabled"},
                                        {"label": "Disabled", "value": "disabled"},
                                    ],
                                },
                            ],
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.GROUP,
            )
        )

        form = card["body"]["elements"][1]
        self.assertEqual(form["elements"][0]["name"], "model")
        self.assertEqual(form["elements"][1]["name"], "mode")
        self.assertEqual(form["elements"][1]["value"], "plan")
        self.assertEqual(form["elements"][2]["name"], "sandbox")
        self.assertEqual(form["elements"][2]["value"], "enabled")

    def test_workspace_choose_agent_card_contains_coco_specific_dropdowns(self) -> None:
        project = Project(
            id="proj_coco",
            name="PoCo Trae",
            created_by="ou_demo_user",
            backend="coco",
            backend_config={"model": "GPT-5.2", "approval_mode": "yolo"},
        )
        card = FeishuCardRenderer().render(
            build_render_instruction(
                IntentDispatchResult(
                    status=DispatchStatus.OK,
                    intent_key="workspace.choose_agent",
                    resource_refs=ResourceRefs(project_id=project.id),
                    view_model=ViewModel(
                        "workspace_choose_agent",
                        {
                            "project": project.to_dict(),
                            "agent_label": "Trae CLI",
                            "current_model": "GPT-5.2",
                            "model_options": [
                                {"label": "GPT-5.2", "value": "GPT-5.2"},
                            ],
                            "config_fields": [
                                {
                                    "key": "approval_mode",
                                    "label": "Permission",
                                    "current_value": "yolo",
                                    "options": [
                                        {"label": "Default", "value": "default"},
                                        {"label": "YOLO", "value": "yolo"},
                                    ],
                                },
                            ],
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.GROUP,
            )
        )

        form = card["body"]["elements"][1]
        self.assertEqual(form["elements"][0]["name"], "model")
        self.assertEqual(form["elements"][1]["name"], "approval_mode")
        self.assertEqual(form["elements"][1]["value"], "yolo")

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
        self.assertEqual(card["body"]["elements"][0]["tag"], "markdown")
        self.assertIn("Need approval before deploy.", card["body"]["elements"][0]["content"])
        approve_button = card["body"]["elements"][1]
        stop_button = card["body"]["elements"][2]
        self.assertEqual(approve_button["behaviors"][0]["value"]["intent_key"], "task.approve")
        self.assertEqual(approve_button["behaviors"][0]["value"]["task_id"], "task_1")
        self.assertEqual(stop_button["behaviors"][0]["value"]["intent_key"], "task.stop")
        self.assertEqual(len(card["body"]["elements"]), 3)

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
        action_row = card["body"]["elements"][1]
        change_workdir_button = action_row["columns"][0]["elements"][0]
        change_model_button = action_row["columns"][1]["elements"][0]
        self.assertEqual(result_block["tag"], "markdown")
        self.assertIn("Done.", result_block["content"])
        self.assertEqual(change_workdir_button["behaviors"][0]["value"]["intent_key"], "workspace.enter_path")
        self.assertEqual(change_model_button["behaviors"][0]["value"]["intent_key"], "workspace.choose_agent")

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
        self.assertEqual(live_block["tag"], "markdown")
        self.assertIn("Step 1", live_block["content"])
        self.assertEqual(card["body"]["elements"][1]["behaviors"][0]["value"]["intent_key"], "task.stop")
        self.assertEqual(len(card["body"]["elements"]), 2)

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
        action_row = card["body"]["elements"][2]
        change_workdir_button = action_row["columns"][0]["elements"][0]
        change_model_button = action_row["columns"][1]["elements"][0]
        self.assertEqual(next_button["behaviors"][0]["value"]["intent_key"], "task.open")
        self.assertEqual(next_button["behaviors"][0]["value"]["page"], "2")
        self.assertEqual(change_workdir_button["behaviors"][0]["value"]["intent_key"], "workspace.enter_path")
        self.assertEqual(change_model_button["behaviors"][0]["value"]["intent_key"], "workspace.choose_agent")

    def test_task_status_card_adds_pagination_for_long_live_output(self) -> None:
        task = {
            "id": "task_run_long",
            "project_id": "proj_1",
            "agent_backend": "codex",
            "effective_workdir": "/srv/poco/api",
            "prompt": "stream output",
            "status": "running",
            "awaiting_confirmation_reason": None,
            "live_output": "A" * 5000,
        }
        card = FeishuCardRenderer().render(
            build_render_instruction(
                IntentDispatchResult(
                    status=DispatchStatus.OK,
                    intent_key="task.status",
                    resource_refs=ResourceRefs(project_id="proj_1", task_id="task_run_long"),
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
            "[Running] Task: task_run_long (codex, /srv/poco/api) [1/3]",
        )
        next_button = card["body"]["elements"][1]
        stop_button = card["body"]["elements"][2]
        self.assertEqual(next_button["behaviors"][0]["value"]["intent_key"], "task.open")
        self.assertEqual(next_button["behaviors"][0]["value"]["page"], "2")
        self.assertEqual(stop_button["behaviors"][0]["value"]["intent_key"], "task.stop")

    def test_task_status_card_uses_stopped_title_and_grey_template_when_cancelled(self) -> None:
        task = {
            "id": "task_stop_1",
            "project_id": "proj_1",
            "agent_backend": "codex",
            "effective_workdir": "/srv/poco/api",
            "prompt": "stop me",
            "status": "cancelled",
            "awaiting_confirmation_reason": None,
            "raw_result": "Task stopped by user.",
        }
        card = FeishuCardRenderer().render(
            build_render_instruction(
                IntentDispatchResult(
                    status=DispatchStatus.OK,
                    intent_key="task.status",
                    resource_refs=ResourceRefs(project_id="proj_1", task_id="task_stop_1"),
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
            "[Stopped] Task: task_stop_1 (codex, /srv/poco/api)",
        )
        self.assertEqual(card["header"]["template"], "grey")
        self.assertEqual(card["body"]["elements"][0]["tag"], "markdown")
        self.assertEqual(card["body"]["elements"][1]["tag"], "column_set")

    def test_task_status_card_shows_queue_position_and_blocking_task(self) -> None:
        task = {
            "id": "task_queue_1",
            "project_id": "proj_1",
            "agent_backend": "codex",
            "effective_workdir": "/srv/poco/api",
            "prompt": "queued work",
            "status": "queued",
            "awaiting_confirmation_reason": None,
            "raw_result": None,
        }
        card = FeishuCardRenderer().render(
            build_render_instruction(
                IntentDispatchResult(
                    status=DispatchStatus.OK,
                    intent_key="task.status",
                    resource_refs=ResourceRefs(project_id="proj_1", task_id="task_queue_1"),
                    view_model=ViewModel(
                        "task_status",
                        {
                            "task": task,
                            "queue_position": 2,
                            "blocking_task_id": "task_run_1",
                        },
                    ),
                    refresh_mode=RefreshMode.REPLACE_CURRENT,
                ),
                surface=Surface.GROUP,
            )
        )

        self.assertEqual(
            card["header"]["title"]["content"],
            "[Queued] Task: task_queue_1 (codex, /srv/poco/api)",
        )
        self.assertIn("Queue position: **2**", card["body"]["elements"][0]["content"])
        self.assertIn("Waiting for task `task_run_1` to finish.", card["body"]["elements"][0]["content"])


if __name__ == "__main__":
    unittest.main()
