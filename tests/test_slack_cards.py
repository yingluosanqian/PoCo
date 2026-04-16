from __future__ import annotations

import json
import unittest
from typing import Any

from poco.interaction.card_models import (
    PlatformRenderInstruction,
    RefreshMode,
    RenderTarget,
    Surface,
)
from poco.platform.slack.cards import SlackCardRenderer


def _instruction(
    template_key: str | None,
    template_data: dict[str, Any],
    *,
    surface: Surface = Surface.DM,
) -> PlatformRenderInstruction:
    return PlatformRenderInstruction(
        surface=surface,
        render_target=RenderTarget.CURRENT_CARD,
        template_key=template_key,
        template_data=template_data,
        refresh_mode=RefreshMode.REPLACE_CURRENT,
    )


def _block_types(message: dict[str, Any]) -> list[str]:
    return [block.get("type") for block in message.get("blocks", [])]


def _action_buttons(message: dict[str, Any]) -> list[dict[str, Any]]:
    buttons: list[dict[str, Any]] = []
    for block in message.get("blocks", []):
        if block.get("type") != "actions":
            continue
        for element in block.get("elements", []):
            if element.get("type") == "button":
                buttons.append(element)
    return buttons


class SlackCardRendererTest(unittest.TestCase):
    def setUp(self) -> None:
        self.renderer = SlackCardRenderer()

    def test_project_home_renders_new_and_manage_buttons(self) -> None:
        message = self.renderer.render(
            _instruction("project_home", {"project_count": 3})
        )

        self.assertIn("blocks", message)
        self.assertEqual(message["blocks"][0]["type"], "header")
        self.assertIn("3", message["blocks"][1]["text"]["text"])

        buttons = _action_buttons(message)
        self.assertEqual(len(buttons), 2)
        intents = [json.loads(btn["value"])["intent_key"] for btn in buttons]
        self.assertEqual(intents, ["project.new", "project.manage"])

    def test_project_create_includes_name_and_backend_inputs(self) -> None:
        message = self.renderer.render(
            _instruction(
                "project_create",
                {
                    "default_backend": "claude_code",
                    "backend_options": [
                        {"label": "Codex", "value": "codex"},
                        {"label": "Claude Code", "value": "claude_code"},
                    ],
                },
            )
        )

        input_blocks = [b for b in message["blocks"] if b.get("type") == "input"]
        self.assertEqual(len(input_blocks), 2)
        self.assertEqual(input_blocks[0]["element"]["type"], "plain_text_input")
        self.assertEqual(input_blocks[1]["element"]["type"], "static_select")
        self.assertEqual(
            input_blocks[1]["element"]["initial_option"]["value"],
            "claude_code",
        )

        buttons = _action_buttons(message)
        action_ids = [btn["action_id"] for btn in buttons]
        self.assertIn("submit_project_create_button", action_ids)
        self.assertIn("cancel_project_create_button", action_ids)

    def test_project_manage_lists_projects_with_delete_buttons(self) -> None:
        message = self.renderer.render(
            _instruction(
                "project_manage",
                {
                    "projects": [
                        {
                            "id": "p1",
                            "name": "Alpha",
                            "backend": "codex",
                            "group_chat_id": "C100",
                            "archived": False,
                        },
                        {
                            "id": "p2",
                            "name": "Beta",
                            "backend": "claude_code",
                            "group_chat_id": None,
                            "archived": True,
                        },
                    ]
                },
            )
        )
        buttons = _action_buttons(message)
        delete_buttons = [b for b in buttons if b["action_id"].startswith("delete_project_")]
        self.assertEqual(len(delete_buttons), 2)
        delete_intents = [json.loads(btn["value"]) for btn in delete_buttons]
        self.assertEqual(
            {intent["project_id"] for intent in delete_intents},
            {"p1", "p2"},
        )
        self.assertTrue(all(intent["intent_key"] == "project.delete" for intent in delete_intents))
        back_buttons = [b for b in buttons if b["action_id"] == "back_to_project_home_button"]
        self.assertEqual(len(back_buttons), 1)

    def test_project_manage_without_projects_shows_empty_state(self) -> None:
        message = self.renderer.render(_instruction("project_manage", {"projects": []}))
        section_texts = [
            b["text"]["text"]
            for b in message["blocks"]
            if b.get("type") == "section"
        ]
        self.assertTrue(any("No projects" in text for text in section_texts))

    def test_project_list_key_dispatches_to_manage_renderer(self) -> None:
        message = self.renderer.render(_instruction("project_list", {"projects": []}))
        header_text = message["blocks"][0]["text"]["text"]
        self.assertEqual(header_text, "Manage Projects")

    def test_task_composer_renders_prompt_input_and_submit(self) -> None:
        message = self.renderer.render(
            _instruction(
                "task_composer",
                {
                    "project": {"id": "p1", "name": "Alpha", "backend": "codex"},
                    "current_agent": "codex",
                    "current_workdir": "/tmp/alpha",
                    "note": "Describe what you need.",
                },
            )
        )
        input_blocks = [b for b in message["blocks"] if b.get("type") == "input"]
        self.assertEqual(len(input_blocks), 1)
        element = input_blocks[0]["element"]
        self.assertEqual(element["type"], "plain_text_input")
        self.assertTrue(element["multiline"])

        buttons = _action_buttons(message)
        submit_btn = next(b for b in buttons if b["action_id"].startswith("submit_task_"))
        intent = json.loads(submit_btn["value"])
        self.assertEqual(intent["intent_key"], "task.submit")
        self.assertEqual(intent["project_id"], "p1")
        self.assertEqual(intent["surface"], "dm")

    def test_workspace_overview_stop_hidden_when_disabled(self) -> None:
        message = self.renderer.render(
            _instruction(
                "workspace_overview",
                {
                    "project": {"id": "p1", "name": "Alpha", "backend": "codex"},
                    "latest_task_status": "none",
                    "stop_enabled": False,
                    "queue_count": 0,
                },
            )
        )
        buttons = _action_buttons(message)
        action_ids = {btn["action_id"] for btn in buttons}
        self.assertNotIn("stop_workspace_task_p1", action_ids)
        self.assertIn("enter_workdir_path_p1", action_ids)
        self.assertIn("choose_workspace_agent_p1", action_ids)
        self.assertIn("choose_workspace_session_p1", action_ids)

    def test_workspace_overview_running_locks_config_and_exposes_stop(self) -> None:
        message = self.renderer.render(
            _instruction(
                "workspace_overview",
                {
                    "project": {"id": "p1", "name": "Alpha", "backend": "codex"},
                    "latest_task_status": "running",
                    "latest_task_id": "t42",
                    "stop_enabled": True,
                    "current_workdir": "/tmp/alpha",
                    "current_agent": "codex",
                    "queue_count": 2,
                },
            )
        )
        buttons = _action_buttons(message)
        action_ids = {btn["action_id"] for btn in buttons}
        self.assertIn("stop_workspace_task_p1", action_ids)
        # Configuration knobs should be locked out while a task is running.
        self.assertNotIn("enter_workdir_path_p1", action_ids)
        self.assertNotIn("choose_workspace_agent_p1", action_ids)

    def test_task_status_awaiting_confirmation_shows_approve_and_stop(self) -> None:
        message = self.renderer.render(
            _instruction(
                "task_status",
                {
                    "task": {
                        "id": "t1",
                        "project_id": "p1",
                        "status": "waiting_for_confirmation",
                        "agent_backend": "codex",
                        "effective_workdir": "/tmp/alpha",
                        "effective_model": "gpt-5",
                        "awaiting_confirmation_reason": "Run dangerous command?",
                    }
                },
            )
        )
        buttons = _action_buttons(message)
        action_ids = {btn["action_id"] for btn in buttons}
        self.assertIn("approve_task_t1", action_ids)
        self.assertIn("stop_task_t1", action_ids)

    def test_task_status_running_shows_live_output_and_stop(self) -> None:
        message = self.renderer.render(
            _instruction(
                "task_status",
                {
                    "task": {
                        "id": "t1",
                        "project_id": "p1",
                        "status": "running",
                        "agent_backend": "codex",
                        "live_output": "building the thing...",
                    }
                },
            )
        )
        sections = [b for b in message["blocks"] if b.get("type") == "section"]
        self.assertTrue(any("building the thing" in s["text"]["text"] for s in sections))
        buttons = _action_buttons(message)
        self.assertIn("stop_task_t1", {b["action_id"] for b in buttons})

    def test_task_status_queued_with_steerable_blocker_shows_steer_button(self) -> None:
        message = self.renderer.render(
            _instruction(
                "task_status",
                {
                    "task": {
                        "id": "t2",
                        "project_id": "p1",
                        "status": "queued",
                        "agent_backend": "codex",
                        "prompt": "run follow-up work",
                    },
                    "queue_position": 1,
                    "blocking_task_id": "t1",
                    "blocking_task_status": "running",
                },
            )
        )
        buttons = _action_buttons(message)
        steer_btn = next(
            (b for b in buttons if b["action_id"].startswith("steer_queued_task_")),
            None,
        )
        self.assertIsNotNone(steer_btn)
        assert steer_btn is not None
        self.assertEqual(json.loads(steer_btn["value"])["intent_key"], "task.steer_queue")

    def test_task_status_terminal_failure_offers_continue(self) -> None:
        message = self.renderer.render(
            _instruction(
                "task_status",
                {
                    "task": {
                        "id": "t1",
                        "project_id": "p1",
                        "status": "failed",
                        "agent_backend": "codex",
                        "backend_session_id": "sess-1",
                        "raw_result": "stacktrace goes here",
                    }
                },
            )
        )
        buttons = _action_buttons(message)
        action_ids = {btn["action_id"] for btn in buttons}
        self.assertIn("continue_task_t1", action_ids)
        self.assertNotIn("stop_task_t1", action_ids)

    def test_task_status_token_usage_renders_context(self) -> None:
        message = self.renderer.render(
            _instruction(
                "task_status",
                {
                    "task": {
                        "id": "t1",
                        "project_id": "p1",
                        "status": "succeeded",
                        "agent_backend": "codex",
                        "raw_result": "done",
                        "total_token_usage": {
                            "input_tokens": 100,
                            "output_tokens": 200,
                            "cached_input_tokens": 20,
                            "reasoning_output_tokens": 5,
                        },
                    }
                },
            )
        )
        context_blocks = [b for b in message["blocks"] if b.get("type") == "context"]
        self.assertTrue(
            any("in 100" in el["text"] for b in context_blocks for el in b["elements"])
        )

    def test_fallback_renders_unknown_template(self) -> None:
        message = self.renderer.render(_instruction("mystery_template", {"foo": "bar"}))
        self.assertEqual(message["blocks"][0]["type"], "header")
        self.assertEqual(
            message["blocks"][0]["text"]["text"],
            "mystery_template",
        )
        text_blob = json.dumps(message)
        self.assertIn("Unrendered template", text_blob)

    def test_button_values_are_truncated_to_block_kit_limit(self) -> None:
        giant_name = "x" * 5000
        message = self.renderer.render(
            _instruction(
                "task_composer",
                {
                    "project": {"id": giant_name, "name": "Alpha", "backend": "codex"},
                },
            )
        )
        for btn in _action_buttons(message):
            self.assertLessEqual(len(btn["value"]), 2000)

    def test_render_returns_message_with_text_fallback(self) -> None:
        message = self.renderer.render(_instruction("project_home", {"project_count": 0}))
        self.assertIn("text", message)
        self.assertIsInstance(message["text"], str)
        self.assertGreater(len(message["text"]), 0)
        self.assertEqual(_block_types(message)[0], "header")


if __name__ == "__main__":
    unittest.main()
