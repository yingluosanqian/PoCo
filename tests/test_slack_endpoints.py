from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
import urllib.parse
from unittest.mock import patch

from fastapi.testclient import TestClient

from poco.main import create_app


_SIGNING_SECRET = "test-signing-secret"
_BOT_TOKEN = "xoxb-test-token"
_APP_TOKEN = "xapp-test-token"


def _slack_signature(raw_body: bytes, timestamp: str) -> str:
    basestring = f"v0:{timestamp}:".encode("utf-8") + raw_body
    digest = hmac.new(
        _SIGNING_SECRET.encode("utf-8"),
        basestring,
        hashlib.sha256,
    ).hexdigest()
    return f"v0={digest}"


def _slack_headers(raw_body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": _slack_signature(raw_body, timestamp),
    }


class _SlackEndpointBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "POCO_STATE_BACKEND": "sqlite",
                "POCO_STATE_DB_PATH": os.path.join(self.tempdir.name, "poco.db"),
                "POCO_SLACK_BOT_TOKEN": _BOT_TOKEN,
                "POCO_SLACK_APP_TOKEN": _APP_TOKEN,
                "POCO_SLACK_SIGNING_SECRET": _SIGNING_SECRET,
                "POCO_SLACK_DELIVERY_MODE": "webhook",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tempdir.cleanup)
        self.app = create_app()
        self.client = TestClient(self.app)


class SlackEventsEndpointTest(_SlackEndpointBase):
    def test_url_verification_returns_challenge(self) -> None:
        body = json.dumps({"type": "url_verification", "challenge": "shh"}).encode("utf-8")
        response = self.client.post(
            "/platform/slack/events",
            content=body,
            headers={**_slack_headers(body), "content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"challenge": "shh"})

    def test_missing_signature_rejected(self) -> None:
        body = json.dumps({"type": "url_verification", "challenge": "shh"}).encode("utf-8")
        response = self.client.post(
            "/platform/slack/events",
            content=body,
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 401)

    def test_invalid_signature_rejected(self) -> None:
        body = json.dumps({"type": "url_verification", "challenge": "shh"}).encode("utf-8")
        response = self.client.post(
            "/platform/slack/events",
            content=body,
            headers={
                "content-type": "application/json",
                "X-Slack-Request-Timestamp": str(int(time.time())),
                "X-Slack-Signature": "v0=deadbeef",
            },
        )
        self.assertEqual(response.status_code, 401)

    def test_invalid_json_rejected(self) -> None:
        body = b"not-json"
        response = self.client.post(
            "/platform/slack/events",
            content=body,
            headers={**_slack_headers(body), "content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 400)


class SlackCommandsEndpointTest(_SlackEndpointBase):
    def test_slash_command_returns_ephemeral_project_list(self) -> None:
        form = {
            "command": "/poco",
            "user_id": "U123",
            "text": "",
            "channel_id": "D123",
        }
        body = urllib.parse.urlencode(form).encode("utf-8")
        response = self.client.post(
            "/platform/slack/commands",
            content=body,
            headers={
                **_slack_headers(body),
                "content-type": "application/x-www-form-urlencoded",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response_type"], "ephemeral")
        self.assertIn("blocks", payload)


class SlackInteractiveEndpointTest(_SlackEndpointBase):
    def test_interactive_form_payload_decoded(self) -> None:
        inner = {
            "user": {"id": "U42"},
            "container": {"channel_id": "C1", "message_ts": "1.0"},
            "actions": [
                {
                    "action_id": "project_open",
                    "value": json.dumps({"intent_key": "project.home", "surface": "dm"}),
                }
            ],
        }
        form = {"payload": json.dumps(inner)}
        body = urllib.parse.urlencode(form).encode("utf-8")
        response = self.client.post(
            "/platform/slack/interactive",
            content=body,
            headers={
                **_slack_headers(body),
                "content-type": "application/x-www-form-urlencoded",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("status", payload)
        self.assertIn("channel", payload)


class SlackHealthTest(_SlackEndpointBase):
    def test_health_reports_slack_fields(self) -> None:
        payload = self.client.get("/health").json()
        self.assertTrue(payload["slack_enabled"])
        self.assertIn("slack_delivery_mode", payload)
        self.assertIn("slack_listener_ready", payload)
        self.assertIn("slack_listener_detail", payload)


class SlackDebugEndpointTest(_SlackEndpointBase):
    def test_slack_debug_snapshot_shape(self) -> None:
        payload = self.client.get("/debug/slack").json()
        self.assertIn("inbound_events", payload)
        self.assertIn("outbound_attempts", payload)
        self.assertIn("errors", payload)
        self.assertIn("listener", payload)
        self.assertIn("delivery_mode", payload["listener"])


class SlackEndpointsWhenDisabledTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "POCO_STATE_BACKEND": "sqlite",
                "POCO_STATE_DB_PATH": os.path.join(self.tempdir.name, "poco.db"),
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tempdir.cleanup)
        # Strip any Slack env the host machine may provide so the app boots
        # with Slack disabled.
        for key in (
            "POCO_SLACK_BOT_TOKEN",
            "POCO_SLACK_APP_TOKEN",
            "POCO_SLACK_SIGNING_SECRET",
        ):
            os.environ.pop(key, None)
        self.client = TestClient(create_app())

    def test_event_endpoint_returns_503(self) -> None:
        response = self.client.post(
            "/platform/slack/events",
            content=b"{}",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
