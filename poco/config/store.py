import json
import logging
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict


LOG = logging.getLogger("poco")
CONFIG_DIR = Path.home() / ".config" / "poco"
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_DIR = Path.home() / ".local" / "state" / "poco"
THREAD_STATE_PATH = STATE_DIR / "threads.json"
WORKER_STATE_PATH = STATE_DIR / "workers.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "feishu": {
        "app_id": "",
        "app_secret": "",
        "encrypt_key": "",
        "verification_token": "",
        "allowed_open_ids": [],
        "allow_all_users": True,
    },
    "codex": {
        "bin": "codex",
        "app_server_args": "",
        "model": "",
        "approval_policy": "never",
        "sandbox": "danger-full-access",
    },
    "bridge": {
        "message_limit": 1400,
        "live_update_initial_seconds": 1,
        "live_update_max_seconds": 8,
        "max_message_edits": 18,
    },
    "ui": {
        "language": "en",
    },
}

INPUT_IDS = {
    "feishu.app_id": "feishu_app_id",
    "feishu.app_secret": "feishu_app_secret",
    "feishu.encrypt_key": "feishu_encrypt_key",
    "feishu.verification_token": "feishu_verification_token",
    "feishu.allowed_open_ids": "feishu_allowed_open_ids",
    "codex.bin": "codex_bin",
    "codex.app_server_args": "codex_app_server_args",
    "codex.model": "codex_model",
    "codex.approval_policy": "codex_approval_policy",
    "codex.sandbox": "codex_sandbox",
    "bridge.message_limit": "bridge_message_limit",
    "bridge.live_update_initial_seconds": "bridge_live_update_initial_seconds",
    "bridge.live_update_max_seconds": "bridge_live_update_max_seconds",
    "bridge.max_message_edits": "bridge_max_message_edits",
    "ui.language": "ui_language",
}

CONFIG_KEY_ALIASES = {
    "app_id": "feishu.app_id",
    "app_secret": "feishu.app_secret",
    "encrypt_key": "feishu.encrypt_key",
    "verification_token": "feishu.verification_token",
    "allowed_open_ids": "feishu.allowed_open_ids",
    "allow_all_users": "feishu.allow_all_users",
    "codex_bin": "codex.bin",
    "app_server_args": "codex.app_server_args",
    "model": "codex.model",
    "approval_policy": "codex.approval_policy",
    "sandbox": "codex.sandbox",
    "message_limit": "bridge.message_limit",
    "live_update_initial_seconds": "bridge.live_update_initial_seconds",
    "live_update_max_seconds": "bridge.live_update_max_seconds",
    "max_message_edits": "bridge.max_message_edits",
    "language": "ui.language",
}


def deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def mask_secret(value: str) -> str:
    if len(value) <= 6:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 6) + value[-3:]


def config_ready(config: Dict[str, Any]) -> bool:
    feishu = config["feishu"]
    return bool(feishu["app_id"] and feishu["app_secret"])


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def set_nested(config: Dict[str, Any], path: str, value: Any) -> Dict[str, Any]:
    parts = path.split(".")
    current = config
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value
    return config


def get_nested(config: Dict[str, Any], path: str) -> Any:
    value: Any = config
    for part in path.split("."):
        value = value[part]
    return value


def normalize_config_key(key: str) -> str:
    normalized = key.strip()
    if not normalized:
        raise ValueError("配置项不能为空。")
    return CONFIG_KEY_ALIASES.get(normalized, normalized)


def parse_config_value(path: str, raw: str) -> Any:
    value = raw.strip()
    if path == "feishu.allowed_open_ids":
        return [item.strip() for item in value.split(",") if item.strip()]
    if path == "feishu.allow_all_users":
        lowered = value.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"{path} 必须是 true/false。")
    if path.startswith("bridge."):
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{path} 必须是整数。") from exc
    return value


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def load(self) -> Dict[str, Any]:
        with self._lock:
            if not self._path.exists():
                return deepcopy(DEFAULT_CONFIG)
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return deep_merge(DEFAULT_CONFIG, raw)

    def save(self, config: Dict[str, Any]) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(config, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            try:
                os.chmod(self._path, 0o600)
            except Exception:
                LOG.exception("Failed to chmod config file")

    def masked(self) -> Dict[str, Any]:
        config = self.load()
        masked = deepcopy(config)
        if masked["feishu"]["app_secret"]:
            masked["feishu"]["app_secret"] = mask_secret(masked["feishu"]["app_secret"])
        return masked
