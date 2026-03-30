import json
import logging
import os
import queue
import hashlib
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from .cards import SetupCardController
from .messenger import FeishuMessenger
from .models import (
    AppConfig,
    PendingImages,
    QueuedMessage,
    SentMessage,
    TurnSession,
    WorkerRuntime,
)
from .runtime import TurnController
from .stores import ThreadStore, WorkerStore
from .utils import IMAGE_CACHE_DIR, patch_lark_ws_card_callbacks
from ..providers import (
    ProviderClient,
    ProviderConfig,
    SessionLocator,
    SessionMeta,
    build_provider_client,
    build_session_locators,
    model_choices,
)


LOG = logging.getLogger("poco.relay")


class RelayApp:
    def __init__(self, config: AppConfig) -> None:
        patch_lark_ws_card_callbacks()
        self.LOG = LOG
        self._config = config
        self._messenger = FeishuMessenger(config)
        self._store = ThreadStore(Path(config.thread_state_path))
        self._worker_store = WorkerStore(Path(config.worker_state_path))
        self._cards = SetupCardController(self)
        self._turns = TurnController(self)
        self._session_locators: Dict[str, SessionLocator] = build_session_locators()
        self._command_queue: "queue.Queue[Dict[str, object]]" = queue.Queue()
        self._known_message_ids: Set[str] = set()
        self._workers: Dict[str, WorkerRuntime] = {}
        self._active_by_worker: Dict[str, TurnSession] = {}
        self._active_by_turn: Dict[Tuple[str, str, str], TurnSession] = {}
        self._queued_by_worker: Dict[str, QueuedMessage] = {}
        self._pending_images: Dict[Tuple[str, str], PendingImages] = {}
        self._project_drafts: Dict[str, Dict[str, str]] = {}
        self._dm_active_card_ids: Dict[str, List[str]] = {}
        self._lock = threading.Lock()

    def _provider_name_for_worker(self, worker_id: str) -> str:
        return self._worker_store.provider_for(worker_id)

    def _provider_label(self, provider_name: str) -> str:
        return provider_name.strip().lower()

    def _claude_backend_name(self, worker_id: Optional[str] = None) -> str:
        if worker_id is not None:
            backend = self._worker_store.backend_for(worker_id).strip().lower()
            if backend:
                return backend
        backend = self._config.claude_default_backend.strip().lower()
        return backend or "anthropic"

    def _claude_backend_payload(self, worker_id: Optional[str] = None) -> Dict[str, object]:
        backend_name = self._claude_backend_name(worker_id)
        payload = self._config.claude_backends.get(backend_name, {})
        return payload if isinstance(payload, dict) else {}

    def _claude_base_env(self, model: str, worker_id: Optional[str] = None) -> Dict[str, str]:
        payload = self._claude_backend_payload(worker_id)
        env: Dict[str, str] = {}
        base_url = str(payload.get("base_url", "")).strip()
        auth_token = str(payload.get("auth_token", "")).strip()
        if base_url:
            env["ANTHROPIC_BASE_URL"] = base_url
        if auth_token:
            env["ANTHROPIC_AUTH_TOKEN"] = auth_token
        extra_env = payload.get("extra_env", {})
        if isinstance(extra_env, dict):
            env.update({str(k): str(v) for k, v in extra_env.items()})
        if model:
            env.setdefault("ANTHROPIC_MODEL", model)
            env.setdefault("ANTHROPIC_SMALL_FAST_MODEL", model)
            env.setdefault("ANTHROPIC_DEFAULT_SONNET_MODEL", model)
            env.setdefault("ANTHROPIC_DEFAULT_OPUS_MODEL", model)
            env.setdefault("ANTHROPIC_DEFAULT_HAIKU_MODEL", model)
        return env

    def _provider_config_for(self, provider_name: str, worker_id: Optional[str] = None) -> ProviderConfig:
        provider = self._provider_label(provider_name)
        base = self._config.provider_config(provider)
        if provider != "claude":
            if worker_id is None:
                return base
            override_model = self._worker_store.model_for(worker_id)
            if override_model:
                return replace(base, model=override_model)
            return base
        payload = self._claude_backend_payload(worker_id)
        default_model = str(payload.get("default_model", "")).strip()
        if worker_id is not None:
            override_model = self._worker_store.model_for(worker_id)
            if override_model:
                default_model = override_model
        return replace(base, model=default_model, env=self._claude_base_env(default_model, worker_id))

    def _build_provider_client(self, worker_id: str, provider_name: str, cwd: str) -> ProviderClient:
        provider = self._provider_label(provider_name)
        provider_config = self._provider_config_for(provider, worker_id)
        return build_provider_client(provider, provider_config, cwd)

    def _effective_model_for_worker(self, worker_id: str) -> str:
        provider_name = self._provider_name_for_worker(worker_id)
        if not provider_name:
            return ""
        return self._provider_config_for(provider_name, worker_id).model.strip()

    def _default_project_draft(self) -> Dict[str, str]:
        return {
            "provider": "codex",
            "backend": "openai",
            "model": "gpt-5.4",
            "mode": "auto",
            "session_id": "",
            "project_id": "",
            "cwd": "",
        }

    def _project_draft(self, chat_id: str) -> Dict[str, str]:
        with self._lock:
            draft = self._project_drafts.get(chat_id)
            if draft is None:
                draft = self._default_project_draft()
                self._project_drafts[chat_id] = draft
            return dict(draft)

    def _reset_project_draft(self, chat_id: str) -> Dict[str, str]:
        with self._lock:
            draft = self._default_project_draft()
            self._project_drafts[chat_id] = draft
            return dict(draft)

    def _merge_project_draft(self, chat_id: str, **updates: str) -> Dict[str, str]:
        with self._lock:
            draft = dict(self._project_drafts.get(chat_id) or self._default_project_draft())
            draft.update({key: value for key, value in updates.items() if value is not None})
            provider_name = draft.get("provider", "codex").strip().lower() or "codex"
            if provider_name == "codex":
                draft["backend"] = "openai"
                if not draft.get("model"):
                    draft["model"] = "gpt-5.4"
            elif provider_name == "claude":
                backend = draft.get("backend", "").strip().lower() or self._config.claude_default_backend.strip().lower() or "anthropic"
                draft["backend"] = backend
                if not draft.get("model"):
                    payload = self._config.claude_backends.get(backend, {})
                    if isinstance(payload, dict):
                        draft["model"] = str(payload.get("default_model", "")).strip()
            if provider_name != "codex":
                draft["session_id"] = ""
            self._project_drafts[chat_id] = draft
            return dict(draft)

    def _backend_choices_for_project_draft(self, chat_id: str) -> List[str]:
        draft = self._project_draft(chat_id)
        provider_name = draft.get("provider", "").strip().lower()
        if provider_name == "codex":
            return ["openai"]
        if provider_name != "claude":
            return []
        return sorted(
            name
            for name in self._config.claude_backends.keys()
            if str(name).strip().lower() != "custom"
        )

    def _model_choices_for_project_draft(self, chat_id: str) -> List[str]:
        draft = self._project_draft(chat_id)
        provider_name = draft.get("provider", "").strip().lower()
        if provider_name == "claude":
            backend = draft.get("backend", "").strip().lower() or self._config.claude_default_backend.strip().lower() or "anthropic"
            return model_choices(provider_name, backend)
        return model_choices(provider_name)

    def _recent_codex_session_choices(self, limit: int = 8) -> List[Tuple[str, str]]:
        locator = self._session_locator_for("codex")
        if locator is None:
            return []
        try:
            sessions = locator.list_recent(limit)
        except Exception:
            return []
        choices: List[Tuple[str, str]] = []
        for item in sessions:
            session_id = item.session_id.strip()
            if not session_id:
                continue
            label = session_id[:8]
            cwd = item.cwd.strip()
            thread_name = item.thread_name.strip()
            if cwd:
                label = f"{label} · {Path(cwd).name or cwd}"
            elif thread_name:
                label = f"{label} · {thread_name[:24]}"
            choices.append((label, session_id))
        return choices

    def _claude_backend_status(self, worker_id: str) -> Tuple[str, Optional[str]]:
        configured_backend = self._worker_store.backend_for(worker_id).strip().lower()
        if not configured_backend:
            return "", "当前群还没有设置 Claude provider。请先在 DM 控制台完成配置。"
        backend = self._claude_backend_name(worker_id)
        payload = self._claude_backend_payload(worker_id)
        if not payload:
            return backend, "Claude backend 配置不存在。"
        base_url = str(payload.get("base_url", "")).strip()
        auth_token = str(payload.get("auth_token", "")).strip()
        if backend == "anthropic":
            if not auth_token:
                return backend, "Claude Anthropic backend 还没有配置 auth_token。"
            return backend, None
        if not base_url:
            return backend, f"Claude backend {backend} 还没有配置 base_url。"
        if not auth_token:
            return backend, f"Claude backend {backend} 还没有配置 auth_token。"
        return backend, None

    def _model_choices_for_worker(self, worker_id: str) -> List[str]:
        provider = self._provider_label(self._provider_name_for_worker(worker_id))
        if provider == "claude":
            backend = self._worker_store.backend_for(worker_id).strip().lower() or self._claude_backend_name(worker_id)
            if not backend:
                return []
            return model_choices(provider, backend)
        return model_choices(provider)

    def _backend_choices_for_worker(self, worker_id: str) -> List[str]:
        provider = self._provider_label(self._provider_name_for_worker(worker_id))
        if provider == "codex":
            return ["openai"]
        if provider != "claude":
            return []
        return sorted(
            name
            for name in self._config.claude_backends.keys()
            if str(name).strip().lower() != "custom"
        )

    def _vendor_name_for_worker(self, worker_id: str) -> str:
        agent = self._provider_label(self._provider_name_for_worker(worker_id))
        if agent == "codex":
            return self._worker_store.backend_for(worker_id).strip().lower() or "openai"
        if agent == "claude":
            return self._worker_store.backend_for(worker_id).strip().lower() or self._claude_backend_name(worker_id)
        return ""

    def _session_locator_for(self, provider_name: str) -> Optional[SessionLocator]:
        return self._session_locators.get(self._provider_label(provider_name))

    def run(self) -> None:
        threading.Thread(target=self._command_loop, daemon=True).start()
        event_handler = (
            lark.EventDispatcherHandler.builder(
                self._config.feishu_encrypt_key,
                self._config.feishu_verification_token,
            )
            .register_p2_card_action_trigger(self._on_card_action_trigger)
            .register_p2_im_message_receive_v1(self._on_message_received)
            .build()
        )
        ws_client = lark.ws.Client(
            self._config.feishu_app_id,
            self._config.feishu_app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )
        LOG.info("Relay runtime is running.")
        ws_client.start()

    def _on_message_received(self, data: P2ImMessageReceiveV1) -> None:
        message = data.event.message
        sender = data.event.sender
        if message is None or sender is None or sender.sender_id is None or not message.chat_id:
            return
        if sender.sender_type != "user":
            return
        chat_type = message.chat_type or ""
        open_id = sender.sender_id.open_id or ""
        message_type = message.message_type or ""
        if not self._is_allowed_user(open_id):
            LOG.warning("Ignored message from unauthorized user: %s", open_id)
            return
        if message.message_id in self._known_message_ids:
            return
        self._known_message_ids.add(message.message_id)
        if message_type == "text":
            text = self._extract_text(message.content)
            if not text:
                return
            self._command_queue.put(
                {
                    "message_id": message.message_id,
                    "chat_id": message.chat_id,
                    "chat_type": chat_type,
                    "message_type": message_type,
                    "text": text,
                    "open_id": open_id,
                    "mentions": list(message.mentions or []),
                }
            )
            return
        if message_type == "image":
            image_key = self._extract_image_key(message.content)
            if not image_key:
                return
            self._command_queue.put(
                {
                    "message_id": message.message_id,
                    "chat_id": message.chat_id,
                    "chat_type": chat_type,
                    "message_type": message_type,
                    "image_key": image_key,
                    "open_id": open_id,
                    "mentions": list(message.mentions or []),
                }
            )
            return
        if message_type == "post":
            text, image_keys = self._extract_post_parts(message.content)
            if not text and not image_keys:
                return
            self._command_queue.put(
                {
                    "message_id": message.message_id,
                    "chat_id": message.chat_id,
                    "chat_type": chat_type,
                    "message_type": message_type,
                    "text": text,
                    "image_keys": image_keys,
                    "open_id": open_id,
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
        message_id = str(payload.get("message_id", ""))
        message_type = str(payload.get("message_type", "text"))
        text = str(payload.get("text", ""))
        mentions = list(payload.get("mentions", []))
        open_id = str(payload.get("open_id", ""))
        try:
            if message_type == "image":
                self._handle_image_message(
                    chat_id,
                    chat_type,
                    open_id,
                    message_id,
                    str(payload.get("image_key", "")),
                )
            elif message_type == "post":
                self._handle_post_message(
                    chat_id,
                    chat_type,
                    open_id,
                    message_id,
                    text,
                    mentions,
                    list(payload.get("image_keys", [])),
                )
            elif chat_type == "p2p":
                self._handle_dm_command(chat_id, text)
            else:
                self._handle_group_command(chat_id, chat_type, text, mentions, open_id)
        except Exception as exc:
            LOG.exception("Command failed")
            self._safe_send(chat_id, f"[poco] 执行失败\n{exc}")

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
        self._disable_stale_dm_cards(chat_id)
        command, arg = self._parse_poco_command(text)
        if command == "cardtest":
            ok = self._safe_send_card(chat_id, self._minimal_test_card())
            if not ok:
                self._safe_send(chat_id, "[poco] Failed to send test card. Check local logs.")
            return
        if command is None or command in {"help", "", "console", "project", "new-project", "new_project", "workers", "list", "sessions", "status", "stop", "reset", "remove"}:
            self._cards.send_dm_console_card(chat_id)
            return
        self._cards.send_dm_console_card(chat_id)

    def _handle_image_message(
        self,
        chat_id: str,
        chat_type: str,
        open_id: str,
        message_id: str,
        image_key: str,
    ) -> None:
        if not image_key:
            return
        if chat_type == "p2p":
            self._safe_send(chat_id, "[poco] 单聊是管理控制台，暂不处理图片。请在项目群里发送图片。")
            return
        worker_id = chat_id
        state_error = self._group_access_error_text(worker_id)
        if state_error:
            self._safe_send(chat_id, state_error)
            return
        self._safe_send(
            chat_id,
            "[poco] 请把图片和文字说明放在同一条飞书图文消息里发送。\n"
            "PoCo 不再使用“先发图、下一条再发文字”的模式。",
        )

    def _handle_post_message(
        self,
        chat_id: str,
        chat_type: str,
        open_id: str,
        message_id: str,
        text: str,
        mentions: list,
        image_keys: List[str],
    ) -> None:
        if chat_type == "p2p":
            if image_keys:
                self._safe_send(chat_id, "[poco] 单聊是管理控制台，暂不处理图片。请在项目群里发送图片。")
                return
            self._handle_dm_command(chat_id, text)
            return

        worker_id = chat_id
        state_error = self._group_access_error_text(worker_id)
        if state_error:
            self._safe_send(chat_id, state_error)
            return

        local_image_paths = [
            str(self._messenger.download_image(key, self._image_cache_dir(), message_id=message_id))
            for key in image_keys
            if key
        ]
        if not text.strip():
            self._delete_image_files(local_image_paths)
            self._safe_send(
                chat_id,
                "[poco] 请在同一条飞书图文消息里同时发送图片和文字说明。",
            )
            return

        self._handle_group_turn_input(
            worker_id,
            chat_id,
            chat_type,
            text,
            mentions,
            open_id,
            local_image_paths,
        )

    def _handle_group_command(
        self,
        chat_id: str,
        chat_type: str,
        text: str,
        mentions: list,
        open_id: str,
    ) -> None:
        worker_id = chat_id
        command, arg = self._parse_poco_command(text)
        stripped = text.strip().lower()
        if command == "cardtest":
            ok = self._safe_send_card(chat_id, self._minimal_test_card())
            if not ok:
                self._safe_send(chat_id, "[poco] Failed to send test card. Check local logs.")
            return
        if command is not None or stripped in {"poco", "/poco"}:
            self._safe_send(
                chat_id,
                "[poco] 项目管理和控制都在 DM 控制台完成。\n"
                "请去单聊发送 `poco`，这个群里直接聊天即可。",
            )
            return
        state_error = self._group_access_error_text(worker_id)
        if state_error:
            self._safe_send(chat_id, state_error)
            return

        self._handle_group_turn_input(worker_id, chat_id, chat_type, text, mentions, open_id)

    def _handle_group_turn_input(
        self,
        worker_id: str,
        chat_id: str,
        chat_type: str,
        text: str,
        mentions: list,
        open_id: str,
        immediate_image_paths: Optional[List[str]] = None,
    ) -> None:
        mode = self._worker_store.mode_for(worker_id)
        if mode == "mention":
            if not self._is_group_bot_mention(mentions):
                self._delete_image_files(immediate_image_paths or [])
                return
            text = self._strip_mentions(text, mentions)
            if not text:
                self._restore_pending_images(chat_id, open_id, immediate_image_paths or [])
                return
        elif mode == "auto":
            text = self._strip_mentions(text, mentions)
        else:
            self._delete_image_files(immediate_image_paths or [])
            self._safe_send(chat_id, f"[poco] 未知群模式：{mode}")
            return

        pending_images = self._pop_pending_images(chat_id, open_id)
        image_paths = pending_images + list(immediate_image_paths or [])
        with self._lock:
            if worker_id in self._active_by_worker:
                if image_paths:
                    self._restore_pending_images(chat_id, open_id, image_paths)
                self._safe_send(
                    chat_id,
                    "[poco] 上一轮还在处理中。\n"
                    "这条消息没有被执行。\n"
                    "请等待当前回复完成后再继续发送下一条消息。",
                )
                return

        self._turns.start_turn_for_worker(worker_id, chat_id, chat_type, text, image_paths)

    def _extract_text(self, raw: Optional[str]) -> str:
        if not raw:
            return ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip()
        return str(data.get("text", "")).strip()

    def _extract_image_key(self, raw: Optional[str]) -> str:
        if not raw:
            return ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        return str(data.get("image_key", "")).strip()

    def _extract_post_parts(self, raw: Optional[str]) -> Tuple[str, List[str]]:
        if not raw:
            return "", []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip(), []
        texts: List[str] = []
        image_keys: List[str] = []

        def walk(node: object) -> None:
            if isinstance(node, dict):
                tag = str(node.get("tag", "")).strip().lower()
                if tag == "img":
                    image_key = (
                        str(node.get("image_key", "")).strip()
                        or str(node.get("file_key", "")).strip()
                    )
                    if image_key:
                        image_keys.append(image_key)
                elif tag == "text":
                    value = str(node.get("text", "")).strip() or str(node.get("content", "")).strip()
                    if value:
                        texts.append(value)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
        normalized_text = "\n".join(part for part in texts if part).strip()
        deduped_images: List[str] = []
        seen: Set[str] = set()
        for key in image_keys:
            if key and key not in seen:
                seen.add(key)
                deduped_images.append(key)
        return normalized_text, deduped_images

    def _image_cache_dir(self) -> Path:
        IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return IMAGE_CACHE_DIR

    def _remember_pending_image(self, chat_id: str, open_id: str, path: str) -> int:
        key = (chat_id, open_id)
        with self._lock:
            bucket = self._pending_images.get(key)
            if bucket is None:
                bucket = PendingImages()
                self._pending_images[key] = bucket
            bucket.paths.append(path)
            bucket.updated_at = time.time()
            while len(bucket.paths) > 4:
                stale = bucket.paths.pop(0)
                self._delete_image_files([stale])
            return len(bucket.paths)

    def _pop_pending_images(self, chat_id: str, open_id: str) -> List[str]:
        if not open_id:
            return []
        key = (chat_id, open_id)
        with self._lock:
            bucket = self._pending_images.pop(key, None)
        if bucket is None:
            return []
        if time.time() - bucket.updated_at > 900:
            self._delete_image_files(bucket.paths)
            return []
        return [path for path in bucket.paths if path]

    def _restore_pending_images(self, chat_id: str, open_id: str, paths: List[str]) -> None:
        if not open_id or not paths:
            return
        key = (chat_id, open_id)
        with self._lock:
            bucket = self._pending_images.get(key)
            if bucket is None:
                bucket = PendingImages()
                self._pending_images[key] = bucket
            bucket.paths = paths + bucket.paths
            bucket.updated_at = time.time()

    def _clear_pending_images_for_chat(self, chat_id: str) -> None:
        with self._lock:
            doomed = [key for key in self._pending_images.keys() if key[0] == chat_id]
            paths: List[str] = []
            for key in doomed:
                bucket = self._pending_images.pop(key, None)
                if bucket is not None:
                    paths.extend(bucket.paths)
        self._delete_image_files(paths)

    @staticmethod
    def _delete_image_files(paths: List[str]) -> None:
        for path in paths:
            if not path:
                continue
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                LOG.exception("Failed to delete temporary image file: %s", path)

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

    def _group_access_error_text(self, worker_id: str) -> Optional[str]:
        if not self._worker_store.has_worker(worker_id):
            if self._store.get(worker_id):
                return (
                    "[poco] This group's local project state is missing or corrupted.\n"
                    "Please go back to the DM console and recreate or repair this project group."
                )
            return (
                "[poco] This group is not active yet.\n"
                "Create and manage project groups from the DM console.\n"
                "DM the bot with `poco`."
            )
        if not self._worker_store.enabled_for(worker_id):
            return (
                "[poco] This group is not active yet.\n"
                "Create and manage project groups from the DM console.\n"
                "DM the bot with `poco`."
            )
        return None

    def _ensure_worker(self, worker_id: str, chat_id: str, chat_type: str) -> WorkerRuntime:
        if not self._worker_store.has_worker(worker_id):
            raise RuntimeError(
                "当前群的本地项目状态缺失或损坏。请回到 DM 控制台重新创建或修复这个项目群。"
            )
        cwd = self._worker_store.cwd_for(worker_id)
        provider_name = self._provider_name_for_worker(worker_id)
        if not provider_name:
            raise RuntimeError("当前 worker 还没有配置 Agent。请先在 DM 控制台完成配置。")
        if not cwd:
            raise RuntimeError("当前 worker 还没有配置 Working directory。请先在 DM 控制台完成配置。")
        validation_error = self._validate_cwd(cwd)
        if validation_error:
            raise RuntimeError(f"当前 worker 的 cwd 无效：{validation_error}")
        with self._lock:
            existing = self._workers.get(worker_id)
            if existing is not None:
                return existing
            client = self._build_provider_client(worker_id, provider_name, cwd)
            client.start()
            worker = WorkerRuntime(
                worker_id=worker_id,
                chat_id=chat_id,
                chat_type=chat_type,
                cwd=cwd,
                provider_name=provider_name,
                client=client,
            )
            self._workers[worker_id] = worker
        threading.Thread(
            target=self._turns.notification_loop,
            args=(worker_id, client),
            daemon=True,
            name=f"poco-worker-{worker_id[:8]}",
        ).start()
        return worker

    def _attach_session(self, worker_id: str, session_id: str, *, allow_create: bool) -> SessionMeta:
        session_id = session_id.strip()
        if not session_id:
            raise RuntimeError("session_id 不能为空。")
        try:
            uuid.UUID(session_id)
        except ValueError as exc:
            raise RuntimeError("当前只支持用 session UUID 进行 attach。") from exc
        self._worker_store.ensure_worker(worker_id)
        provider_name = self._provider_name_for_worker(worker_id)
        if not provider_name:
            raise RuntimeError("当前 worker 还没有配置 Agent。请先在 DM 控制台完成配置。")
        with self._lock:
            session = self._active_by_worker.get(worker_id)
            if session is not None:
                raise RuntimeError("该 worker 当前还有一轮在进行中，请先等待完成。")
            worker = self._workers.pop(worker_id, None)
        if worker is not None:
            worker.client.close()
        locator = self._session_locator_for(provider_name)
        if locator is None:
            raise RuntimeError(f"provider {provider_name} 目前还不支持 attach 现有 session。")
        meta = locator.get(session_id) or SessionMeta(provider=provider_name, session_id=session_id, cwd="")
        if meta.cwd:
            validation_error = self._validate_cwd(meta.cwd)
            if validation_error:
                raise RuntimeError(f"session 的 cwd 无效：{validation_error}")
            self._worker_store.set_cwd(worker_id, meta.cwd)
        elif not self._worker_store.cwd_for(worker_id):
            raise RuntimeError("未找到该 session 的 cwd，请先在 DM 控制台手动填写 Working Dir。")
        if allow_create:
            self._worker_store.ensure_worker(worker_id)
        self._store.set(worker_id, session_id)
        return meta

    def _get_worker(self, worker_id: str) -> Optional[WorkerRuntime]:
        with self._lock:
            return self._workers.get(worker_id)

    def _remove_worker(self, worker_id: str) -> None:
        provider_name = self._provider_name_for_worker(worker_id)
        thread_id = self._store.get(worker_id)
        with self._lock:
            session = self._active_by_worker.get(worker_id)
            if session is not None:
                raise RuntimeError("该 worker 当前还有一轮在进行中，请先等待完成。")
            worker = self._workers.pop(worker_id, None)
        self._store.clear(worker_id)
        self._worker_store.remove(worker_id)
        if thread_id and provider_name:
            locator = self._session_locator_for(provider_name)
            if locator is not None:
                try:
                    locator.delete(thread_id)
                except Exception:
                    LOG.warning("Failed to delete local session %s for worker %s", thread_id, worker_id)
        if worker is not None:
            worker.client.close()

    def _recycle_worker_runtime(self, worker_id: str, *, reason: str) -> Optional[str]:
        with self._lock:
            session = self._active_by_worker.get(worker_id)
            if session is not None:
                return reason
            worker = self._workers.pop(worker_id, None)
            self._queued_by_worker.pop(worker_id, None)
        self._store.clear(worker_id)
        if worker is not None:
            worker.client.close()
        return None

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
            return "[poco] 当前还没有项目 worker。把 bot 拉进项目群后，在群里 @bot 发消息即可自动创建。"
        lines = ["[poco] 当前 workers："]
        with self._lock:
            active_by_worker = {key: session.turn_id for key, session in self._active_by_worker.items()}
            known_workers = set(self._workers)
        for worker_id in known_worker_ids:
            alias = alias_items.get(worker_id, "")
            thread_id = thread_items.get(worker_id, "(none)")
            running = worker_id in known_workers
            active_turn = active_by_worker.get(worker_id, "(none)")
            provider_name = self._provider_name_for_worker(worker_id)
            model = self._effective_model_for_worker(worker_id)
            backend = self._worker_store.backend_for(worker_id) if provider_name == "claude" else ""
            enabled = self._worker_store.enabled_for(worker_id)
            mode = self._worker_store.mode_for(worker_id)
            cwd = self._worker_store.cwd_for(worker_id)
            lines.append(
                f"- {alias or worker_id}\n"
                f"  worker_id={worker_id}\n"
                f"  provider={provider_name or '(unset)'}\n"
                f"  backend={backend or '(n/a)'}\n"
                f"  model={model or '(unset)'}\n"
                f"  enabled={enabled}\n"
                f"  mode={mode}\n"
                f"  cwd={cwd or '(unset)'}\n"
                f"  thread_id={thread_id}\n"
                f"  process_running={running}\n"
                f"  active_turn={active_turn}"
            )
        return "\n".join(lines)

    def _sessions_text(self, provider_name: str, limit: int) -> str:
        if not provider_name:
            lines = ["[poco] 可用 provider sessions："]
            for current_provider in ("codex", "claude"):
                locator = self._session_locator_for(current_provider)
                if locator is None:
                    continue
                sessions = locator.list_recent(limit)
                lines.append(f"- {current_provider}: {len(sessions)}")
            return "\n".join(lines)
        locator = self._session_locator_for(provider_name)
        if locator is None:
            return f"[poco] provider {provider_name} 目前还不支持本地 session 发现。"
        sessions = locator.list_recent(limit)
        if not sessions:
            return f"[poco] 当前没有找到可用的本地 {provider_name} sessions。"
        lines = [f"[poco] 最近 {len(sessions)} 个可接管的 {provider_name} sessions："]
        for item in sessions:
            title = item.thread_name or "(untitled)"
            lines.append(
                f"- {item.session_id}\n"
                f"  provider={item.provider}\n"
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
            return f"[poco] worker {target} 不存在。"
        thread_id = self._store.get(worker_id)
        worker = self._get_worker(worker_id)
        with self._lock:
            active = self._active_by_worker.get(worker_id)
        active_turn = active.turn_id if active is not None else "(none)"
        alias = self._worker_store.alias_for(worker_id)
        provider_name = self._provider_name_for_worker(worker_id)
        model = self._effective_model_for_worker(worker_id)
        backend = self._worker_store.backend_for(worker_id) if provider_name == "claude" else ""
        enabled = self._worker_store.enabled_for(worker_id)
        mode = self._worker_store.mode_for(worker_id)
        cwd = self._worker_store.cwd_for(worker_id)
        if thread_id is None and worker is None and active is None and not alias and not enabled and not cwd:
            return f"[poco] worker {worker_id} 不存在。"
        return (
            f"[poco] worker: {alias or worker_id}\n"
            f"worker_id: {worker_id}\n"
            f"provider: {provider_name or '(unset)'}\n"
            f"backend: {backend or '(n/a)'}\n"
            f"model: {model or '(unset)'}\n"
            f"enabled: {enabled}\n"
            f"mode: {mode}\n"
            f"cwd: {cwd or '(unset)'}\n"
            f"thread_id: {thread_id or '(none)'}\n"
            f"process_running: {worker is not None}\n"
            f"active_turn: {active_turn}"
        )

    @staticmethod
    def _looks_like_project_request(text: str) -> bool:
        normalized = " ".join(text.strip().lower().split())
        if not normalized:
            return False
        triggers = (
            "new project",
            "create project",
            "start project",
            "project please",
            "新项目",
            "新建项目",
            "创建项目",
            "起一个项目",
            "开一个项目",
            "我要起一个项目",
            "我要新建一个项目",
        )
        return any(trigger in normalized for trigger in triggers)

    def _create_project_group_from_dm(
        self,
        dm_chat_id: str,
        requester_open_id: str,
        project_id: str,
        cwd: str,
        *,
        provider_name: str,
        backend: str,
        model: str,
        mode: str,
        attach_session_id: str = "",
    ) -> str:
        group_chat_id = self._messenger.create_project_group(project_id, requester_open_id)
        worker_id = group_chat_id
        self._worker_store.ensure_worker(worker_id)
        self._worker_store.set_provider(worker_id, provider_name)
        self._worker_store.set_backend(worker_id, backend)
        self._worker_store.set_model(worker_id, model)
        self._worker_store.set_mode(worker_id, mode)
        self._worker_store.set_alias(worker_id, project_id)
        self._worker_store.set_cwd(worker_id, cwd)
        self._worker_store.set_enabled(worker_id, True)
        self._store.clear(worker_id)
        if attach_session_id:
            self._attach_session(worker_id, attach_session_id, allow_create=False)
        self._safe_send_card(
            group_chat_id,
            self._cards.project_ready_card(
                project_id=project_id,
                provider_name=provider_name,
                backend=backend,
                model=model,
                mode=mode,
                cwd=cwd,
            ),
        )
        self._reset_project_draft(dm_chat_id)
        return group_chat_id

    def _safe_send(self, chat_id: str, text: str) -> None:
        try:
            self._messenger.send_text(chat_id, text)
        except Exception:
            LOG.exception("Failed to send Feishu message")

    def _safe_update_text(self, message_id: str, text: str) -> bool:
        try:
            self._messenger.update_text(message_id, text)
            return True
        except Exception:
            LOG.exception("Failed to update Feishu message")
            return False

    def _safe_send_card(self, chat_id: str, card: dict) -> bool:
        try:
            self._messenger.create_card(chat_id, card)
            return True
        except Exception:
            LOG.exception("Failed to send Feishu card")
            return False

    def _safe_send_dm_card(self, chat_id: str, card: dict) -> bool:
        try:
            sent = self._messenger.create_card(chat_id, card)
        except Exception:
            LOG.exception("Failed to send Feishu DM card")
            return False
        self._disable_stale_dm_cards(chat_id, keep_message_id=sent.message_id)
        with self._lock:
            self._dm_active_card_ids[chat_id] = [sent.message_id]
        return True

    def _disable_stale_dm_cards(self, chat_id: str, *, keep_message_id: str = "") -> None:
        with self._lock:
            stale_ids = list(self._dm_active_card_ids.get(chat_id, []))
        if not stale_ids:
            return
        disabled_card = self._cards.inactive_dm_card()
        for message_id in stale_ids:
            if keep_message_id and message_id == keep_message_id:
                continue
            try:
                self._messenger.update_card(message_id, disabled_card)
            except Exception:
                LOG.exception("Failed to disable stale DM card %s", message_id)
        with self._lock:
            if keep_message_id:
                self._dm_active_card_ids[chat_id] = [keep_message_id]
            else:
                self._dm_active_card_ids.pop(chat_id, None)

    @staticmethod
    def _card_permission_required_text() -> str:
        return (
            "[poco] 当前卡片发送失败。\n"
            "这通常是卡片结构不合法或当前配置不兼容，请查看本地 poco.log 后重试。"
        )

    def _card_button(
        self,
        text: str,
        action_name: str,
        button_type: str = "default",
        *,
        selected: str = "",
        name: str = "",
        form_action_type: str = "",
        enable_callback: bool = True,
    ) -> dict:
        value = {"action": action_name}
        if selected:
            value["selected"] = selected
        raw_id = "|".join([action_name, selected, name, form_action_type, text])
        digest = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:8]
        prefix = "".join(ch if ch.isalnum() else "_" for ch in action_name.lower())[:11] or "btn"
        payload = {
            "tag": "button",
            "element_id": f"{prefix}_{digest}",
            "text": {"tag": "plain_text", "content": text},
            "type": button_type,
        }
        if enable_callback:
            payload["value"] = value
            payload["behaviors"] = [
                {
                    "type": "callback",
                    "value": value,
                }
            ]
        elif selected:
            payload["value"] = value
        if name:
            payload["name"] = name
        if form_action_type:
            payload["form_action_type"] = form_action_type
        return payload

    @staticmethod
    def _card_choice_columns(buttons: List[dict]) -> dict:
        columns: List[dict] = []
        for idx, button in enumerate(buttons, start=1):
            columns.append(
                {
                    "tag": "column",
                    "width": "132px",
                    "elements": [button],
                    "element_id": f"col_{idx}",
                }
            )
        return {
            "tag": "column_set",
            "flex_mode": "flow",
            "horizontal_spacing": "8px",
            "columns": columns,
        }

    @staticmethod
    def _card_label_markdown(label: str, *, subtle: bool = False) -> dict:
        color = "grey-650" if subtle else "orange-700"
        text = label
        if not subtle:
            stripped = label.rstrip()
            if stripped.endswith(" *"):
                core = stripped[:-2].rstrip()
                text = f"**{core}** *"
            else:
                text = f"**{stripped}**"
        return {
            "tag": "markdown",
            "content": f"<font color='{color}'>{text}</font>",
        }

    @staticmethod
    def _card_labeled_row(label: str, content: dict) -> dict:
        return {
            "tag": "column_set",
            "flex_mode": "none",
            "horizontal_spacing": "8px",
            "columns": [
                {
                    "tag": "column",
                    "width": "150px",
                    "vertical_align": "center",
                    "elements": [RelayApp._card_label_markdown(label)],
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "vertical_align": "center",
                    "elements": [content],
                },
            ],
        }

    def _card_choice_group(
        self,
        title: str,
        current_value: str,
        action_name: str,
        choices: List[tuple[str, str]],
    ) -> List[dict]:
        buttons: List[dict] = []
        current = current_value.strip().lower()
        for label, value in choices:
            selected = value.strip().lower()
            button_type = "primary" if current and selected == current else "default"
            buttons.append(
                self._card_button(
                    label,
                    action_name,
                    button_type,
                    selected=value,
                )
            )
        return [self._card_labeled_row(title, self._card_choice_columns(buttons))]

    def _card_select(
        self,
        title: str,
        action_name: str,
        current_value: str,
        choices: List[tuple[str, str]],
        *,
        placeholder: str,
    ) -> List[dict]:
        options: List[dict] = []
        initial_option = ""
        for label, value in choices:
            options.append(
                {
                    "text": {"tag": "plain_text", "content": label},
                    "value": value,
                }
            )
            if value == current_value:
                initial_option = value
        payload = {
            "tag": "select_static",
            "element_id": self._card_button(
                title,
                action_name,
            )["element_id"].replace("btn_", "sel_", 1),
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "options": options,
            "value": {"action": action_name},
            "behaviors": [
                {
                    "type": "callback",
                    "value": {"action": action_name},
                }
            ],
        }
        if initial_option:
            payload["initial_option"] = initial_option
        return [self._card_labeled_row(title, payload)]

    @staticmethod
    def _card_selectable_summary_row(label: str, value: str) -> List[dict]:
        return [
            RelayApp._card_labeled_row(
                label,
                {
                    "tag": "markdown",
                    "content": value or "-",
                },
            )
        ]

    @staticmethod
    def _reply_mode_label(mode: str) -> str:
        normalized = mode.strip().lower()
        if normalized == "mention":
            return "mention only"
        if normalized == "auto":
            return "all"
        return normalized or "mention only"

    def _enable_worker(self, worker_id: str) -> Optional[str]:
        return self._cards.enable_worker(worker_id)

    def _reset_worker_config(self, worker_id: str) -> None:
        self._cards.reset_worker_config(worker_id)

    def _setup_card(
        self,
        chat_id: str,
        worker_id: str,
        *,
        notice: str = "",
        form_alias: str = "",
        form_cwd: str = "",
    ) -> dict:
        return self._cards.setup_card(
            chat_id,
            worker_id,
            notice=notice,
            form_alias=form_alias,
            form_cwd=form_cwd,
        )

    def _minimal_test_card(self, notice: str = "") -> dict:
        return self._cards.minimal_test_card(notice)

    @staticmethod
    def _status_card(title: str, body: str, *, template: str = "red") -> dict:
        return SetupCardController.status_card(title, body, template=template)

    def _send_setup_card(self, chat_id: str, worker_id: str, *, notice: str = "") -> None:
        self._cards.send_setup_card(chat_id, worker_id, notice=notice)

    def _project_launch_card(
        self,
        chat_id: str,
        *,
        notice: str = "",
        form_project_id: str = "",
        form_cwd: str = "",
        form_session_id: str = "",
    ) -> dict:
        return self._cards.project_launch_card(
            chat_id,
            notice=notice,
            form_project_id=form_project_id,
            form_cwd=form_cwd,
            form_session_id=form_session_id,
        )

    def _send_project_launch_card(self, chat_id: str, *, notice: str = "") -> None:
        self._cards.send_project_launch_card(chat_id, notice=notice)

    def _on_card_action_trigger(self, data):
        return self._cards.on_card_action_trigger(data)

    @staticmethod
    def _group_help_text() -> str:
        return SetupCardController.group_help_text()

    @staticmethod
    def _dm_help_text() -> str:
        return SetupCardController.dm_help_text()
