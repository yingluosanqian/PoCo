from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from typing import Any


class FeishuVerificationError(ValueError):
    pass


class FeishuRequestVerifier:
    def __init__(
        self,
        *,
        verification_token: str | None = None,
        encrypt_key: str | None = None,
    ) -> None:
        self._verification_token = verification_token
        self._encrypt_key = encrypt_key

    def verify(
        self,
        *,
        payload: dict[str, Any],
        headers: Mapping[str, str],
        raw_body: bytes,
    ) -> None:
        self._verify_token(payload)
        self._verify_signature(headers=headers, raw_body=raw_body)
        self._reject_encrypted_payload(payload)

    def _verify_token(self, payload: dict[str, Any]) -> None:
        if not self._verification_token:
            return

        token = payload.get("token")
        if token is None:
            return
        if token != self._verification_token:
            raise FeishuVerificationError("Invalid Feishu verification token.")

    def _verify_signature(
        self,
        *,
        headers: Mapping[str, str],
        raw_body: bytes,
    ) -> None:
        if not self._encrypt_key:
            return

        timestamp = _get_header(headers, "X-Lark-Request-Timestamp")
        nonce = _get_header(headers, "X-Lark-Request-Nonce")
        signature = _get_header(headers, "X-Lark-Signature")
        if not timestamp or not nonce or not signature:
            raise FeishuVerificationError(
                "Missing Feishu signature headers while encrypt key validation is enabled."
            )

        expected = hashlib.sha256(
            f"{timestamp}{nonce}{self._encrypt_key}{raw_body.decode('utf-8')}".encode(
                "utf-8"
            )
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            raise FeishuVerificationError("Invalid Feishu request signature.")

    def _reject_encrypted_payload(self, payload: dict[str, Any]) -> None:
        if "encrypt" in payload:
            raise FeishuVerificationError(
                "Encrypted Feishu event payloads are not supported yet. Disable event encryption for the current MVP."
            )


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None
