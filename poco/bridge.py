#!/usr/bin/env python3
import json
import logging
import os
import queue
import shlex
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
    UpdateMessageRequest,
    UpdateMessageRequestBody,
)


LOG = logging.getLogger("poco.bridge")
def chunk_text(text: str, limit: int) -> List[str]:
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
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


@dataclass
class AppConfig:
    feishu_app_id: str
    feishu_app_secret: str
    feishu_encrypt_key: str
    feishu_verification_token: str
    codex_bin: str
    codex_app_server_args: str
    codex_model: str
    codex_approval_policy: str
    codex_sandbox: str
    message_limit: int
    live_update_initial_seconds: int
    live_update_max_seconds: int
    max_message_edits: int
    allowed_open_ids: Set[str]
    allow_all_users: bool
    thread_state_path: str
    worker_state_path: str


@dataclass
class SentMessage:
    message_id: str
    chat_id: str


@dataclass
class LiveMessage:
    sent: SentMessage
    edit_count: int = 0
    last_text: str = ""


@dataclass
class TurnSession:
    worker_id: str
    chat_id: str
    thread_id: str
    turn_id: str
    prompt: str
    live: LiveMessage
    accumulated_text: str = ""
    final_text: str = ""
    error_text: str = ""
    done: bool = False
    started_at: float = field(default_factory=time.time)
    next_delay: int = 1
    next_update_at: float = field(default_factory=time.time)
    updated_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def notify(self) -> None:
        self.updated_event.set()


@dataclass
class WorkerRuntime:
    worker_id: str
    chat_id: str
    chat_type: str
    cwd: str
    codex: "AppServerClient"
    created_at: float = field(default_factory=time.time)


@dataclass
class QueuedMessage:
    worker_id: str
    chat_id: str
    chat_type: str
    text: str


@dataclass
class CodexSessionMeta:
    session_id: str
    cwd: str
    thread_name: str = ""
    updated_at: str = ""
    source: str = ""
    originator: str = ""
    file_path: str = ""


