from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_REPO_ROOT = str(Path(__file__).resolve().parents[1])


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = getenv("POCO_APP_NAME", "PoCo")
    agent_backend: str = getenv("POCO_AGENT_BACKEND", "codex")
    codex_command: str = getenv("POCO_CODEX_COMMAND", "codex")
    codex_workdir: str = getenv("POCO_CODEX_WORKDIR", DEFAULT_REPO_ROOT)
    codex_model: str | None = getenv("POCO_CODEX_MODEL")
    codex_sandbox: str = getenv("POCO_CODEX_SANDBOX", "workspace-write")
    codex_approval_policy: str = getenv("POCO_CODEX_APPROVAL_POLICY", "never")
    codex_timeout_seconds: int = int(getenv("POCO_CODEX_TIMEOUT_SECONDS", "900"))
    feishu_api_base_url: str = getenv("POCO_FEISHU_API_BASE_URL", "https://open.feishu.cn").rstrip("/")
    feishu_app_id: str | None = getenv("POCO_FEISHU_APP_ID")
    feishu_app_secret: str | None = getenv("POCO_FEISHU_APP_SECRET")
    feishu_verification_token: str | None = getenv("POCO_FEISHU_VERIFICATION_TOKEN")
    feishu_encrypt_key: str | None = getenv("POCO_FEISHU_ENCRYPT_KEY")

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
    def feishu_api_origin(self) -> str:
        parsed = urlparse(self.feishu_api_base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(
                "POCO_FEISHU_API_BASE_URL must be a full URL such as https://open.feishu.cn"
            )
        return f"{parsed.scheme}://{parsed.netloc}"
