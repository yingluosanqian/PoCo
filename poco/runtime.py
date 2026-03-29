import logging
import threading
import time
from collections import deque
from typing import Any, Dict, Optional

from .bridge import AppConfig, BridgeApp
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


class BridgeRunner:
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
                target=self._run_bridge,
                args=(app_config,),
                daemon=True,
                name="poco-bridge",
            )
            self._thread = thread
            self._started_at = time.time()
            thread.start()
            return True

    def _run_bridge(self, config: AppConfig) -> None:
        try:
            bridge = BridgeApp(config)
            bridge.run()
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
            LOG.exception("Bridge runtime crashed")


def build_app_config(config: Dict[str, Any]) -> AppConfig:
    feishu = config["feishu"]
    codex = config["codex"]
    bridge = config["bridge"]
    return AppConfig(
        feishu_app_id=feishu["app_id"],
        feishu_app_secret=feishu["app_secret"],
        feishu_encrypt_key=feishu["encrypt_key"],
        feishu_verification_token=feishu["verification_token"],
        codex_bin=codex["bin"],
        codex_app_server_args=codex["app_server_args"],
        codex_model=codex["model"],
        codex_approval_policy=codex["approval_policy"],
        codex_sandbox=codex["sandbox"],
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
        self.bridge = BridgeRunner()

    def load_config(self) -> Dict[str, Any]:
        return self.store.load()

    def save_config(self, config: Dict[str, Any]) -> None:
        self.store.save(config)

    def masked_config(self) -> Dict[str, Any]:
        return self.store.masked()

    def bridge_status(self) -> Dict[str, Any]:
        return self.bridge.status()

    def set_config_value(self, key: str, raw_value: str) -> tuple[str, Any]:
        path = normalize_config_key(key)
        if path not in INPUT_IDS and path not in {"feishu.allow_all_users"}:
            raise ValueError(f"未知配置项：{key}")
        config = self.load_config()
        value = parse_config_value(path, raw_value)
        set_nested(config, path, value)
        self.save_config(config)
        return path, value

    def start_bridge(self) -> bool:
        config = self.load_config()
        if not config_ready(config):
            raise ValueError("配置还不完整，至少需要 Feishu App ID 和 App Secret。")
        return self.bridge.start(config)