class FeishuMessenger:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._client = (
            lark.Client.builder()
            .app_id(config.feishu_app_id)
            .app_secret(config.feishu_app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

    def create_text(self, chat_id: str, text: str) -> SentMessage:
        first_sent: Optional[SentMessage] = None
        for chunk in chunk_text(text, self._config.message_limit):
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(json.dumps({"text": chunk}, ensure_ascii=False))
                    .uuid(str(uuid.uuid4()))
                    .build()
                )
                .build()
            )
            response = self._client.im.v1.message.create(request)
            if response.code != 0:
                raise RuntimeError(
                    f"Feishu send failed: code={response.code}, msg={response.msg}, "
                    f"log_id={response.get_log_id()}"
                )
            if first_sent is None:
                message_id = response.data.message_id if response.data is not None else None
                if not message_id:
                    raise RuntimeError("Feishu send succeeded but returned no message_id")
                first_sent = SentMessage(message_id=message_id, chat_id=chat_id)
        assert first_sent is not None
        return first_sent

    def send_text(self, chat_id: str, text: str) -> None:
        self.create_text(chat_id, text)

    def update_text(self, message_id: str, text: str) -> None:
        request = (
            UpdateMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                UpdateMessageRequestBody.builder()
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = self._client.im.v1.message.update(request)
        if response.code != 0:
            raise RuntimeError(
                f"Feishu update failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )


class ThreadStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data = {str(k): str(v) for k, v in raw.items()}
        except Exception:
            LOG.warning("Failed to load thread state from %s", self._path)

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, chat_id: str) -> Optional[str]:
        with self._lock:
            return self._data.get(chat_id)

    def set(self, chat_id: str, thread_id: str) -> None:
        with self._lock:
            self._data[chat_id] = thread_id
            self._save()

    def clear(self, chat_id: str) -> None:
        with self._lock:
            if chat_id in self._data:
                del self._data[chat_id]
                self._save()

    def items(self) -> List[Tuple[str, str]]:
        with self._lock:
            return sorted(self._data.items())


class CodexSessionLocator:
    def __init__(self, codex_home: Optional[Path] = None) -> None:
        root = codex_home or (Path.home() / ".codex")
        self._sessions_dir = root / "sessions"
        self._session_index_path = root / "session_index.jsonl"

    def get(self, session_id: str) -> Optional[CodexSessionMeta]:
        session_id = session_id.strip()
        if not session_id or not self._sessions_dir.exists():
            return None
        index_items = self._session_index_items()
        for path in self._sessions_dir.rglob("*.jsonl"):
            payload = self._read_session_meta_payload(path)
            if payload is None:
                continue
            if str(payload.get("id", "")).strip() != session_id:
                continue
            index_item = index_items.get(session_id, {})
            return CodexSessionMeta(
                session_id=session_id,
                cwd=str(payload.get("cwd", "")).strip(),
                thread_name=str(index_item.get("thread_name") or payload.get("thread_name", "")).strip(),
                updated_at=str(index_item.get("updated_at") or payload.get("timestamp", "")).strip(),
                source=str(payload.get("source", "")).strip(),
                originator=str(payload.get("originator", "")).strip(),
                file_path=str(path),
            )
        return None

    def list_recent(self, limit: int = 10) -> List[CodexSessionMeta]:
        index_items = self._session_index_items()
        merged: Dict[str, CodexSessionMeta] = {}

        for path in self._sessions_dir.rglob("*.jsonl") if self._sessions_dir.exists() else []:
            payload = self._read_session_meta_payload(path)
            if payload is None:
                continue
            session_id = str(payload.get("id", "")).strip()
            if not session_id:
                continue
            index_item = index_items.get(session_id, {})
            merged[session_id] = CodexSessionMeta(
                session_id=session_id,
                cwd=str(payload.get("cwd", "")).strip(),
                thread_name=str(index_item.get("thread_name") or payload.get("thread_name", "")).strip(),
                updated_at=str(index_item.get("updated_at") or payload.get("timestamp", "")).strip(),
                source=str(payload.get("source", "")).strip(),
                originator=str(payload.get("originator", "")).strip(),
                file_path=str(path),
            )

        for session_id, item in index_items.items():
            if session_id in merged:
                continue
            merged[session_id] = CodexSessionMeta(
                session_id=session_id,
                cwd="",
                thread_name=str(item.get("thread_name", "")).strip(),
                updated_at=str(item.get("updated_at", "")).strip(),
            )

        results = list(merged.values())
        results.sort(key=lambda item: item.updated_at, reverse=True)
        return results[:limit]

    def _session_index_items(self) -> Dict[str, Dict[str, str]]:
        if not self._session_index_path.exists():
            return {}
        items: Dict[str, Dict[str, str]] = {}
        try:
            with self._session_index_path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    session_id = str(payload.get("id", "")).strip()
                    if not session_id:
                        continue
                    items[session_id] = {
                        "id": session_id,
                        "thread_name": str(payload.get("thread_name", "")).strip(),
                        "updated_at": str(payload.get("updated_at", "")).strip(),
                    }
        except OSError:
            return {}
        return items

    @staticmethod
    def _read_session_meta_payload(path: Path) -> Optional[dict]:
        try:
            with path.open(encoding="utf-8") as handle:
                first_line = handle.readline()
        except OSError:
            return None
        if not first_line:
            return None
        try:
            message = json.loads(first_line)
        except json.JSONDecodeError:
            return None
        if message.get("type") != "session_meta":
            return None
        payload = message.get("payload", {})
        return payload if isinstance(payload, dict) else None


class WorkerStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, object]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cleaned: Dict[str, Dict[str, object]] = {}
                for worker_id, payload in raw.items():
                    if not isinstance(payload, dict):
                        continue
                    alias = str(payload.get("alias", "")).strip()
                    mode = str(payload.get("mode", "mention")).strip() or "mention"
                    enabled = bool(payload.get("enabled", False))
                    onboarding_sent = bool(payload.get("onboarding_sent", False))
                    cwd = str(payload.get("cwd", "")).strip()
                    cleaned[str(worker_id)] = {
                        "alias": alias,
                        "mode": mode,
                        "enabled": enabled,
                        "onboarding_sent": onboarding_sent,
                        "cwd": cwd,
                    }
                self._data = cleaned
        except Exception:
            LOG.warning("Failed to load worker state from %s", self._path)

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def alias_for(self, worker_id: str) -> str:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            return str(payload.get("alias", "")).strip()

    def set_alias(self, worker_id: str, alias: str) -> None:
        alias = alias.strip()
        with self._lock:
            for existing_worker_id, payload in list(self._data.items()):
                if existing_worker_id != worker_id and payload.get("alias", "") == alias:
                    raise ValueError(f"别名 {alias} 已被 worker {existing_worker_id} 使用。")
            record = self._ensure_record_locked(worker_id)
            record["alias"] = alias
            self._save()

    def clear_alias(self, worker_id: str) -> None:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            payload["alias"] = ""
            self._save()

    def mode_for(self, worker_id: str) -> str:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            return str(payload.get("mode", "mention")).strip() or "mention"

    def set_mode(self, worker_id: str, mode: str) -> None:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            payload["mode"] = mode
            self._save()

    def enabled_for(self, worker_id: str) -> bool:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            return bool(payload.get("enabled", False))

    def set_enabled(self, worker_id: str, enabled: bool) -> None:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            payload["enabled"] = enabled
            if enabled:
                payload["onboarding_sent"] = True
            self._save()

    def onboarding_sent_for(self, worker_id: str) -> bool:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            return bool(payload.get("onboarding_sent", False))

    def mark_onboarding_sent(self, worker_id: str) -> None:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            payload["onboarding_sent"] = True
            self._save()

    def ensure_worker(self, worker_id: str) -> None:
        with self._lock:
            self._ensure_record_locked(worker_id)
            self._save()

    def cwd_for(self, worker_id: str) -> str:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            return str(payload.get("cwd", "")).strip()

    def set_cwd(self, worker_id: str, cwd: str) -> None:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            payload["cwd"] = cwd.strip()
            self._save()

    def resolve(self, identifier: str) -> Optional[str]:
        key = identifier.strip()
        if not key:
            return None
        with self._lock:
            if key in self._data:
                return key
            for worker_id, payload in self._data.items():
                if payload.get("alias", "") == key:
                    return worker_id
        return key if key.startswith("oc_") else None

    def items(self) -> List[Tuple[str, str]]:
        with self._lock:
            return sorted((worker_id, payload.get("alias", "")) for worker_id, payload in self._data.items())

    def remove(self, worker_id: str) -> None:
        with self._lock:
            if worker_id in self._data:
                del self._data[worker_id]
                self._save()

    def _ensure_record_locked(self, worker_id: str) -> Dict[str, object]:
        payload = self._data.get(worker_id)
        if payload is None:
            payload = {
                "alias": "",
                "mode": "mention",
                "enabled": False,
                "onboarding_sent": False,
                "cwd": "",
            }
            self._data[worker_id] = payload
        return payload


