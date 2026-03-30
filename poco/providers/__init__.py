from .base import (
    ProviderClient,
    ProviderConfig,
    ProviderNotImplementedError,
    SessionLocator,
    SessionMeta,
)
from .claude import ClaudeProviderClient, ClaudeSessionLocator
from .codex import CodexProviderClient, CodexSessionLocator
from .models import model_choices


def build_provider_client(provider_name: str, provider_config: ProviderConfig, cwd: str) -> ProviderClient:
    provider = provider_name.strip().lower()
    if provider == "codex":
        return CodexProviderClient(provider_config, cwd)
    if provider == "claude":
        return ClaudeProviderClient(provider_config, cwd)
    raise RuntimeError(f"Unsupported provider: {provider_name}")


def build_session_locators() -> dict[str, SessionLocator]:
    return {
        "codex": CodexSessionLocator(),
        "claude": ClaudeSessionLocator(),
    }


__all__ = [
    "ClaudeProviderClient",
    "ClaudeSessionLocator",
    "CodexProviderClient",
    "CodexSessionLocator",
    "build_provider_client",
    "build_session_locators",
    "model_choices",
    "ProviderClient",
    "ProviderConfig",
    "ProviderNotImplementedError",
    "SessionLocator",
    "SessionMeta",
]
