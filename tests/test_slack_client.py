from __future__ import annotations

import io
import json
import unittest
from typing import Any
from unittest.mock import patch

from poco.platform.slack.client import SlackApiError, SlackMessageClient


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def _make_urlopen(responses: list[dict[str, Any]]):
    captured: list[dict[str, Any]] = []

    def fake_urlopen(request, timeout=None):  # noqa: ANN001 - urllib signature
        captured.append(
            {
                "url": request.full_url,
                "headers": dict(request.header_items()),
                "body": json.loads(request.data.decode("utf-8")) if request.data else None,
            }
        )
        payload = responses.pop(0)
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    return fake_urlopen, captured


class SlackMessageClientTest(unittest.TestCase):
    def test_send_interactive_posts_blocks_and_returns_ts_and_channel(self) -> None:
        fake_urlopen, captured = _make_urlopen(
            [{"ok": True, "ts": "1711111111.000100", "channel": "C123"}]
        )
        client = SlackMessageClient("xoxb-test")
        with patch("poco.platform.slack.client.urlopen", fake_urlopen):
            result = client.send_interactive(
                receive_id="C123",
                receive_id_type="channel",
                card={"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "hi"}}]},
            )

        self.assertEqual(result.message_id, "1711111111.000100")
        self.assertEqual(result.channel, "C123")
        self.assertEqual(len(captured), 1)
        self.assertTrue(captured[0]["url"].endswith("/chat.postMessage"))
        body = captured[0]["body"]
        self.assertEqual(body["channel"], "C123")
        self.assertIn("blocks", body)

    def test_update_interactive_requires_channel(self) -> None:
        client = SlackMessageClient("xoxb-test")
        with self.assertRaises(SlackApiError):
            client.update_interactive(
                message_id="1711111111.000100",
                card={"blocks": []},
            )

    def test_update_interactive_uses_chat_update(self) -> None:
        fake_urlopen, captured = _make_urlopen(
            [{"ok": True, "ts": "1711111111.000100", "channel": "C123"}]
        )
        client = SlackMessageClient("xoxb-test")
        with patch("poco.platform.slack.client.urlopen", fake_urlopen):
            result = client.update_interactive(
                message_id="1711111111.000100",
                card={"blocks": []},
                channel="C123",
            )

        self.assertEqual(result.message_id, "1711111111.000100")
        self.assertEqual(result.channel, "C123")
        self.assertTrue(captured[0]["url"].endswith("/chat.update"))
        body = captured[0]["body"]
        self.assertEqual(body["channel"], "C123")
        self.assertEqual(body["ts"], "1711111111.000100")

    def test_slack_error_response_raises(self) -> None:
        fake_urlopen, _ = _make_urlopen([{"ok": False, "error": "channel_not_found"}])
        client = SlackMessageClient("xoxb-test")
        with patch("poco.platform.slack.client.urlopen", fake_urlopen):
            with self.assertRaises(SlackApiError):
                client.send_text(
                    receive_id="C-missing",
                    receive_id_type="channel",
                    text="hello",
                )


if __name__ == "__main__":
    unittest.main()
