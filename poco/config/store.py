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
LOG_PATH = STATE_DIR / "poco.log"

DEFAULT_CONFIG: Dict[str, Any] = {
    "feishu": {
        "app_id": "",
        "app_secret": "",
        "encrypt_key": "",
        "verification_token": "",
        "card_test_template_id": "",
        "allowed_open_ids": [],
        "allow_all_users": True,
    },
    "codex": {
        "bin": "codex",
        "app_server_args": "",
        "model": "gpt-5.4",
        "reasoning_effort": "high",
        "approval_policy": "never",
        "sandbox": "danger-full-access",
    },
    "claude": {
        "bin": "claude",
        "app_server_args": "",
        "approval_policy": "",
        "sandbox": "",
        "default_backend": "anthropic",
        "backends": {
            "anthropic": {
                "base_url": "https://api.anthropic.com",
                "auth_token": "",
                "default_model": "claude-sonnet-4-6",
                "extra_env": {},
            },
            "deepseek": {
                "base_url": "https://api.deepseek.com",
                "auth_token": "",
                "default_model": "deepseek-chat",
                "extra_env": {},
            },
            "kimi": {
                "base_url": "https://api.moonshot.ai/v1",
                "auth_token": "",
                "default_model": "kimi-k2.5",
                "extra_env": {},
            },
            "minimax": {
                "base_url": "https://api.minimaxi.com/anthropic",
                "auth_token": "",
                "default_model": "MiniMax-M2.7",
                "extra_env": {
                    "API_TIMEOUT_MS": "3000000",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                },
            },
        },
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
    "feishu.card_test_template_id": "feishu_card_test_template_id",
    "feishu.allowed_open_ids": "feishu_allowed_open_ids",
    "codex.bin": "codex_bin",
    "codex.app_server_args": "codex_app_server_args",
    "codex.model": "codex_model",
    "codex.reasoning_effort": "codex_reasoning_effort",
    "codex.approval_policy": "codex_approval_policy",
    "codex.sandbox": "codex_sandbox",
    "claude.bin": "claude_bin",
    "claude.app_server_args": "claude_app_server_args",
    "claude.approval_policy": "claude_approval_policy",
    "claude.sandbox": "claude_sandbox",
    "claude.default_backend": "claude_default_backend",
    "claude.backends.anthropic.base_url": "claude_backend_anthropic_base_url",
    "claude.backends.anthropic.auth_token": "claude_backend_anthropic_auth_token",
    "claude.backends.anthropic.default_model": "claude_backend_anthropic_default_model",
    "claude.backends.anthropic.extra_env": "claude_backend_anthropic_extra_env",
    "claude.backends.minimax.base_url": "claude_backend_minimax_base_url",
    "claude.backends.minimax.auth_token": "claude_backend_minimax_auth_token",
    "claude.backends.minimax.default_model": "claude_backend_minimax_default_model",
    "claude.backends.minimax.extra_env": "claude_backend_minimax_extra_env",
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
    "card_test_template_id": "feishu.card_test_template_id",
    "allowed_open_ids": "feishu.allowed_open_ids",
    "allow_all_users": "feishu.allow_all_users",
    "codex_bin": "codex.bin",
    "app_server_args": "codex.app_server_args",
    "model": "codex.model",
    "reasoning_effort": "codex.reasoning_effort",
    "approval_policy": "codex.approval_policy",
    "sandbox": "codex.sandbox",
    "claude_bin": "claude.bin",
    "claude_app_server_args": "claude.app_server_args",
    "claude_approval_policy": "claude.approval_policy",
    "claude_sandbox": "claude.sandbox",
    "claude_default_backend": "claude.default_backend",
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


def normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Backfills durable defaults that older saved configs may miss.

    This keeps new built-in defaults visible in the TUI even when an older
    config file explicitly saved empty strings before those defaults existed.

    Args:
        config: The merged config dictionary loaded from disk.

    Returns:
        The normalized config dictionary.
    """
    codex = config.setdefault("codex", {})
    if not str(codex.get("model", "")).strip():
        codex["model"] = DEFAULT_CONFIG["codex"]["model"]
    if not str(codex.get("reasoning_effort", "")).strip():
        codex["reasoning_effort"] = DEFAULT_CONFIG["codex"]["reasoning_effort"]

    claude = config.setdefault("claude", {})
    if not str(claude.get("default_backend", "")).strip():
        claude["default_backend"] = DEFAULT_CONFIG["claude"]["default_backend"]

    configured_backends = claude.setdefault("backends", {})
    default_backends = DEFAULT_CONFIG["claude"]["backends"]
    for backend_name, backend_defaults in default_backends.items():
        backend = configured_backends.setdefault(backend_name, deepcopy(backend_defaults))
        if not str(backend.get("base_url", "")).strip():
            backend["base_url"] = backend_defaults["base_url"]
        if not str(backend.get("default_model", "")).strip():
            backend["default_model"] = backend_defaults["default_model"]
        if not isinstance(backend.get("extra_env"), dict):
            backend["extra_env"] = deepcopy(backend_defaults.get("extra_env", {}))

    return config


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
    if path.endswith(".extra_env"):
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} 必须是 JSON 对象。") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{path} 必须是 JSON 对象。")
        return {str(k): str(v) for k, v in parsed.items()}
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
            return normalize_config(deep_merge(DEFAULT_CONFIG, raw))

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
        if masked["feishu"]["verification_token"]:
            masked["feishu"]["verification_token"] = mask_secret(masked["feishu"]["verification_token"])
        claude = masked.get("claude", {})
        backends = claude.get("backends", {})
        if isinstance(backends, dict):
            for backend_payload in backends.values():
                if not isinstance(backend_payload, dict):
                    continue
                auth_token = str(backend_payload.get("auth_token", "")).strip()
                if auth_token:
                    backend_payload["auth_token"] = mask_secret(auth_token)
        return masked
