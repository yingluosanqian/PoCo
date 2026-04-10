from __future__ import annotations

import unittest

from poco.interaction.card_dispatcher import (
    CardActionDispatcher,
    UnknownActionIntentError,
    build_render_instruction,
)
from poco.interaction.card_models import (
    ActionIntent,
    DispatchStatus,
    IntentDispatchResult,
    RefreshMode,
    RenderTarget,
    ResourceRefs,
    Surface,
    ViewModel,
)


class CountingHandler:
    def __init__(self, result: IntentDispatchResult) -> None:
        self.calls = 0
        self.result = result

    def handle(self, intent: ActionIntent) -> IntentDispatchResult:
        self.calls += 1
        return self.result


class CardActionDispatcherTest(unittest.TestCase):
    def test_dispatch_routes_intent_to_handler(self) -> None:
        handler = CountingHandler(
            IntentDispatchResult(
                status=DispatchStatus.OK,
                intent_key="workspace.refresh",
                resource_refs=ResourceRefs(project_id="proj_1"),
                view_model=ViewModel("workspace_overview", {"project_id": "proj_1"}),
                refresh_mode=RefreshMode.REPLACE_CURRENT,
                message="Workspace refreshed.",
            )
        )
        dispatcher = CardActionDispatcher({"workspace.refresh": handler})
        intent = ActionIntent(
            intent_key="workspace.refresh",
            surface=Surface.GROUP,
            actor_id="ou_user",
            source_message_id="om_message",
            request_id="req_1",
            project_id="proj_1",
        )

        result = dispatcher.dispatch(intent)

        self.assertEqual(handler.calls, 1)
        self.assertEqual(result.intent_key, "workspace.refresh")
        self.assertEqual(result.resource_refs.project_id, "proj_1")

    def test_duplicate_write_intent_returns_cached_result(self) -> None:
        handler = CountingHandler(
            IntentDispatchResult(
                status=DispatchStatus.OK,
                intent_key="task.approve",
                resource_refs=ResourceRefs(project_id="proj_1", task_id="task_1"),
                view_model=ViewModel("approval", {"task_id": "task_1"}),
                refresh_mode=RefreshMode.APPEND_NEW,
                message="Task approved.",
            )
        )
        dispatcher = CardActionDispatcher({"task.approve": handler})
        intent = ActionIntent(
            intent_key="task.approve",
            surface=Surface.GROUP,
            actor_id="ou_user",
            source_message_id="om_message",
            request_id="req_approve_1",
            project_id="proj_1",
            task_id="task_1",
        )

        first = dispatcher.dispatch(intent)
        second = dispatcher.dispatch(intent)

        self.assertEqual(handler.calls, 1)
        self.assertEqual(first, second)

    def test_duplicate_read_intent_is_not_cached(self) -> None:
        handler = CountingHandler(
            IntentDispatchResult(
                status=DispatchStatus.OK,
                intent_key="workspace.refresh",
                resource_refs=ResourceRefs(project_id="proj_1"),
                view_model=ViewModel("workspace_overview", {"project_id": "proj_1"}),
                refresh_mode=RefreshMode.REPLACE_CURRENT,
                message="Workspace refreshed.",
            )
        )
        dispatcher = CardActionDispatcher({"workspace.refresh": handler})
        intent = ActionIntent(
            intent_key="workspace.refresh",
            surface=Surface.GROUP,
            actor_id="ou_user",
            source_message_id="om_message",
            request_id="req_refresh_1",
            project_id="proj_1",
        )

        dispatcher.dispatch(intent)
        dispatcher.dispatch(intent)

        self.assertEqual(handler.calls, 2)

    def test_unknown_intent_raises(self) -> None:
        dispatcher = CardActionDispatcher({})
        intent = ActionIntent(
            intent_key="project.open",
            surface=Surface.DM,
            actor_id="ou_user",
            source_message_id="om_message",
            request_id="req_open_1",
        )

        with self.assertRaises(UnknownActionIntentError):
            dispatcher.dispatch(intent)

    def test_build_render_instruction_maps_refresh_mode(self) -> None:
        result = IntentDispatchResult(
            status=DispatchStatus.OK,
            intent_key="project.open",
            resource_refs=ResourceRefs(project_id="proj_1"),
            view_model=ViewModel("project_config", {"project_id": "proj_1"}),
            refresh_mode=RefreshMode.REPLACE_CURRENT,
            message="Project opened.",
        )

        instruction = build_render_instruction(result, surface=Surface.DM)

        self.assertEqual(instruction.surface, Surface.DM)
        self.assertEqual(instruction.render_target, RenderTarget.CURRENT_CARD)
        self.assertEqual(instruction.template_key, "project_config")
        self.assertEqual(instruction.template_data["project_id"], "proj_1")

    def test_build_render_instruction_supports_ack_only(self) -> None:
        result = IntentDispatchResult(
            status=DispatchStatus.REJECTED,
            intent_key="task.approve",
            resource_refs=ResourceRefs(task_id="task_1"),
            view_model=None,
            refresh_mode=RefreshMode.ACK_ONLY,
            message="Task is already completed.",
        )

        instruction = build_render_instruction(result, surface=Surface.GROUP)

        self.assertEqual(instruction.render_target, RenderTarget.ACK)
        self.assertIsNone(instruction.template_key)
        self.assertEqual(instruction.message, "Task is already completed.")


if __name__ == "__main__":
    unittest.main()
