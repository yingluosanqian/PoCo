from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class FeishuApiError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FeishuSendResult:
    message_id: str | None
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
        response = _post_json(
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
    ) -> FeishuSendResult:
        token = self._token_provider.get_token()
        query = urlencode({"receive_id_type": receive_id_type})
        response = _post_json(
            url=f"{self._base_url}/open-apis/im/v1/messages?{query}",
            payload={
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
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
        return FeishuSendResult(
            message_id=data.get("message_id"),
            raw_response=response,
        )


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url=url,
        data=body,
        headers=headers,
        method="POST",
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
