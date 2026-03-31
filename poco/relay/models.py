"""Relay dataclasses shared across transport and orchestration layers."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set

from ..providers import ProviderClient, ProviderConfig


@dataclass
class AppConfig:
    feishu_app_id: str
    feishu_app_secret: str
    feishu_encrypt_key: str
    feishu_verification_token: str
    feishu_card_test_template_id: str
    codex: ProviderConfig
    cursor: ProviderConfig
    claude: ProviderConfig
    claude_default_backend: str
    claude_backends: Dict[str, Dict[str, object]]
    message_limit: int
    live_update_initial_seconds: int
    live_update_max_seconds: int
    max_message_edits: int
    allowed_open_ids: Set[str]
    allow_all_users: bool
    thread_state_path: str
    worker_state_path: str

    def provider_config(self, provider_name: str) -> ProviderConfig:
        provider = provider_name.strip().lower()
        if provider == "codex":
            return self.codex
        if provider == "cursor":
            return self.cursor
        if provider == "claude":
            return self.claude
        raise ValueError(f"Unsupported provider: {provider_name}")


@dataclass
class SentMessage:
    message_id: str
    chat_id: str


@dataclass
class LiveMessage:
    sent: SentMessage
    edit_count: int = 0
    last_text: str = ""
    card_id: str = ""
    element_id: str = ""
    stream_uuid: str = ""
    stream_sequence: int = 0
    streaming_mode: bool = False
    card_broken: bool = False


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
    stopped: bool = False
    started_at: float = field(default_factory=time.time)
    next_delay: int = 1
    next_update_at: float = field(default_factory=time.time)
    updated_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    image_paths: List[str] = field(default_factory=list)

    def notify(self) -> None:
        self.updated_event.set()


@dataclass
class WorkerRuntime:
    worker_id: str
    chat_id: str
    chat_type: str
    cwd: str
    provider_name: str
    client: ProviderClient
    created_at: float = field(default_factory=time.time)


@dataclass
class QueuedMessage:
    worker_id: str
    chat_id: str
    chat_type: str
    text: str


@dataclass
class PendingImages:
    paths: List[str] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)