class AppServerClient:
    def __init__(self, config: AppConfig, cwd: str) -> None:
        self._config = config
        self._cwd = cwd
        self._process: Optional[subprocess.Popen[str]] = None
        self._request_id = 0
        self._responses: Dict[int, "queue.Queue[dict]"] = {}
        self._responses_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._notify_queue: "queue.Queue[dict]" = queue.Queue()
        self._loaded_threads: Set[str] = set()

    def start(self) -> None:
        cmd = [self._config.codex_bin, "app-server"]
        extra_args = shlex.split(self._config.codex_app_server_args)
        cmd.extend(extra_args)
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        assert self._process.stderr is not None
        threading.Thread(target=self._stdout_loop, daemon=True).start()
        threading.Thread(target=self._stderr_loop, daemon=True).start()
        result = self._request(
            "initialize",
            {
                "clientInfo": {"name": "feishu-codex-bridge", "version": "0.1"},
                "capabilities": {"experimentalApi": True},
            },
        )
        LOG.info("App server initialized: %s", result)

    def notifications(self) -> "queue.Queue[dict]":
        return self._notify_queue

    def close(self) -> None:
        if self._process is None:
            return
        try:
            self._process.terminate()
        except Exception:
            LOG.exception("Failed to terminate app-server")
        try:
            self._notify_queue.put({"method": "__closed__"})
        except Exception:
            LOG.exception("Failed to notify app-server close")
        self._process = None

    def _stdout_loop(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        for raw_line in self._process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                LOG.warning("Invalid JSON from app-server stdout: %s", line)
                continue
            if "id" in message and ("result" in message or "error" in message):
                self._handle_response(message)
            elif "method" in message:
                self._notify_queue.put(message)
            else:
                LOG.debug("Unrecognized app-server message: %s", message)

    def _stderr_loop(self) -> None:
        assert self._process is not None
        assert self._process.stderr is not None
        for raw_line in self._process.stderr:
            line = raw_line.rstrip("\n")
            if line:
                LOG.warning("app-server stderr: %s", line)

    def _handle_response(self, message: dict) -> None:
        response_id = message.get("id")
        if not isinstance(response_id, int):
            return
        with self._responses_lock:
            waiter = self._responses.get(response_id)
        if waiter is not None:
            waiter.put(message)

    def _request(self, method: str, params: dict, timeout: float = 30.0) -> dict:
        if self._process is None or self._process.poll() is not None:
            raise RuntimeError("app-server is not running")
        with self._responses_lock:
            self._request_id += 1
            request_id = self._request_id
            waiter: "queue.Queue[dict]" = queue.Queue(maxsize=1)
            self._responses[request_id] = waiter
        message = {"id": request_id, "method": method, "params": params}
        with self._write_lock:
            assert self._process.stdin is not None
            self._process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
        try:
            response = waiter.get(timeout=timeout)
        except queue.Empty as exc:
            raise RuntimeError(f"app-server request timed out: {method}") from exc
        finally:
            with self._responses_lock:
                self._responses.pop(request_id, None)
        if "error" in response:
            error = response["error"]
            raise RuntimeError(f"app-server error on {method}: {error}")
        return response["result"]

    def ensure_thread(self, thread_id: Optional[str]) -> str:
        if thread_id:
            if thread_id not in self._loaded_threads:
                self._request(
                    "thread/resume",
                    {
                        "threadId": thread_id,
                        "cwd": self._cwd,
                        "approvalPolicy": self._config.codex_approval_policy,
                        "sandbox": self._config.codex_sandbox,
                        "model": self._config.codex_model or None,
                    },
                )
                self._loaded_threads.add(thread_id)
            return thread_id
        result = self._request(
            "thread/start",
            {
                "cwd": self._cwd,
                "approvalPolicy": self._config.codex_approval_policy,
                "sandbox": self._config.codex_sandbox,
                "model": self._config.codex_model or None,
            },
        )
        new_thread_id = result["thread"]["id"]
        self._loaded_threads.add(new_thread_id)
        return new_thread_id

    def start_turn(self, thread_id: str, text: str) -> str:
        result = self._request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [{"type": "text", "text": text}],
            },
            timeout=60.0,
        )
        return result["turn"]["id"]

    def interrupt_turn(self, thread_id: str, turn_id: str) -> None:
        self._request(
            "turn/interrupt",
            {"threadId": thread_id, "turnId": turn_id},
            timeout=10.0,
        )

    def steer_turn(self, thread_id: str, turn_id: str, text: str) -> None:
        self._request(
            "turn/steer",
            {
                "threadId": thread_id,
                "expectedTurnId": turn_id,
                "input": [{"type": "text", "text": text}],
            },
            timeout=30.0,
        )


