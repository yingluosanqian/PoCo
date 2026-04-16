from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from os import getenv
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_REPO_ROOT = str(Path(__file__).resolve().parents[1])
DEFAULT_RUNTIME_DIR = str(Path.home() / ".poco")
DEFAULT_CONFIG_PATH = str(Path(DEFAULT_RUNTIME_DIR) / "poco.config.json")


def _config_path() -> Path:
    return Path(getenv("POCO_CONFIG_PATH", DEFAULT_CONFIG_PATH))


@lru_cache(maxsize=1)
def load_file_config() -> dict[str, object]:
    path = _config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _setting(name: str, default: str | None = None) -> str | None:
    env_value = getenv(name)
    if env_value is not None:
        return env_value
    file_value = load_file_config().get(name, default)
    if file_value is None:
        return None
    return str(file_value)


def _setting_int(name: str, default: int) -> int:
    value = _setting(name, str(default))
    return int(value or default)


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = field(default_factory=lambda: _setting("POCO_APP_NAME", "PoCo") or "PoCo")
    agent_backend: str = field(default_factory=lambda: _setting("POCO_AGENT_BACKEND", "codex") or "codex")
    codex_command: str = field(default_factory=lambda: _setting("POCO_CODEX_COMMAND", "codex") or "codex")
    codex_workdir: str = field(default_factory=lambda: _setting("POCO_CODEX_WORKDIR", DEFAULT_REPO_ROOT) or DEFAULT_REPO_ROOT)
    codex_model: str | None = field(default_factory=lambda: _setting("POCO_CODEX_MODEL"))
    codex_sandbox: str = field(default_factory=lambda: _setting("POCO_CODEX_SANDBOX", "workspace-write") or "workspace-write")
    codex_reasoning_effort: str = field(default_factory=lambda: _setting("POCO_CODEX_REASONING_EFFORT", "medium") or "medium")
    codex_approval_policy: str = field(default_factory=lambda: _setting("POCO_CODEX_APPROVAL_POLICY", "never") or "never")
    codex_timeout_seconds: int = field(default_factory=lambda: _setting_int("POCO_CODEX_TIMEOUT_SECONDS", 900))
    codex_transport_idle_seconds: int = field(default_factory=lambda: _setting_int("POCO_CODEX_TRANSPORT_IDLE_SECONDS", 1800))
    claude_command: str = field(default_factory=lambda: _setting("POCO_CLAUDE_COMMAND", "claude") or "claude")
    claude_workdir: str = field(default_factory=lambda: _setting("POCO_CLAUDE_WORKDIR", DEFAULT_REPO_ROOT) or DEFAULT_REPO_ROOT)
    claude_model: str | None = field(default_factory=lambda: _setting("POCO_CLAUDE_MODEL", "sonnet"))
    claude_permission_mode: str = field(default_factory=lambda: _setting("POCO_CLAUDE_PERMISSION_MODE", "default") or "default")
    claude_timeout_seconds: int = field(default_factory=lambda: _setting_int("POCO_CLAUDE_TIMEOUT_SECONDS", 900))
    cursor_command: str = field(default_factory=lambda: _setting("POCO_CURSOR_COMMAND", "cursor-agent") or "cursor-agent")
    cursor_workdir: str = field(default_factory=lambda: _setting("POCO_CURSOR_WORKDIR", DEFAULT_REPO_ROOT) or DEFAULT_REPO_ROOT)
    cursor_model: str | None = field(default_factory=lambda: _setting("POCO_CURSOR_MODEL", "auto"))
    cursor_mode: str = field(default_factory=lambda: _setting("POCO_CURSOR_MODE", "default") or "default")
    cursor_sandbox: str = field(default_factory=lambda: _setting("POCO_CURSOR_SANDBOX", "default") or "default")
    cursor_timeout_seconds: int = field(default_factory=lambda: _setting_int("POCO_CURSOR_TIMEOUT_SECONDS", 900))
    coco_command: str = field(default_factory=lambda: _setting("POCO_COCO_COMMAND", "traecli") or "traecli")
    coco_workdir: str = field(default_factory=lambda: _setting("POCO_COCO_WORKDIR", DEFAULT_REPO_ROOT) or DEFAULT_REPO_ROOT)
    coco_model: str | None = field(default_factory=lambda: _setting("POCO_COCO_MODEL"))
    coco_approval_mode: str = field(default_factory=lambda: _setting("POCO_COCO_APPROVAL_MODE", "default") or "default")
    coco_timeout_seconds: int = field(default_factory=lambda: _setting_int("POCO_COCO_TIMEOUT_SECONDS", 900))
    feishu_api_base_url: str = field(default_factory=lambda: (_setting("POCO_FEISHU_API_BASE_URL", "https://open.feishu.cn") or "https://open.feishu.cn").rstrip("/"))
    feishu_app_id: str | None = field(default_factory=lambda: _setting("POCO_FEISHU_APP_ID"))
    feishu_app_secret: str | None = field(default_factory=lambda: _setting("POCO_FEISHU_APP_SECRET"))
    feishu_delivery_mode: str = field(default_factory=lambda: (_setting("POCO_FEISHU_DELIVERY_MODE", "longconn") or "longconn").strip().lower())
    feishu_verification_token: str | None = field(default_factory=lambda: _setting("POCO_FEISHU_VERIFICATION_TOKEN"))
    feishu_encrypt_key: str | None = field(default_factory=lambda: _setting("POCO_FEISHU_ENCRYPT_KEY"))
    state_backend: str = field(default_factory=lambda: (_setting("POCO_STATE_BACKEND", "sqlite") or "sqlite").strip().lower())
    state_db_path: str = field(
        default_factory=lambda: _setting(
            "POCO_STATE_DB_PATH",
            str(Path(DEFAULT_RUNTIME_DIR) / "poco.db"),
        )
        or str(Path(DEFAULT_RUNTIME_DIR) / "poco.db")
    )

    @property
    def feishu_enabled(self) -> bool:
        return bool(self.feishu_app_id and self.feishu_app_secret)

    @property
    def feishu_verification_enabled(self) -> bool:
        return bool(self.feishu_verification_token)

    @property
    def feishu_signature_enabled(self) -> bool:
        return bool(self.feishu_encrypt_key)

    @property
    def runtime_mode(self) -> str:
        if self.feishu_enabled:
            return "feishu"
        return "local"

    @property
    def feishu_longconn_enabled(self) -> bool:
        return self.feishu_delivery_mode == "longconn"

    @property
    def feishu_api_origin(self) -> str:
        parsed = urlparse(self.feishu_api_base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(
                "POCO_FEISHU_API_BASE_URL must be a full URL such as https://open.feishu.cn"
            )
        return f"{parsed.scheme}://{parsed.netloc}"
