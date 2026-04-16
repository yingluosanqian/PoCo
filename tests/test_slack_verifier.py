from __future__ import annotations

import hashlib
import hmac
import unittest

from poco.platform.slack.verification import SlackRequestVerifier, SlackVerificationError


SIGNING_SECRET = "slack_signing_secret_value"


def _sign(timestamp: str, body: bytes, *, secret: str = SIGNING_SECRET) -> str:
    basestring = f"v0:{timestamp}:".encode("utf-8") + body
    digest = hmac.new(secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    return f"v0={digest}"


class SlackRequestVerifierTest(unittest.TestCase):
    def test_valid_signature_passes(self) -> None:
        body = b'{"type":"event_callback"}'
        timestamp = "1_700_000_000".replace("_", "")
        signature = _sign(timestamp, body)
        verifier = SlackRequestVerifier(
            signing_secret=SIGNING_SECRET,
            now=lambda: int(timestamp),
        )

        verifier.verify(
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
            raw_body=body,
        )

    def test_tampered_body_is_rejected(self) -> None:
        body = b'{"type":"event_callback"}'
        timestamp = "1700000000"
        signature = _sign(timestamp, body)
        verifier = SlackRequestVerifier(
            signing_secret=SIGNING_SECRET,
            now=lambda: int(timestamp),
        )

        with self.assertRaises(SlackVerificationError):
            verifier.verify(
                headers={
                    "X-Slack-Request-Timestamp": timestamp,
                    "X-Slack-Signature": signature,
                },
                raw_body=b'{"type":"tampered"}',
            )

    def test_old_timestamp_is_rejected(self) -> None:
        body = b"{}"
        timestamp = "1700000000"
        verifier = SlackRequestVerifier(
            signing_secret=SIGNING_SECRET,
            now=lambda: int(timestamp) + 10_000,
        )

        with self.assertRaises(SlackVerificationError):
            verifier.verify(
                headers={
                    "X-Slack-Request-Timestamp": timestamp,
                    "X-Slack-Signature": _sign(timestamp, body),
                },
                raw_body=body,
            )

    def test_missing_headers_are_rejected(self) -> None:
        verifier = SlackRequestVerifier(signing_secret=SIGNING_SECRET)

        with self.assertRaises(SlackVerificationError):
            verifier.verify(headers={}, raw_body=b"{}")

    def test_disabled_verifier_skips_all_checks(self) -> None:
        verifier = SlackRequestVerifier(signing_secret=None)

        verifier.verify(headers={}, raw_body=b"anything")


if __name__ == "__main__":
    unittest.main()
