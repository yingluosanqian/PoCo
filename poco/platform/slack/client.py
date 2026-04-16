from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from poco.platform.common.message_client import MessageSendResult


class SlackApiError(RuntimeError):
    pass


class SlackMessageClient:
    """Skeleton implementation of the :class:`MessageClient` protocol for Slack.

    Uses the Slack Web API (``chat.postMessage`` / ``chat.update``) via
    ``urllib`` so we stay aligned with the Feishu client and avoid a hard
    dependency on ``slack_sdk``. More capable Slack-specific helpers
    (conversation opening, file uploads, DM routing) will be layered on top
    in later PRs.
    """

    DEFAULT_BASE_URL = "https://slack.com/api"

    def __init__(self, bot_token: str, *, base_url: str = DEFAULT_BASE_URL) -> None:
        self._bot_token = bot_token
        self._base_url = base_url.rstrip("/")

    def send_text(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        text: str,
    ) -> MessageSendResult:
        del receive_id_type  # Slack does not distinguish channel/user for posting.
        return self._post_message(
            channel=receive_id,
            payload={"text": text},
        )

    def send_interactive(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        card: dict[str, Any],
    ) -> MessageSendResult:
        del receive_id_type
        payload = _block_kit_payload(card)
        return self._post_message(channel=receive_id, payload=payload)

    def update_interactive(
        self,
        *,
        message_id: str,
        card: dict[str, Any],
        channel: str | None = None,
    ) -> MessageSendResult:
        if not channel:
            raise SlackApiError(
                "Slack chat.update requires the channel id alongside the message ts."
            )
        payload = {
            "channel": channel,
            "ts": message_id,
            **_block_kit_payload(card),
        }
        response = self._call("chat.update", payload)
        return MessageSendResult(
            message_id=response.get("ts") or message_id,
            channel=response.get("channel") or channel,
            raw_response=response,
        )

    def _post_message(
        self,
        *,
        channel: str,
        payload: dict[str, Any],
    ) -> MessageSendResult:
        body = {"channel": channel, **payload}
        response = self._call("chat.postMessage", body)
        return MessageSendResult(
            message_id=response.get("ts"),
            channel=response.get("channel") or channel,
            raw_response=response,
        )

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}/{method}"
        response = _request_json(
            method="POST",
            url=url,
            payload=payload,
            headers={
                "Authorization": f"Bearer {self._bot_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        if not response.get("ok", False):
            raise SlackApiError(
                f"Slack API call {method} failed: {response.get('error', 'unknown error')}"
            )
        return response


def _block_kit_payload(card: dict[str, Any]) -> dict[str, Any]:
    """Coerce a rendered card payload into ``chat.postMessage`` kwargs.

    A Block Kit renderer (P2-2) emits ``{"blocks": [...], "text": "..."}``.
    For now accept either pre-shaped payloads or raw block arrays keyed under
    ``blocks`` so early callers can experiment.
    """

    if "blocks" in card:
        payload: dict[str, Any] = {"blocks": card["blocks"]}
        if "text" in card:
            payload["text"] = card["text"]
        return payload
    return dict(card)


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
        raise SlackApiError(
            f"Slack API request failed with HTTP {exc.code}: {detail}"
        ) from exc
    except URLError as exc:
        raise SlackApiError(f"Slack API request failed: {exc.reason}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SlackApiError("Slack API returned non-JSON response.") from exc

    if not isinstance(parsed, dict):
        raise SlackApiError("Slack API returned an unexpected response shape.")
    return parsed
