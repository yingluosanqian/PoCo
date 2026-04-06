from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from poco.interaction.service import InteractionService
from poco.platform.feishu.client import FeishuMessageClient
from poco.platform.feishu.verification import FeishuRequestVerifier
from poco.task.dispatcher import AsyncTaskDispatcher


class FeishuGateway:
    def __init__(
        self,
        interaction_service: InteractionService,
        *,
        request_verifier: FeishuRequestVerifier | None = None,
        message_client: FeishuMessageClient | None = None,
        dispatcher: AsyncTaskDispatcher | None = None,
    ) -> None:
        self._interaction_service = interaction_service
        self._request_verifier = request_verifier
        self._message_client = message_client
        self._dispatcher = dispatcher

    def handle_event(
        self,
        payload: dict[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
        raw_body: bytes | None = None,
    ) -> dict[str, Any]:
        request_headers = headers or {}
        request_body = raw_body or json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if self._request_verifier is not None:
            self._request_verifier.verify(
                payload=payload,
                headers=request_headers,
                raw_body=request_body,
            )

        if "challenge" in payload:
            return {"challenge": payload["challenge"]}

        event = payload.get("event", payload)
        if not event.get("message"):
            return {"ok": True, "ignored": True}

        user_id = self._extract_user_id(event)
        text = self._extract_text(event)
        target = self._resolve_reply_target(event, fallback_user_id=user_id)

        response = self._interaction_service.handle_text(
            user_id=user_id,
            text=text,
            source="feishu",
            reply_receive_id=target["receive_id"],
            reply_receive_id_type=target["receive_id_type"],
        )

        delivered = False
        if self._message_client is not None:
            self._message_client.send_text(
                receive_id=target["receive_id"],
                receive_id_type=target["receive_id_type"],
                text=response.text,
            )
            delivered = True

        if self._dispatcher is not None and response.task_id:
            if response.dispatch_action == "start":
                self._dispatcher.dispatch_start(response.task_id)
            elif response.dispatch_action == "resume":
                self._dispatcher.dispatch_resume(response.task_id)

        return {
            "ok": True,
            "delivered": delivered,
            "reply_preview": response.text,
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

    def _resolve_reply_target(
        self,
        event: dict[str, Any],
        *,
        fallback_user_id: str,
    ) -> dict[str, str]:
        message = event.get("message", {})
        chat_id = message.get("chat_id")
        if chat_id:
            return {
                "receive_id": str(chat_id),
                "receive_id_type": "chat_id",
            }

        return {
            "receive_id": fallback_user_id,
            "receive_id_type": "open_id",
        }
