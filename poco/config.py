from __future__ import annotations

from dataclasses import dataclass, field
from os import getenv
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_REPO_ROOT = str(Path(__file__).resolve().parents[1])


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = field(default_factory=lambda: getenv("POCO_APP_NAME", "PoCo"))
    app_base_url: str | None = field(default_factory=lambda: getenv("POCO_APP_BASE_URL"))
    agent_backend: str = field(default_factory=lambda: getenv("POCO_AGENT_BACKEND", "codex"))
    codex_command: str = field(default_factory=lambda: getenv("POCO_CODEX_COMMAND", "codex"))
    codex_workdir: str = field(default_factory=lambda: getenv("POCO_CODEX_WORKDIR", DEFAULT_REPO_ROOT))
    codex_model: str | None = field(default_factory=lambda: getenv("POCO_CODEX_MODEL"))
    codex_sandbox: str = field(default_factory=lambda: getenv("POCO_CODEX_SANDBOX", "workspace-write"))
    codex_approval_policy: str = field(default_factory=lambda: getenv("POCO_CODEX_APPROVAL_POLICY", "never"))
    codex_timeout_seconds: int = field(default_factory=lambda: int(getenv("POCO_CODEX_TIMEOUT_SECONDS", "900")))
    feishu_api_base_url: str = field(default_factory=lambda: getenv("POCO_FEISHU_API_BASE_URL", "https://open.feishu.cn").rstrip("/"))
    feishu_app_id: str | None = field(default_factory=lambda: getenv("POCO_FEISHU_APP_ID"))
    feishu_app_secret: str | None = field(default_factory=lambda: getenv("POCO_FEISHU_APP_SECRET"))
    feishu_delivery_mode: str = field(default_factory=lambda: getenv("POCO_FEISHU_DELIVERY_MODE", "webhook").strip().lower())
    feishu_verification_token: str | None = field(default_factory=lambda: getenv("POCO_FEISHU_VERIFICATION_TOKEN"))
    feishu_encrypt_key: str | None = field(default_factory=lambda: getenv("POCO_FEISHU_ENCRYPT_KEY"))
    state_backend: str = field(default_factory=lambda: getenv("POCO_STATE_BACKEND", "sqlite").strip().lower())
    state_db_path: str = field(
        default_factory=lambda: getenv(
            "POCO_STATE_DB_PATH",
            str(Path(DEFAULT_REPO_ROOT) / ".work" / "poco.db"),
        )
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

    @property
    def app_origin(self) -> str | None:
        if not self.app_base_url:
            return None
        parsed = urlparse(self.app_base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(
                "POCO_APP_BASE_URL must be a full URL such as https://poco.example.com"
            )
        path = parsed.path.rstrip("/")
        return f"{parsed.scheme}://{parsed.netloc}{path}"