class BridgeApp:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._messenger = FeishuMessenger(config)
        self._store = ThreadStore(Path(config.thread_state_path))
        self._worker_store = WorkerStore(Path(config.worker_state_path))
        self._session_locator = CodexSessionLocator()
        self._command_queue: "queue.Queue[Dict[str, object]]" = queue.Queue()
        self._known_message_ids: Set[str] = set()
        self._workers: Dict[str, WorkerRuntime] = {}
        self._active_by_worker: Dict[str, TurnSession] = {}
        self._active_by_turn: Dict[Tuple[str, str, str], TurnSession] = {}
        self._queued_by_worker: Dict[str, QueuedMessage] = {}
        self._lock = threading.Lock()

    def run(self) -> None:
        threading.Thread(target=self._command_loop, daemon=True).start()
        event_handler = (
            lark.EventDispatcherHandler.builder(
                self._config.feishu_encrypt_key,
                self._config.feishu_verification_token,
            )
            .register_p2_im_message_receive_v1(self._on_message_received)
            .build()
        )
        ws_client = lark.ws.Client(
            self._config.feishu_app_id,
            self._config.feishu_app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )
        LOG.info("App-server bridge is running.")
        ws_client.start()

    def _on_message_received(self, data: P2ImMessageReceiveV1) -> None:
        message = data.event.message
        sender = data.event.sender
        if message is None or sender is None or sender.sender_id is None or not message.chat_id:
            return
        if message.message_type != "text":
            return
        if sender.sender_type != "user":
            return
        chat_type = message.chat_type or ""
        open_id = sender.sender_id.open_id or ""
        LOG.info(
            "Received message from open_id=%s chat_id=%s chat_type=%s",
            open_id,
            message.chat_id,
            chat_type,
        )
        if not self._is_allowed_user(open_id):
            LOG.warning("Ignored message from unauthorized user: %s", open_id)
            return
        if message.message_id in self._known_message_ids:
            return
        self._known_message_ids.add(message.message_id)
        text = self._extract_text(message.content)
        if not text:
            return
        self._command_queue.put(
            {
                "chat_id": message.chat_id,
                "chat_type": chat_type,
                "text": text,
                "mentions": list(message.mentions or []),
            }
        )

    def _command_loop(self) -> None:
        while True:
            payload = self._command_queue.get()
            threading.Thread(target=self._process_command, args=(payload,), daemon=True).start()

    def _process_command(self, payload: Dict[str, object]) -> None:
        chat_id = str(payload["chat_id"])
        chat_type = str(payload["chat_type"])
        text = str(payload["text"])
        mentions = list(payload.get("mentions", []))
        try:
            if chat_type == "p2p":
                self._handle_dm_command(chat_id, text)
            else:
                self._handle_group_command(chat_id, chat_type, text, mentions)
        except Exception as exc:
            LOG.exception("Command failed")
            self._safe_send(chat_id, f"[bridge] 执行失败\n{exc}")

    def _parse_poco_command(self, text: str) -> Tuple[Optional[str], str]:
        stripped = text.strip()
        if not stripped.startswith("/poco"):
            return None, ""
        rest = stripped[len("/poco"):].strip()
        if not rest:
            return "help", ""
        if " " not in rest:
            return rest.lower(), ""
        command, arg = rest.split(" ", 1)
        return command.lower(), arg.strip()

    def _handle_dm_command(self, chat_id: str, text: str) -> None:
        command, arg = self._parse_poco_command(text)
        if command is None:
            self._safe_send(chat_id, self._dm_help_text())
            return
        if command == "help":
            self._safe_send(chat_id, self._dm_help_text())
            return
        if command in {"workers", "list"}:
            self._safe_send(chat_id, self._workers_text())
            return
        if command == "sessions":
            limit = 10
            if arg:
                try:
                    limit = max(1, min(50, int(arg)))
                except ValueError:
                    self._safe_send(chat_id, "[bridge] 用法：/poco sessions [limit]")
                    return
            self._safe_send(chat_id, self._sessions_text(limit))
            return
        if command == "status":
            if not arg:
                self._safe_send(chat_id, self._workers_text())
                return
            self._safe_send(chat_id, self._worker_status_text(self._resolve_worker_id(arg), requested=arg))
            return
        if command == "stop":
            if not arg:
                self._safe_send(chat_id, "[bridge] 用法：/poco stop <worker_alias|group_chat_id>")
                return
            worker_id = self._resolve_worker_id(arg)
            if worker_id is None:
                self._safe_send(chat_id, f"[bridge] 找不到 worker：{arg}")
                return
            with self._lock:
                session = self._active_by_worker.get(worker_id)
            if session is None:
                self._safe_send(chat_id, f"[bridge] worker {worker_id} 当前没有进行中的回复。")
                return
            worker = self._get_worker(worker_id)
            if worker is None:
                self._safe_send(chat_id, f"[bridge] worker {worker_id} 不存在。")
                return
            worker.codex.interrupt_turn(session.thread_id, session.turn_id)
            self._safe_send(chat_id, f"[bridge] 已请求停止 worker {worker_id} 的当前回复。")
            return
        if command == "reset":
            if not arg:
                self._safe_send(chat_id, "[bridge] 用法：/poco reset <worker_alias|group_chat_id>")
                return
            worker_id = self._resolve_worker_id(arg)
            if worker_id is None:
                self._safe_send(chat_id, f"[bridge] 找不到 worker：{arg}")
                return
            with self._lock:
                session = self._active_by_worker.get(worker_id)
                if session is not None:
                    self._safe_send(chat_id, "[bridge] 该 worker 当前还有一轮在进行中，先等待完成或使用 /stop。")
                    return
            self._store.clear(worker_id)
            self._safe_send(chat_id, f"[bridge] 已清空 worker {worker_id} 绑定的 Codex 会话。")
            return
        if command == "remove":
            if not arg:
                self._safe_send(chat_id, "[bridge] 用法：/poco remove <worker_alias|group_chat_id>")
                return
            worker_id = self._resolve_worker_id(arg)
            if worker_id is None:
                self._safe_send(chat_id, f"[bridge] 找不到 worker：{arg}")
                return
            self._remove_worker(worker_id)
            self._safe_send(chat_id, f"[bridge] 已移除 worker {worker_id}。")
            return
        self._safe_send(chat_id, "[bridge] 未知管理命令。使用 /poco help 查看可用命令。")

    def _handle_group_command(self, chat_id: str, chat_type: str, text: str, mentions: list) -> None:
        worker_id = chat_id
        self._worker_store.ensure_worker(worker_id)
        command, arg = self._parse_poco_command(text)
        if command == "help":
            self._safe_send(chat_id, self._group_help_text())
            return
        if command == "mode":
            if arg not in {"mention", "auto"}:
                self._safe_send(chat_id, "[bridge] 用法：/poco mode <mention|auto>")
                return
            self._worker_store.set_mode(worker_id, arg)
            self._safe_send(chat_id, f"[bridge] 当前群模式已设置为 {arg}")
            return
        if command == "cwd":
            cwd = arg.strip()
            if not cwd:
                current_cwd = self._worker_store.cwd_for(worker_id)
                self._safe_send(chat_id, f"[bridge] 当前群 cwd: {current_cwd or '(未设置)'}")
                return
            validation_error = self._validate_cwd(cwd)
            if validation_error:
                self._safe_send(chat_id, f"[bridge] cwd 无效：{validation_error}")
                return
            self._worker_store.set_cwd(worker_id, cwd)
            self._safe_send(chat_id, f"[bridge] 当前群工作目录已设置为 {cwd}")
            return
        if command == "attach":
            session_id = arg.strip()
            if not session_id:
                self._safe_send(chat_id, "[bridge] 用法：/poco attach <session_id>")
                return
            meta = self._attach_session(worker_id, session_id, allow_create=True)
            message = f"[bridge] 已将当前项目 worker 绑定到 session {meta.session_id}。"
            if meta.cwd:
                message += f"\ncwd: {meta.cwd}"
            elif self._worker_store.cwd_for(worker_id):
                message += f"\ncwd: {self._worker_store.cwd_for(worker_id)}"
            else:
                message += "\n注意：未找到 session 的 cwd，请先手动设置 /poco cwd <path>。"
            if not self._worker_store.enabled_for(worker_id):
                message += "\n当前群还未启用；如需开始接管，请继续执行 /poco enable。"
            self._safe_send(chat_id, message)
            return
        if command == "enable":
            cwd = self._worker_store.cwd_for(worker_id)
            if not cwd:
                self._safe_send(chat_id, "[bridge] 启用前必须先设置 /poco cwd <path>")
                return
            validation_error = self._validate_cwd(cwd)
            if validation_error:
                self._safe_send(chat_id, f"[bridge] 当前群 cwd 无效：{validation_error}")
                return
            self._worker_store.set_enabled(worker_id, True)
            self._safe_send(chat_id, "[bridge] 当前群已启用。之后会按当前 mode 处理新消息。")
            return
        if command == "disable":
            self._worker_store.set_enabled(worker_id, False)
            self._safe_send(chat_id, "[bridge] 当前群已停用。未重新启用前，不会把群消息发给 Codex。")
            return
        if command in {"reset", "new"}:
            with self._lock:
                session = self._active_by_worker.get(worker_id)
                if session is not None:
                    self._safe_send(chat_id, "[bridge] 当前还有一轮在进行中，先等待完成或使用 /stop。")
                    return
            self._store.clear(worker_id)
            self._safe_send(chat_id, "[bridge] 已清空当前项目群绑定的 Codex 会话。下一条消息会新开线程。")
            return
        if command == "status":
            self._safe_send(chat_id, self._worker_status_text(worker_id))
            return
        if command == "name":
            alias = arg.strip()
            if not alias:
                self._safe_send(chat_id, "[bridge] 用法：/poco name <alias>")
                return
            normalized_alias = self._normalize_alias(alias)
            if normalized_alias is None:
                self._safe_send(chat_id, "[bridge] alias 只能包含小写字母、数字、- 和 _，长度 2-32。")
                return
            self._worker_store.set_alias(worker_id, normalized_alias)
            self._safe_send(chat_id, f"[bridge] 当前项目 worker 已命名为 {normalized_alias}")
            return
        if command in {"unname", "clear-name"}:
            self._worker_store.clear_alias(worker_id)
            self._safe_send(chat_id, "[bridge] 当前项目 worker 的别名已清空。")
            return
        if command == "stop":
            with self._lock:
                session = self._active_by_worker.get(worker_id)
            if session is None:
                self._safe_send(chat_id, "[bridge] 当前没有进行中的回复。")
                return
            worker = self._ensure_worker(worker_id, chat_id, chat_type)
            worker.codex.interrupt_turn(session.thread_id, session.turn_id)
            self._safe_send(chat_id, "[bridge] 已请求停止当前回复。")
            return
        if command == "steer":
            steer_text = arg.strip()
            if not steer_text:
                self._safe_send(chat_id, "[bridge] 用法：/poco steer <message>")
                return
            with self._lock:
                session = self._active_by_worker.get(worker_id)
            if session is None:
                self._safe_send(chat_id, "[bridge] 当前没有进行中的回复，不需要 steer。直接发送普通消息即可。")
                return
            worker = self._ensure_worker(worker_id, chat_id, chat_type)
            worker.codex.steer_turn(session.thread_id, session.turn_id, steer_text)
            self._safe_send(chat_id, "[bridge] 已将你的补充指令发送给当前这轮回复。")
            return
        if command == "queue":
            queued_text = arg.strip()
            if not queued_text:
                self._safe_send(chat_id, "[bridge] 用法：/poco queue <message>")
                return
            with self._lock:
                session = self._active_by_worker.get(worker_id)
                existing = self._queued_by_worker.get(worker_id)
            if session is None:
                self._safe_send(chat_id, "[bridge] 当前没有进行中的回复，不需要 queue。直接发送普通消息即可。")
                return
            if existing is not None:
                self._safe_send(chat_id, "[bridge] 当前已经有一条排队消息。等它执行完再追加。")
                return
            with self._lock:
                self._queued_by_worker[worker_id] = QueuedMessage(
                    worker_id=worker_id,
                    chat_id=chat_id,
                    chat_type=chat_type,
                    text=queued_text,
                )
            self._safe_send(chat_id, "[bridge] 已加入队列。当前这轮完成后，会自动发送这条消息。")
            return
        if command == "remove":
            self._remove_worker(worker_id)
            self._safe_send(chat_id, "[bridge] 已移除当前项目 worker。下次 @bot 发消息会自动重新创建。")
            return
        if command is not None:
            self._safe_send(chat_id, "[bridge] 未知管理命令。使用 /poco help 查看可用命令。")
            return

        if not self._worker_store.enabled_for(worker_id):
            self._send_group_setup_prompt(chat_id, worker_id)
            return

        mode = self._worker_store.mode_for(worker_id)
        if mode == "mention":
            if not self._is_group_bot_mention(mentions):
                return
            text = self._strip_mentions(text, mentions)
            if not text:
                return
        elif mode == "auto":
            text = self._strip_mentions(text, mentions)
        else:
            self._safe_send(chat_id, f"[bridge] 未知群模式：{mode}")
            return

        with self._lock:
            if worker_id in self._active_by_worker:
                self._safe_send(
                    chat_id,
                    "[bridge] 上一轮还在处理中。\n"
                    "这条消息没有被执行。\n"
                    "如果你只是想补充指令，请使用 /poco steer <message>。\n"
                    "如果你想让它在下一轮自动执行，请使用 /poco queue <message>。\n"
                    "如果你想终止当前任务，请使用 /poco stop。",
                )
                return

        self._start_turn_for_worker(worker_id, chat_id, chat_type, text)

    def _notification_loop(self, worker_id: str, codex: AppServerClient) -> None:
        notifications = codex.notifications()
        while True:
            message = notifications.get()
            if message.get("method") == "__closed__":
                return
            try:
                self._handle_notification(worker_id, message)
            except Exception:
                LOG.exception("Failed to handle app-server notification for worker %s", worker_id)

    def _handle_notification(self, worker_id: str, message: dict) -> None:
        method = message.get("method")
        params = message.get("params", {})
        if method == "item/agentMessage/delta":
            self._on_agent_delta(worker_id, params)
            return
        if method == "item/completed":
            self._on_item_completed(worker_id, params)
            return
        if method == "turn/completed":
            self._on_turn_completed(worker_id, params)
            return
        if method == "error":
            LOG.error("app-server notification error: %s", params)
            return
        LOG.debug("Ignored app-server notification: %s", method)

    def _lookup_session(self, worker_id: str, thread_id: str, turn_id: str) -> Optional[TurnSession]:
        with self._lock:
            return self._active_by_turn.get((worker_id, thread_id, turn_id))

    def _on_agent_delta(self, worker_id: str, params: dict) -> None:
        thread_id = params.get("threadId")
        turn_id = params.get("turnId")
        delta = str(params.get("delta", ""))
        if not thread_id or not turn_id or not delta:
            return
        session = self._lookup_session(worker_id, thread_id, turn_id)
        if session is None:
            return
        with session.lock:
            session.accumulated_text += delta
        session.notify()

    def _on_item_completed(self, worker_id: str, params: dict) -> None:
        thread_id = params.get("threadId")
        turn_id = params.get("turnId")
        item = params.get("item", {})
        if not thread_id or not turn_id or not isinstance(item, dict):
            return
        if item.get("type") != "agentMessage":
            return
        session = self._lookup_session(worker_id, thread_id, turn_id)
        if session is None:
            return
        final_text = str(item.get("text", "")).strip()
        if not final_text:
            return
        with session.lock:
            session.accumulated_text = final_text
            session.final_text = final_text
        session.notify()

    def _on_turn_completed(self, worker_id: str, params: dict) -> None:
        thread_id = params.get("threadId")
        turn = params.get("turn", {})
        if not thread_id or not isinstance(turn, dict):
            return
        turn_id = turn.get("id")
        if not turn_id:
            return
        session = self._lookup_session(worker_id, thread_id, turn_id)
        if session is None:
            return
        status = str(turn.get("status", "completed"))
        with session.lock:
            session.done = True
            if status != "completed" and not session.error_text:
                session.error_text = f"[bridge] 当前回复已结束，状态：{status}"
        session.notify()

    def _render_loop(self, session: TurnSession) -> None:
        max_delay = max(
            max(1, self._config.live_update_initial_seconds),
            self._config.live_update_max_seconds,
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
                    self._render_text(session, error_text, final=True)
                elif final_text or accumulated:
                    self._render_text(session, final_text or accumulated, final=True)
                else:
                    self._render_text(session, "[bridge] 回复已完成，但没有可显示的文本。", final=True)
                self._cleanup_session(session)
                return

            if accumulated and now >= next_update_at:
                self._render_text(session, accumulated, final=False)
                with session.lock:
                    session.next_delay = min(next_delay * 2, max_delay)
                    session.next_update_at = now + session.next_delay
                continue

            if not accumulated and now >= next_update_at:
                status_text = (
                    "[bridge] Codex 正在处理...\n"
                    f"已等待 {elapsed}s\n"
                    f"本轮问题：{shorten(session.prompt, 100)}"
                )
                self._render_text(session, status_text, final=False)
                with session.lock:
                    session.next_delay = min(next_delay * 2, max_delay)
                    session.next_update_at = now + session.next_delay

    def _render_text(self, session: TurnSession, text: str, final: bool) -> None:
        rendered = self._with_turn_state(text, completed=final)
        chunks = chunk_text(rendered, self._config.message_limit)
        if not chunks:
            chunks = [""]
        live = session.live
        live = self._update_live_message(session.chat_id, live, chunks[0])
        session.live = live
        if final:
            for chunk in chunks[1:]:
                self._messenger.send_text(session.chat_id, chunk)

    def _update_live_message(self, chat_id: str, live: LiveMessage, text: str) -> LiveMessage:
        if text == live.last_text:
            return live
        if live.edit_count >= self._config.max_message_edits:
            new_sent = self._messenger.create_text(chat_id, text)
            return LiveMessage(sent=new_sent, edit_count=0, last_text=text)
        try:
            self._messenger.update_text(live.sent.message_id, text)
            live.edit_count += 1
            live.last_text = text
            return live
        except Exception:
            LOG.exception("Message update failed, falling back to create a new message")
            new_sent = self._messenger.create_text(chat_id, text)
            return LiveMessage(sent=new_sent, edit_count=0, last_text=text)

    @staticmethod
    def _with_turn_state(text: str, *, completed: bool) -> str:
        status_line = (
            "[poco] state: completed, you can send the next message now."
            if completed
            else "[poco] state: running, please wait before sending the next message."
        )
        base = text.rstrip()
        if not base:
            return status_line
        return f"{base}\n\n{status_line}"

    def _start_turn_for_worker(self, worker_id: str, chat_id: str, chat_type: str, text: str) -> None:
        worker = self._ensure_worker(worker_id, chat_id, chat_type)
        thread_id = worker.codex.ensure_thread(self._store.get(worker_id))
        self._store.set(worker_id, thread_id)
        initial_text = self._with_turn_state("[bridge] 已发送给 Codex，处理中...", completed=False)
        live = LiveMessage(
            sent=self._messenger.create_text(chat_id, initial_text),
            last_text=initial_text,
        )
        turn_id = worker.codex.start_turn(thread_id, text)
        session = TurnSession(
            worker_id=worker_id,
            chat_id=chat_id,
            thread_id=thread_id,
            turn_id=turn_id,
            prompt=text,
            live=live,
            next_delay=max(1, self._config.live_update_initial_seconds),
            next_update_at=time.time() + max(1, self._config.live_update_initial_seconds),
        )
        with self._lock:
            self._active_by_worker[worker_id] = session
            self._active_by_turn[(worker_id, thread_id, turn_id)] = session
        threading.Thread(target=self._render_loop, args=(session,), daemon=True).start()

    def _cleanup_session(self, session: TurnSession) -> None:
        queued: Optional[QueuedMessage] = None
        with self._lock:
            current = self._active_by_turn.pop((session.worker_id, session.thread_id, session.turn_id), None)
            if current is not None and self._active_by_worker.get(session.worker_id) is current:
                del self._active_by_worker[session.worker_id]
            queued = self._queued_by_worker.pop(session.worker_id, None)
        if queued is not None:
            self._safe_send(
                queued.chat_id,
                "[bridge] 当前这轮已经完成，开始执行你之前排队的那条消息。",
            )
            threading.Thread(
                target=self._start_turn_for_worker,
                args=(queued.worker_id, queued.chat_id, queued.chat_type, queued.text),
                daemon=True,
            ).start()

    def _extract_text(self, raw: Optional[str]) -> str:
        if not raw:
            return ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip()
        return str(data.get("text", "")).strip()

    def _is_allowed_user(self, open_id: str) -> bool:
        if self._config.allow_all_users:
            return True
        if not self._config.allowed_open_ids:
            return False
        return open_id in self._config.allowed_open_ids

    def _is_group_bot_mention(self, mentions: Optional[list]) -> bool:
        return bool(mentions)

    def _strip_mentions(self, text: str, mentions: Optional[list]) -> str:
        cleaned = text
        for mention in mentions or []:
            key = getattr(mention, "key", None)
            name = getattr(mention, "name", None)
            if key:
                cleaned = cleaned.replace(str(key), " ")
            if name:
                cleaned = cleaned.replace(f"@{name}", " ")
        return " ".join(cleaned.split())

    def _ensure_worker(self, worker_id: str, chat_id: str, chat_type: str) -> WorkerRuntime:
        self._worker_store.ensure_worker(worker_id)
        cwd = self._worker_store.cwd_for(worker_id)
        if not cwd:
            raise RuntimeError("当前 worker 还没有配置 cwd。先执行 /poco cwd <path>。")
        validation_error = self._validate_cwd(cwd)
        if validation_error:
            raise RuntimeError(f"当前 worker 的 cwd 无效：{validation_error}")
        with self._lock:
            existing = self._workers.get(worker_id)
            if existing is not None:
                return existing
            codex = AppServerClient(self._config, cwd)
            codex.start()
            worker = WorkerRuntime(
                worker_id=worker_id,
                chat_id=chat_id,
                chat_type=chat_type,
                cwd=cwd,
                codex=codex,
            )
            self._workers[worker_id] = worker
        threading.Thread(
            target=self._notification_loop,
            args=(worker_id, codex),
            daemon=True,
            name=f"poco-worker-{worker_id[:8]}",
        ).start()
        LOG.info("Started worker %s for chat_id=%s chat_type=%s", worker_id, chat_id, chat_type)
        return worker

    def _attach_session(self, worker_id: str, session_id: str, *, allow_create: bool) -> CodexSessionMeta:
        session_id = session_id.strip()
        if not session_id:
            raise RuntimeError("session_id 不能为空。")
        try:
            uuid.UUID(session_id)
        except ValueError as exc:
            raise RuntimeError("当前只支持用 session UUID 进行 attach。") from exc
        self._worker_store.ensure_worker(worker_id)
        with self._lock:
            session = self._active_by_worker.get(worker_id)
            if session is not None:
                raise RuntimeError("该 worker 当前还有一轮在进行中，先等待完成或使用 /poco stop。")
            worker = self._workers.pop(worker_id, None)
        if worker is not None:
            worker.codex.close()
        meta = self._session_locator.get(session_id) or CodexSessionMeta(session_id=session_id, cwd="")
        if meta.cwd:
            validation_error = self._validate_cwd(meta.cwd)
            if validation_error:
                raise RuntimeError(f"session 的 cwd 无效：{validation_error}")
            self._worker_store.set_cwd(worker_id, meta.cwd)
        elif not self._worker_store.cwd_for(worker_id):
            raise RuntimeError("未找到该 session 的 cwd，请先手动设置 /poco cwd <path>。")
        if allow_create:
            self._worker_store.ensure_worker(worker_id)
        self._store.set(worker_id, session_id)
        return meta

    def _get_worker(self, worker_id: str) -> Optional[WorkerRuntime]:
        with self._lock:
            return self._workers.get(worker_id)

    def _remove_worker(self, worker_id: str) -> None:
        with self._lock:
            session = self._active_by_worker.get(worker_id)
            if session is not None:
                raise RuntimeError("该 worker 当前还有一轮在进行中，先等待完成或使用 /poco stop。")
            worker = self._workers.pop(worker_id, None)
        self._store.clear(worker_id)
        self._worker_store.remove(worker_id)
        if worker is not None:
            worker.codex.close()
            LOG.info("Removed worker %s", worker_id)

    def _send_group_setup_prompt(self, chat_id: str, worker_id: str) -> None:
        if self._worker_store.onboarding_sent_for(worker_id):
            self._safe_send(chat_id, "[bridge] 当前群还没启用。请先执行 /poco help 查看初始化步骤。")
            return
        self._worker_store.mark_onboarding_sent(worker_id)
        self._safe_send(
            chat_id,
            (
                "[bridge] 我已加入这个群，但当前还没启用。\n"
                "请先完成初始化：\n"
                "1. /poco name <alias> 给当前项目 worker 取个名字\n"
                "2. /poco cwd <path> 设置当前项目工作目录\n"
                "3. /poco mode <mention|auto> 设置群模式\n"
                "4. /poco enable 启用当前群\n"
                "在启用前，我不会把群消息发给 Codex。"
            ),
        )

    def _resolve_worker_id(self, identifier: str) -> Optional[str]:
        return self._worker_store.resolve(identifier)

    def _display_worker_name(self, worker_id: str) -> str:
        alias = self._worker_store.alias_for(worker_id)
        return alias or worker_id

    def _normalize_alias(self, alias: str) -> Optional[str]:
        value = alias.strip().lower()
        if len(value) < 2 or len(value) > 32:
            return None
        for char in value:
            if not (char.islower() or char.isdigit() or char in {"-", "_"}):
                return None
        return value

    def _validate_cwd(self, cwd: str) -> Optional[str]:
        path = Path(cwd).expanduser()
        if not path.exists():
            return "路径不存在"
        if not path.is_dir():
            return "路径不是目录"
        if not os.access(path, os.R_OK | os.X_OK):
            return "当前进程没有访问权限"
        return None

    def _workers_text(self) -> str:
        thread_items = dict(self._store.items())
        alias_items = dict(self._worker_store.items())
        known_worker_ids = sorted(set(thread_items) | set(alias_items) | set(self._workers))
        if not known_worker_ids:
            return "[bridge] 当前还没有项目 worker。把 bot 拉进项目群后，在群里 @bot 发消息即可自动创建。"
        lines = ["[bridge] 当前 workers："]
        with self._lock:
            active_by_worker = {key: session.turn_id for key, session in self._active_by_worker.items()}
            known_workers = set(self._workers)
        for worker_id in known_worker_ids:
            alias = alias_items.get(worker_id, "")
            thread_id = thread_items.get(worker_id, "(none)")
            running = worker_id in known_workers
            active_turn = active_by_worker.get(worker_id, "(none)")
            enabled = self._worker_store.enabled_for(worker_id)
            mode = self._worker_store.mode_for(worker_id)
            cwd = self._worker_store.cwd_for(worker_id)
            lines.append(
                f"- {alias or worker_id}\n"
                f"  worker_id={worker_id}\n"
                f"  enabled={enabled}\n"
                f"  mode={mode}\n"
                f"  cwd={cwd or '(unset)'}\n"
                f"  thread_id={thread_id}\n"
                f"  process_running={running}\n"
                f"  active_turn={active_turn}"
            )
        return "\n".join(lines)

    def _sessions_text(self, limit: int) -> str:
        sessions = self._session_locator.list_recent(limit)
        if not sessions:
            return "[bridge] 当前没有找到可用的本地 Codex sessions。"
        lines = [f"[bridge] 最近 {len(sessions)} 个可接管的 Codex sessions："]
        for item in sessions:
            title = item.thread_name or "(untitled)"
            lines.append(
                f"- {item.session_id}\n"
                f"  title={title}\n"
                f"  cwd={item.cwd or '(unknown)'}\n"
                f"  updated_at={item.updated_at or '(unknown)'}\n"
                f"  source={item.source or '(unknown)'}\n"
                f"  originator={item.originator or '(unknown)'}"
            )
        return "\n".join(lines)

    def _worker_status_text(self, worker_id: Optional[str], *, requested: Optional[str] = None) -> str:
        if worker_id is None:
            target = requested or "(unknown)"
            return f"[bridge] worker {target} 不存在。"
        thread_id = self._store.get(worker_id)
        worker = self._get_worker(worker_id)
        with self._lock:
            active = self._active_by_worker.get(worker_id)
        active_turn = active.turn_id if active is not None else "(none)"
        alias = self._worker_store.alias_for(worker_id)
        enabled = self._worker_store.enabled_for(worker_id)
        mode = self._worker_store.mode_for(worker_id)
        cwd = self._worker_store.cwd_for(worker_id)
        if thread_id is None and worker is None and active is None and not alias and not enabled and not cwd:
            return f"[bridge] worker {worker_id} 不存在。"
        return (
            f"[bridge] worker: {alias or worker_id}\n"
            f"worker_id: {worker_id}\n"
            f"enabled: {enabled}\n"
            f"mode: {mode}\n"
            f"cwd: {cwd or '(unset)'}\n"
            f"thread_id: {thread_id or '(none)'}\n"
            f"process_running: {worker is not None}\n"
            f"active_turn: {active_turn}"
        )

    def _safe_send(self, chat_id: str, text: str) -> None:
        try:
            self._messenger.send_text(chat_id, text)
        except Exception:
            LOG.exception("Failed to send Feishu message")

    @staticmethod
    def _group_help_text() -> str:
        return (
            "[bridge] 这是项目工作区模式。\n"
            "当前群支持两种模式：mention 和 auto。\n"
            "/poco help 查看帮助\n"
            "/poco attach <session_id> 绑定到现有 Codex session\n"
            "/poco cwd <path> 设置当前项目工作目录\n"
            "/poco mode <mention|auto> 设置群模式\n"
            "/poco enable 启用当前群\n"
            "/poco disable 停用当前群\n"
            "/poco reset 清空当前项目群绑定的 Codex 会话\n"
            "/poco new 新建会话（等同 reset）\n"
            "/poco name <alias> 给当前项目 worker 取别名\n"
            "/poco unname 清空当前项目 worker 的别名\n"
            "/poco status 查看当前 worker 的状态\n"
            "/poco stop 停止当前回复\n"
            "/poco steer <message> 给当前回复补充引导\n"
            "/poco queue <message> 把一条消息排到下一轮执行\n"
            "/poco remove 移除当前项目 worker\n"
            "启用后：\n"
            "- mention 模式：只有 @bot 的消息会发给 Codex\n"
            "- auto 模式：群里后续所有新消息都会发给 Codex\n"
            "在启用前，普通群消息会被 bridge 拦截。"
        )

    @staticmethod
    def _dm_help_text() -> str:
        return (
            "[bridge] 这是单聊管理控制台。\n"
            "/poco help 查看帮助\n"
            "/poco workers 或 /poco list 列出当前所有项目 worker\n"
            "/poco sessions [limit] 列出最近可接管的 Codex sessions\n"
            "/poco status <worker_alias|group_chat_id> 查看某个 worker 状态\n"
            "/poco stop <worker_alias|group_chat_id> 停止某个 worker 当前回复\n"
            "/poco reset <worker_alias|group_chat_id> 清空某个 worker 的会话\n"
            "/poco remove <worker_alias|group_chat_id> 移除某个 worker\n"
            "把 bot 拉进项目群后，在群里 @bot 发消息即可创建独立 worker。"
        )
