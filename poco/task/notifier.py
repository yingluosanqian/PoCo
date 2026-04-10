from __future__ import annotations

from typing import Protocol

from poco.interaction.card_dispatcher import build_render_instruction
from poco.interaction.card_models import Surface
from poco.platform.feishu.client import FeishuMessageClient
from poco.platform.feishu.cards import FeishuCardRenderer
from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.task.models import Task
from poco.task.rendering import headline_for_notification, render_task_text


class TaskNotifier(Protocol):
    def notify_task(self, task: Task) -> None:
        ...


class NullTaskNotifier:
    def notify_task(self, task: Task) -> None:
        return None


class FeishuTaskNotifier:
    def __init__(
        self,
        message_client: FeishuMessageClient,
        *,
        renderer: FeishuCardRenderer | None = None,
        debug_recorder: FeishuDebugRecorder | None = None,
    ) -> None:
        self._message_client = message_client
        self._renderer = renderer or FeishuCardRenderer()
        self._debug_recorder = debug_recorder

    def notify_task(self, task: Task) -> None:
        if not task.reply_receive_id or not task.reply_receive_id_type:
            return

        is_card_target = task.reply_receive_id_type in {"chat_id", "open_id"}
        if is_card_target:
            from poco.interaction.card_handlers import build_task_status_result

            surface = (
                Surface.GROUP
                if task.reply_receive_id_type == "chat_id"
                else Surface.DM
            )
            instruction = build_render_instruction(
                build_task_status_result(task, message=headline_for_notification(task)),
                surface=surface,
            )
            card = self._renderer.render(instruction)
            preview = f"[card] task_status:{task.status.value}"
            if self._debug_recorder is not None:
                self._debug_recorder.record_outbound_attempt(
                    source="task_notifier",
                    receive_id=task.reply_receive_id,
                    receive_id_type=task.reply_receive_id_type,
                    text=preview,
                    task_id=task.id,
                )
            try:
                self._message_client.send_interactive(
                    receive_id=task.reply_receive_id,
                    receive_id_type=task.reply_receive_id_type,
                    card=card,
                )
                return
            except Exception as exc:
                if self._debug_recorder is not None:
                    self._debug_recorder.record_error(
                        stage="task_notifier",
                        message=str(exc),
                        context={
                            "task_id": task.id,
                            "receive_id": task.reply_receive_id,
                            "receive_id_type": task.reply_receive_id_type,
                            "mode": "interactive",
                        },
                    )
                raise

        text = render_task_text(task, headline=headline_for_notification(task))
        if self._debug_recorder is not None:
            self._debug_recorder.record_outbound_attempt(
                source="task_notifier",
                receive_id=task.reply_receive_id,
                receive_id_type=task.reply_receive_id_type,
                text=text,
                task_id=task.id,
            )
        try:
            self._message_client.send_text(
                receive_id=task.reply_receive_id,
                receive_id_type=task.reply_receive_id_type,
                text=text,
            )
        except Exception as exc:
            if self._debug_recorder is not None:
                self._debug_recorder.record_error(
                    stage="task_notifier",
                    message=str(exc),
                    context={
                        "task_id": task.id,
                        "receive_id": task.reply_receive_id,
                        "receive_id_type": task.reply_receive_id_type,
                    },
                )
            raise
