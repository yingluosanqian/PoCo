from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from poco.platform.common.message_client import MessageSendResult


class FeishuApiError(RuntimeError):
    pass


class FeishuChatNotFoundError(FeishuApiError):
    pass


class FeishuChatDeleteForbiddenError(FeishuApiError):
    pass


@dataclass(frozen=True, slots=True)
class FeishuChatCreateResult:
    chat_id: str
    name: str | None
    raw_response: dict[str, Any]


class FeishuAccessTokenProvider:
    def __init__(self, base_url: str, app_id: str, app_secret: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._app_id = app_id
        self._app_secret = app_secret
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token

        payload = {
            "app_id": self._app_id,
            "app_secret": self._app_secret,
        }
        response = _request_json(
            method="POST",
            url=f"{self._base_url}/open-apis/auth/v3/tenant_access_token/internal",
            payload=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        token = response.get("tenant_access_token")
        expire = response.get("expire")
        code = response.get("code", 0)

        if code != 0 or not token or not isinstance(expire, int):
            raise FeishuApiError(
                f"Failed to obtain tenant_access_token: code={code} msg={response.get('msg', 'unknown error')}"
            )

        self._token = token
        self._expires_at = time.time() + max(expire - 300, 60)
        return token


class FeishuMessageClient:
    def __init__(self, base_url: str, token_provider: FeishuAccessTokenProvider) -> None:
        self._base_url = base_url.rstrip("/")
        self._token_provider = token_provider

    def send_text(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        text: str,
    ) -> MessageSendResult:
        return self._send_message(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            msg_type="text",
            content={"text": text},
        )

    def send_interactive(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        card: dict[str, Any],
    ) -> MessageSendResult:
        return self._send_message(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            msg_type="interactive",
            content=card,
        )

    def update_interactive(
        self,
        *,
        message_id: str,
        card: dict[str, Any],
        channel: str | None = None,
    ) -> MessageSendResult:
        # ``channel`` is accepted for MessageClient compatibility (Slack needs
        # composite addressing) and is ignored by Feishu.
        del channel
        token = self._token_provider.get_token()
        response = _request_json(
            method="PATCH",
            url=f"{self._base_url}/open-apis/im/v1/messages/{message_id}",
            payload={
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )

        code = response.get("code", 0)
        if code != 0:
            raise FeishuApiError(
                f"Failed to update Feishu message: code={code} msg={response.get('msg', 'unknown error')}"
            )

        data = response.get("data", {})
        return MessageSendResult(
            message_id=data.get("message_id") or message_id,
            raw_response=response,
        )

    def create_group_chat(
        self,
        *,
        name: str,
        owner_open_id: str,
    ) -> FeishuChatCreateResult:
        token = self._token_provider.get_token()
        query = urlencode(
            {
                "user_id_type": "open_id",
                "set_bot_manager": "true",
                "uuid": uuid4().hex,
            }
        )
        response = _request_json(
            method="POST",
            url=f"{self._base_url}/open-apis/im/v1/chats?{query}",
            payload={
                "name": name,
                "owner_id": owner_open_id,
                "chat_mode": "group",
                "chat_type": "private",
                "group_message_type": "chat",
                "membership_approval": "no_approval_required",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )

        code = response.get("code", 0)
        if code != 0:
            raise FeishuApiError(
                f"Failed to create Feishu group chat: code={code} msg={response.get('msg', 'unknown error')}"
            )

        data = response.get("data", {})
        chat_id = data.get("chat_id")
        if not isinstance(chat_id, str) or not chat_id.strip():
            raise FeishuApiError("Feishu group create response did not include a chat_id.")
        return FeishuChatCreateResult(
            chat_id=chat_id,
            name=data.get("name"),
            raw_response=response,
        )

    def delete_group_chat(self, *, chat_id: str) -> None:
        token = self._token_provider.get_token()
        response = _request_json(
            method="DELETE",
            url=f"{self._base_url}/open-apis/im/v1/chats/{chat_id}",
            payload={},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )

        code = response.get("code", 0)
        if code == 232006:
            raise FeishuChatNotFoundError(
                f"Feishu group chat not found: chat_id={chat_id}"
            )
        if code == 232017:
            raise FeishuChatDeleteForbiddenError(
                "Feishu rejected group deletion. The app likely does not have permission to dismiss this group."
            )
        if code != 0:
            raise FeishuApiError(
                f"Failed to delete Feishu group chat: code={code} msg={response.get('msg', 'unknown error')}"
            )

    def _send_message(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        msg_type: str,
        content: dict[str, Any],
    ) -> MessageSendResult:
        token = self._token_provider.get_token()
        query = urlencode({"receive_id_type": receive_id_type})
        response = _request_json(
            method="POST",
            url=f"{self._base_url}/open-apis/im/v1/messages?{query}",
            payload={
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": json.dumps(content, ensure_ascii=False),
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )

        code = response.get("code", 0)
        if code != 0:
            raise FeishuApiError(
                f"Failed to send Feishu message: code={code} msg={response.get('msg', 'unknown error')}"
            )

        data = response.get("data", {})
        return MessageSendResult(
            message_id=data.get("message_id"),
            raw_response=response,
        )


def _request_json(
    *,
    method: str,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url=url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FeishuApiError(
            f"Feishu API request failed with HTTP {exc.code}: {detail}"
        ) from exc
    except URLError as exc:
        raise FeishuApiError(f"Feishu API request failed: {exc.reason}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FeishuApiError("Feishu API returned non-JSON response.") from exc

    if not isinstance(parsed, dict):
        raise FeishuApiError("Feishu API returned an unexpected response shape.")
    return parsed
