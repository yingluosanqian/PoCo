from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class MessageSendResult:
    """Platform-neutral outcome of sending or updating a message.

    ``channel`` is populated by platforms whose update operations require
    composite addressing (e.g. Slack's ``(channel, ts)`` pair). Feishu leaves
    it ``None``.
    """

    message_id: str | None
    channel: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


class MessageClient(Protocol):
    """Protocol for per-platform messaging clients used by platform-neutral
    components (e.g. the task notifier). Platform-specific chat management
    (creating/deleting groups, uploading files) is intentionally excluded so
    each platform can expose its own helpers outside of this contract.
    """

    def send_text(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        text: str,
    ) -> MessageSendResult: ...

    def send_interactive(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        card: dict[str, Any],
    ) -> MessageSendResult: ...

    def update_interactive(
        self,
        *,
        message_id: str,
        card: dict[str, Any],
        channel: str | None = None,
    ) -> MessageSendResult: ...
