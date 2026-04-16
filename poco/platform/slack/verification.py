from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable, Mapping


class SlackVerificationError(ValueError):
    pass


class SlackRequestVerifier:
    """Validates the ``X-Slack-Signature`` header on inbound HTTP requests.

    Slack signs each request with the app's signing secret:
    ``v0=<hex(hmac_sha256(signing_secret, f"v0:{timestamp}:{body}"))>``.
    Requests older than ``max_clock_skew_seconds`` (5 minutes by default) are
    rejected to prevent replay.
    """

    SIGNATURE_VERSION = "v0"

    def __init__(
        self,
        *,
        signing_secret: str | None,
        max_clock_skew_seconds: int = 5 * 60,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._signing_secret = signing_secret
        self._max_clock_skew_seconds = max_clock_skew_seconds
        self._now = now

    def verify(
        self,
        *,
        headers: Mapping[str, str],
        raw_body: bytes,
    ) -> None:
        if not self._signing_secret:
            return

        timestamp = _get_header(headers, "X-Slack-Request-Timestamp")
        signature = _get_header(headers, "X-Slack-Signature")
        if not timestamp or not signature:
            raise SlackVerificationError(
                "Missing Slack signature headers while signing is enabled."
            )

        try:
            ts_value = int(timestamp)
        except ValueError as exc:
            raise SlackVerificationError("X-Slack-Request-Timestamp is not an integer.") from exc

        if abs(self._now() - ts_value) > self._max_clock_skew_seconds:
            raise SlackVerificationError("Slack request timestamp outside of allowed skew window.")

        basestring = f"{self.SIGNATURE_VERSION}:{timestamp}:".encode("utf-8") + raw_body
        digest = hmac.new(
            self._signing_secret.encode("utf-8"),
            basestring,
            hashlib.sha256,
        ).hexdigest()
        expected = f"{self.SIGNATURE_VERSION}={digest}"

        if not hmac.compare_digest(expected, signature):
            raise SlackVerificationError("Invalid Slack request signature.")


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None
