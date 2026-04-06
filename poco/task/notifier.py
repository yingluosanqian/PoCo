from __future__ import annotations

from typing import Protocol

from poco.platform.feishu.client import FeishuMessageClient
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
        debug_recorder: FeishuDebugRecorder | None = None,
    ) -> None:
        self._message_client = message_client
        self._debug_recorder = debug_recorder

    def notify_task(self, task: Task) -> None:
        if not task.reply_receive_id or not task.reply_receive_id_type:
            return

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
