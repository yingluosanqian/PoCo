import logging
import threading
import time
from collections import deque
from typing import Any, Dict, Optional

from .relay import AppConfig, ProviderConfig, RelayApp
from .config import (
    INPUT_IDS,
    THREAD_STATE_PATH,
    WORKER_STATE_PATH,
    ConfigStore,
    config_ready,
    normalize_config_key,
    parse_config_value,
    set_nested,
)


LOG = logging.getLogger("poco")


class RingLogHandler(logging.Handler):
    def __init__(self, limit: int = 500) -> None:
        super().__init__()
        self._records = deque(maxlen=limit)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        payload = {
            "time": int(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        with self._lock:
            self._records.append(payload)

    def snapshot(self, limit: int = 500) -> list[dict]:
        with self._lock:
            return list(self._records)[-limit:]


class RelayRunner:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._last_error: str = ""
        self._started_at: Optional[float] = None
        self._lock = threading.Lock()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "running": self._thread is not None and self._thread.is_alive(),
                "started_at": self._started_at,
                "last_error": self._last_error,
            }

    def start(self, config: Dict[str, Any]) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._last_error = ""
            app_config = build_app_config(config)
            thread = threading.Thread(
                target=self._run_relay,
                args=(app_config,),
                daemon=True,
                name="poco-relay",
            )
            self._thread = thread
            self._started_at = time.time()
            thread.start()
            return True

    def _run_relay(self, config: AppConfig) -> None:
        try:
            relay = RelayApp(config)
            relay.run()
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
            LOG.exception("Relay runtime crashed")


def build_app_config(config: Dict[str, Any]) -> AppConfig:
    feishu = config["feishu"]
    codex = config["codex"]
    claude = config.get("claude", {})
    bridge = config["bridge"]
    return AppConfig(
        feishu_app_id=feishu["app_id"],
        feishu_app_secret=feishu["app_secret"],
        feishu_encrypt_key=feishu["encrypt_key"],
        feishu_verification_token=feishu["verification_token"],
        feishu_card_test_template_id=str(feishu.get("card_test_template_id", "")),
        codex=ProviderConfig(
            name="codex",
            bin=codex["bin"],
            app_server_args=codex["app_server_args"],
            model=codex["model"],
            approval_policy=codex["approval_policy"],
            sandbox=codex["sandbox"],
            reasoning_effort=str(codex.get("reasoning_effort", "")),
        ),
        claude=ProviderConfig(
            name="claude",
            bin=str(claude.get("bin", "claude")),
            app_server_args=str(claude.get("app_server_args", "")),
            model="",
            approval_policy=str(claude.get("approval_policy", "")),
            sandbox=str(claude.get("sandbox", "")),
            reasoning_effort="",
        ),
        claude_default_backend=str(claude.get("default_backend", "anthropic")),
        claude_backends=dict(claude.get("backends", {})),
        message_limit=int(bridge["message_limit"]),
        live_update_initial_seconds=int(bridge["live_update_initial_seconds"]),
        live_update_max_seconds=int(bridge["live_update_max_seconds"]),
        max_message_edits=int(bridge["max_message_edits"]),
        allowed_open_ids=set(feishu["allowed_open_ids"]),
        allow_all_users=bool(feishu["allow_all_users"]),
        thread_state_path=str(THREAD_STATE_PATH),
        worker_state_path=str(WORKER_STATE_PATH),
    )


class PoCoService:
    def __init__(self, store: ConfigStore, logs: RingLogHandler) -> None:
        self.store = store
        self.logs = logs
        self.relay = RelayRunner()

    def load_config(self) -> Dict[str, Any]:
        return self.store.load()

    def save_config(self, config: Dict[str, Any]) -> None:
        self.store.save(config)

    def masked_config(self) -> Dict[str, Any]:
        return self.store.masked()

    def relay_status(self) -> Dict[str, Any]:
        return self.relay.status()

    def set_config_value(self, key: str, raw_value: str) -> tuple[str, Any]:
        path = normalize_config_key(key)
        allowed_dynamic = (
            path == "feishu.allow_all_users"
            or path == "claude.default_backend"
            or path.startswith("claude.backends.")
        )
        if path not in INPUT_IDS and not allowed_dynamic:
            raise ValueError(f"未知配置项：{key}")
        config = self.load_config()
        value = parse_config_value(path, raw_value)
        set_nested(config, path, value)
        self.save_config(config)
        return path, value

    def start_relay(self) -> bool:
        config = self.load_config()
        if not config_ready(config):
            raise ValueError("配置还不完整，至少需要 Feishu App ID 和 App Secret。")
        return self.relay.start(config)
