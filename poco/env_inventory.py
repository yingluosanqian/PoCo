from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

_INVENTORY_NOTE = (
    "This inventory only reports whether each key is present in the PoCo "
    "process environment and the length of its value. Values are never "
    "returned. Use it to diagnose 'did PoCo inherit my env var' when an "
    "agent backend subprocess behaves unexpectedly."
)

_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "codex",
        (
            "POCO_CODEX_COMMAND",
            "POCO_CODEX_WORKDIR",
            "POCO_CODEX_MODEL",
            "POCO_CODEX_SANDBOX",
            "POCO_CODEX_REASONING_EFFORT",
            "POCO_CODEX_APPROVAL_POLICY",
            "POCO_CODEX_TIMEOUT_SECONDS",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
        ),
    ),
    (
        "claude_code",
        (
            "POCO_CLAUDE_COMMAND",
            "POCO_CLAUDE_WORKDIR",
            "POCO_CLAUDE_MODEL",
            "POCO_CLAUDE_PERMISSION_MODE",
            "POCO_CLAUDE_TIMEOUT_SECONDS",
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
        ),
    ),
    (
        "cursor_agent",
        (
            "POCO_CURSOR_COMMAND",
            "POCO_CURSOR_WORKDIR",
            "POCO_CURSOR_MODEL",
            "POCO_CURSOR_MODE",
            "POCO_CURSOR_SANDBOX",
            "POCO_CURSOR_TIMEOUT_SECONDS",
        ),
    ),
    (
        "coco",
        (
            "POCO_COCO_COMMAND",
            "POCO_COCO_WORKDIR",
            "POCO_COCO_MODEL",
            "POCO_COCO_APPROVAL_MODE",
            "POCO_COCO_TIMEOUT_SECONDS",
        ),
    ),
    (
        "proxy",
        (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "NO_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "no_proxy",
            "all_proxy",
        ),
    ),
)


def whitelisted_keys() -> tuple[str, ...]:
    return tuple(key for _, keys in _CATEGORIES for key in keys)


def build_env_inventory(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = env if env is not None else os.environ
    categories: list[dict[str, Any]] = []
    for name, keys in _CATEGORIES:
        variables: list[dict[str, Any]] = []
        for key in keys:
            raw = source.get(key)
            variables.append(
                {
                    "key": key,
                    "present": raw is not None,
                    "length": len(raw) if raw is not None else 0,
                }
            )
        categories.append({"name": name, "variables": variables})
    return {"note": _INVENTORY_NOTE, "categories": categories}
