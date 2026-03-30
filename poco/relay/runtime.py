"""Turn execution and rendering lifecycle for the Feishu relay."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Optional, Tuple

from .models import LiveMessage, QueuedMessage, TurnSession
from .utils import chunk_text, shorten


LOG = logging.getLogger("poco.relay")


class TurnController:
    """Owns provider turn lifecycle, notifications, and live rendering."""

    def __init__(self, app) -> None:
        self.app = app

    def notification_loop(self, worker_id: str, client) -> None:
        """Consume provider notifications for a single worker."""
        notifications = client.notifications()
        while True:
            message = notifications.get()
            if message.get("method") == "__closed__":
                return
            try:
                self.handle_notification(worker_id, message)
            except Exception:
                LOG.exception("Failed to handle app-server notification for worker %s", worker_id)

    def handle_notification(self, worker_id: str, message: dict) -> None:
        """Route one provider notification to the matching handler."""
        method = message.get("method")
        params = message.get("params", {})
        if method == "item/agentMessage/delta":
            self.on_agent_delta(worker_id, params)
            return
        if method == "item/completed":
            self.on_item_completed(worker_id, params)
            return
        if method == "turn/completed":
            self.on_turn_completed(worker_id, params)
            return
        if method == "error":
            LOG.error("app-server notification error: %s", params)
            return
        LOG.debug("Ignored app-server notification: %s", method)

    def lookup_session(self, worker_id: str, thread_id: str, turn_id: str) -> Optional[TurnSession]:
        """Look up one active turn session by worker/thread/turn triple."""
        with self.app._lock:
            return self.app._active_by_turn.get((worker_id, thread_id, turn_id))

    def on_agent_delta(self, worker_id: str, params: dict) -> None:
        """Append one streaming delta chunk to the active turn session."""
        thread_id = params.get("threadId")
        turn_id = params.get("turnId")
        delta = str(params.get("delta", ""))
        if not thread_id or not turn_id or not delta:
            return
        session = self.lookup_session(worker_id, thread_id, turn_id)
        if session is None:
            return
        with session.lock:
            session.accumulated_text += delta
        session.notify()

    def on_item_completed(self, worker_id: str, params: dict) -> None:
        """Capture final text when the provider completes one agent message item."""
        thread_id = params.get("threadId")
        turn_id = params.get("turnId")
        item = params.get("item", {})
        if not thread_id or not turn_id or not isinstance(item, dict):
            return
        if item.get("type") != "agentMessage":
            return
        session = self.lookup_session(worker_id, thread_id, turn_id)
        if session is None:
            return
        final_text = str(item.get("text", "")).strip()
        if not final_text:
            return
        with session.lock:
            session.accumulated_text = final_text
            session.final_text = final_text
        session.notify()

    def on_turn_completed(self, worker_id: str, params: dict) -> None:
        """Mark the active turn as complete and wake the renderer."""
        thread_id = params.get("threadId")
        turn = params.get("turn", {})
        if not thread_id or not isinstance(turn, dict):
            return
        turn_id = turn.get("id")
        if not turn_id:
            return
        session = self.lookup_session(worker_id, thread_id, turn_id)
        if session is None:
            return
        status = str(turn.get("status", "completed"))
        with session.lock:
            session.done = True
            if status != "completed" and not session.error_text:
                session.error_text = f"[poco] 当前回复已结束，状态：{status}"
        session.notify()

    def render_loop(self, session: TurnSession) -> None:
        """Render a live turn into streaming cards or fallback messages."""
        max_delay = max(
            max(1, self.app._config.live_update_initial_seconds),
            self.app._config.live_update_max_seconds,
        )
        while True:
            session.updated_event.wait(timeout=0.5)
            session.updated_event.clear()
            now = time.time()

            with session.lock:
                done = session.done
                accumulated = session.accumulated_text
                final_text = session.final_text
                error_text = session.error_text
                next_update_at = session.next_update_at
                next_delay = session.next_delay
                elapsed = int(now - session.started_at)

            if done:
                if error_text and not accumulated:
                    self.render_text(session, error_text, final=True)
                elif final_text or accumulated:
                    self.render_text(session, final_text or accumulated, final=True)
                else:
                    self.render_text(session, "[poco] 回复已完成，但没有可显示的文本。", final=True)
                self.cleanup_session(session)
                return

            if accumulated and now >= next_update_at:
                self.render_text(session, accumulated, final=False)
                with session.lock:
                    session.next_delay = min(next_delay * 2, max_delay)
                    session.next_update_at = now + session.next_delay
                continue

            if not accumulated and now >= next_update_at:
                status_text = (
                    f"[poco] {self.app._provider_name_for_worker(session.worker_id)} 正在处理...\n"
                    f"已等待 {elapsed}s"
                )
                self.render_text(session, status_text, final=False)
                with session.lock:
                    session.next_delay = min(next_delay * 2, max_delay)
                    session.next_update_at = now + session.next_delay

    def render_text(self, session: TurnSession, text: str, final: bool) -> None:
        """Render one text snapshot into the session live surface."""
        live = session.live
        if live.card_id:
            if live.card_broken:
                return
            rendered = text.rstrip() or ("Done." if final else "")
            live = self.update_live_message(session.chat_id, live, rendered)
            session.live = live
            if final and live.streaming_mode:
                try:
                    self.app._messenger.set_card_streaming_mode(
                        live.card_id,
                        enabled=False,
                        sequence=live.stream_sequence + 1,
                        summary=shorten(rendered, 80),
                    )
                    live.stream_sequence += 1
                    live.streaming_mode = False
                    self.app._messenger.update_card_entity(
                        live.card_id,
                        self.answer_card(
                            self.app._provider_name_for_worker(session.worker_id),
                            rendered,
                            state="completed",
                            stop_enabled=False,
                            streaming=False,
                            element_id=live.element_id or "answer_stream",
                        ),
                        live.stream_sequence + 1,
                    )
                    live.stream_sequence += 1
                except Exception:
                    LOG.exception("Failed to close streaming mode for card_id=%s", live.card_id)
            return
        rendered = self.with_turn_state(text, completed=final)
        chunks = chunk_text(rendered, self.app._config.message_limit)
        if not chunks:
            chunks = [""]
        live = self.update_live_message(session.chat_id, live, chunks[0])
        session.live = live
        if final:
            for chunk in chunks[1:]:
                self.app._messenger.send_text(session.chat_id, chunk)

    def update_live_message(self, chat_id: str, live: LiveMessage, text: str) -> LiveMessage:
        """Push one updated text snapshot into the active live surface."""
        if text == live.last_text:
            return live
        if live.card_id and live.element_id:
            try:
                self.app._messenger.stream_card_text(
                    live.card_id,
                    live.element_id,
                    text,
                    live.stream_sequence + 1,
                )
                live.stream_sequence += 1
                live.last_text = text
                return live
            except Exception:
                LOG.exception("Streaming card update failed")
                if not live.card_broken:
                    self.app._safe_send_card(
                        chat_id,
                        self.app._status_card(
                            "PoCo Streaming Error",
                            "**PoCo** failed to update the streaming answer card. Please check local logs.",
                            template="red",
                        ),
                    )
                live.card_broken = True
                live.last_text = text
                return live
        if live.edit_count >= self.app._config.max_message_edits:
            new_sent = self.app._messenger.create_text(chat_id, text)
            return LiveMessage(sent=new_sent, edit_count=0, last_text=text)
        try:
            self.app._messenger.update_text(live.sent.message_id, text)
            live.edit_count += 1
            live.last_text = text
            return live
        except Exception:
            LOG.exception("Message update failed, falling back to create a new message")
            new_sent = self.app._messenger.create_text(chat_id, text)
            return LiveMessage(sent=new_sent, edit_count=0, last_text=text)

    @staticmethod
    def with_turn_state(text: str, *, completed: bool) -> str:
        """Append a short turn-state footer to a text reply."""
        status_line = (
            "[poco] state: completed, you can send the next message now."
            if completed
            else "[poco] state: running, please wait before sending the next message."
        )
        base = text.rstrip()
        if not base:
            return status_line
        return f"{base}\n\n{status_line}"

    def start_turn_for_worker(
        self,
        worker_id: str,
        chat_id: str,
        chat_type: str,
        text: str,
        local_image_paths: Optional[list[str]] = None,
    ) -> None:
        """Start one new provider turn for the specified worker."""
        worker = self.app._ensure_worker(worker_id, chat_id, chat_type)
        thread_id = worker.client.ensure_thread(self.app._store.get(worker_id))
        self.app._store.set(worker_id, thread_id)
        try:
            live = self.create_initial_live_message(chat_id, worker.provider_name)
        except Exception:
            LOG.exception("Failed to initialize streaming answer card")
            self.app._safe_send_card(
                chat_id,
                self.app._status_card(
                    "PoCo Streaming Error",
                    "**PoCo** could not create the streaming answer card. Please check local logs and cardkit permissions.",
                    template="red",
                ),
            )
            return
        image_paths = list(local_image_paths or [])
        turn_id = worker.client.start_turn(thread_id, text, image_paths)
        session = TurnSession(
            worker_id=worker_id,
            chat_id=chat_id,
            thread_id=thread_id,
            turn_id=turn_id,
            prompt=text,
            live=live,
            image_paths=image_paths,
            next_delay=max(1, self.app._config.live_update_initial_seconds),
            next_update_at=time.time() + max(1, self.app._config.live_update_initial_seconds),
        )
        with self.app._lock:
            self.app._active_by_worker[worker_id] = session
            self.app._active_by_turn[(worker_id, thread_id, turn_id)] = session
        threading.Thread(target=self.render_loop, args=(session,), daemon=True).start()

    def create_initial_live_message(self, chat_id: str, provider_name: str) -> LiveMessage:
        """Create and send the initial streaming answer card message."""
        initial_text = f"PoCo is thinking with {provider_name}..."
        card_id, element_id = self.create_streaming_answer_card(provider_name)
        sent = self.app._messenger.create_card_entity_message(chat_id, card_id)
        return LiveMessage(
            sent=sent,
            last_text=initial_text,
            card_id=card_id,
            element_id=element_id,
            stream_uuid=str(uuid.uuid4()),
            stream_sequence=0,
            streaming_mode=True,
        )

    def answer_card(
        self,
        provider_name: str,
        text: str,
        *,
        state: str,
        stop_enabled: bool,
        streaming: bool,
        element_id: str = "answer_stream",
    ) -> dict:
        """Build one reply card for streaming, completed, or stopped states."""
        normalized = state.strip().lower()
        if normalized == "stopped":
            template = "orange"
            tag_text = "Stopped"
            tag_color = "orange"
        elif normalized == "completed":
            template = "green"
            tag_text = "Completed"
            tag_color = "green"
        else:
            template = "orange"
            tag_text = "Running"
            tag_color = "blue"
        elements = [
            {
                "tag": "markdown",
                "element_id": element_id,
                "content": text,
            }
        ]
        if stop_enabled:
            elements.append(
                {
                    "tag": "column_set",
                    "horizontal_spacing": "8px",
                    "columns": [
                        {
                            "tag": "column",
                            "width": "auto",
                            "elements": [
                                self.app._card_button("Stop", "stop_turn", "default")
                            ],
                        }
                    ],
                }
            )
        elif normalized == "stopped":
            elements.append(
                {
                    "tag": "column_set",
                    "horizontal_spacing": "8px",
                    "columns": [
                        {
                            "tag": "column",
                            "width": "auto",
                            "elements": [
                                self.app._card_button("Stopped", "stopped", "default", enable_callback=False)
                            ],
                        }
                    ],
                }
            )
        return {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "enable_forward": True,
                "streaming_mode": streaming,
                "summary": {"content": "Generating..." if streaming else shorten(text, 80)},
                "streaming_config": {
                    "print_frequency_ms": {"default": 70},
                    "print_step": {"default": 1},
                    "print_strategy": "fast",
                } if streaming else {},
            },
            "header": {
                "template": template,
                "title": {"tag": "plain_text", "content": f"{provider_name.capitalize()} Reply"},
                "text_tag_list": [
                    {
                        "tag": "text_tag",
                        "text": {"tag": "plain_text", "content": tag_text},
                        "color": tag_color,
                    }
                ],
            },
            "body": {
                "padding": "14px",
                "vertical_spacing": "8px",
                "elements": elements,
            },
        }

    def create_streaming_answer_card(self, provider_name: str) -> Tuple[str, str]:
        """Create a reusable streaming card entity for one answer."""
        element_id = "answer_stream"
        card = self.answer_card(
            provider_name,
            f"PoCo is thinking with {provider_name}...",
            state="running",
            stop_enabled=True,
            streaming=True,
            element_id=element_id,
        )
        return self.app._messenger.create_card_entity(card), element_id

    def cleanup_session(self, session: TurnSession) -> None:
        """Release one finished turn and kick any queued follow-up turn."""
        queued: Optional[QueuedMessage] = None
        with self.app._lock:
            current = self.app._active_by_turn.pop((session.worker_id, session.thread_id, session.turn_id), None)
            if current is not None and self.app._active_by_worker.get(session.worker_id) is current:
                del self.app._active_by_worker[session.worker_id]
            queued = self.app._queued_by_worker.pop(session.worker_id, None)
        if queued is not None:
            self.app._safe_send(
                queued.chat_id,
                "[poco] 当前这轮已经完成，开始执行你之前排队的那条消息。",
            )
            threading.Thread(
                target=self.start_turn_for_worker,
                args=(queued.worker_id, queued.chat_id, queued.chat_type, queued.text),
                daemon=True,
            ).start()
        self.app._delete_image_files(session.image_paths)
