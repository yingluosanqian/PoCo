from __future__ import annotations

from typing import Protocol

from poco.platform.feishu.client import FeishuMessageClient
from poco.task.models import Task
from poco.task.rendering import headline_for_notification, render_task_text


class TaskNotifier(Protocol):
    def notify_task(self, task: Task) -> None:
        ...


class NullTaskNotifier:
    def notify_task(self, task: Task) -> None:
        return None


class FeishuTaskNotifier:
    def __init__(self, message_client: FeishuMessageClient) -> None:
        self._message_client = message_client

    def notify_task(self, task: Task) -> None:
        if not task.reply_receive_id or not task.reply_receive_id_type:
            return

        self._message_client.send_text(
            receive_id=task.reply_receive_id,
            receive_id_type=task.reply_receive_id_type,
            text=render_task_text(task, headline=headline_for_notification(task)),
        )
