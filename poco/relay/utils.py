"""Low-level relay helpers and compatibility patches."""

from __future__ import annotations

import base64
import http
import time
from pathlib import Path
from typing import List

import lark_oapi.ws.client as lark_ws_client


IMAGE_CACHE_DIR = Path.home() / ".local" / "state" / "poco" / "images"


def patch_lark_ws_card_callbacks() -> None:
    """Makes the Lark WS client dispatch CARD frames to the event handler."""
    if getattr(lark_ws_client.Client, "_poco_card_patch_applied", False):
        return

    async def _patched_handle_data_frame(self, frame):
        hs = frame.headers
        msg_id = lark_ws_client._get_by_key(hs, lark_ws_client.HEADER_MESSAGE_ID)
        trace_id = lark_ws_client._get_by_key(hs, lark_ws_client.HEADER_TRACE_ID)
        sum_ = lark_ws_client._get_by_key(hs, lark_ws_client.HEADER_SUM)
        seq = lark_ws_client._get_by_key(hs, lark_ws_client.HEADER_SEQ)
        type_ = lark_ws_client._get_by_key(hs, lark_ws_client.HEADER_TYPE)

        pl = frame.payload
        if int(sum_) > 1:
            pl = self._combine(msg_id, int(sum_), int(seq), pl)
            if pl is None:
                return

        message_type = lark_ws_client.MessageType(type_)
        lark_ws_client.logger.debug(
            self._fmt_log(
                "receive message, message_type: {}, message_id: {}, trace_id: {}, payload: {}",
                message_type.value,
                msg_id,
                trace_id,
                pl.decode(lark_ws_client.UTF_8),
            )
        )

        resp = lark_ws_client.Response(code=http.HTTPStatus.OK)
        try:
            start = int(round(time.time() * 1000))
            if message_type in {lark_ws_client.MessageType.EVENT, lark_ws_client.MessageType.CARD}:
                result = self._event_handler.do_without_validation(pl)
            else:
                return
            end = int(round(time.time() * 1000))
            header = hs.add()
            header.key = lark_ws_client.HEADER_BIZ_RT
            header.value = str(end - start)
            if result is not None:
                resp.data = base64.b64encode(
                    lark_ws_client.JSON.marshal(result).encode(lark_ws_client.UTF_8)
                )
        except Exception as exc:
            lark_ws_client.logger.error(
                self._fmt_log(
                    "handle message failed, message_type: {}, message_id: {}, trace_id: {}, err: {}",
                    message_type.value,
                    msg_id,
                    trace_id,
                    exc,
                )
            )
            resp = lark_ws_client.Response(code=http.HTTPStatus.INTERNAL_SERVER_ERROR)

        frame.payload = lark_ws_client.JSON.marshal(resp).encode(lark_ws_client.UTF_8)
        await self._write_message(frame.SerializeToString())

    lark_ws_client.Client._handle_data_frame = _patched_handle_data_frame
    lark_ws_client.Client._poco_card_patch_applied = True


def chunk_text(text: str, limit: int) -> List[str]:
    """Splits text into chunks that fit Feishu text message limits."""
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for line in text.splitlines():
        line = line.rstrip()
        if len(line) > limit:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for start in range(0, len(line), limit):
                chunks.append(line[start:start + limit])
            continue
        extra = len(line) + (1 if current else 0)
        if current and current_len + extra > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
            continue
        current.append(line)
        current_len += extra
    if current:
        chunks.append("\n".join(current))
    if not chunks:
        chunks.append("")
    return chunks


def shorten(text: str, limit: int) -> str:
    """Produces a single-line shortened summary."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."
