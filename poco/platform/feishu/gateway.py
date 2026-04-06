from __future__ import annotations

import json
from typing import Any

from poco.interaction.service import InteractionService


class FeishuGateway:
    def __init__(self, interaction_service: InteractionService) -> None:
        self._interaction_service = interaction_service

    def handle_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "challenge" in payload:
            return {"challenge": payload["challenge"]}

        event = payload.get("event", payload)
        user_id = self._extract_user_id(event)
        text = self._extract_text(event)

        response = self._interaction_service.handle_text(
            user_id=user_id,
            text=text,
            source="feishu",
        )
        return {
            "ok": True,
            "reply": {
                "message_type": "text",
                "content": response.text,
            },
            "task_id": response.task_id,
        }

    def _extract_user_id(self, event: dict[str, Any]) -> str:
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {})
        return (
            sender_id.get("open_id")
            or sender_id.get("user_id")
            or sender.get("open_id")
            or "anonymous"
        )

    def _extract_text(self, event: dict[str, Any]) -> str:
        message = event.get("message", {})
        content = message.get("content")

        if isinstance(content, str):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                return content
            if isinstance(parsed, dict):
                return str(parsed.get("text", "")).strip()
            return ""

        if isinstance(content, dict):
            return str(content.get("text", "")).strip()

        return str(event.get("text", "")).strip()
