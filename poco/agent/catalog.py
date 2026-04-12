from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BackendDescriptor:
    key: str
    label: str
    model_options: tuple[str, ...] = ()
    access_options: tuple[tuple[str, str], ...] = ()
    default_config: dict[str, object] = field(default_factory=dict)


_BACKEND_DESCRIPTORS: dict[str, BackendDescriptor] = {
    "codex": BackendDescriptor(
        key="codex",
        label="Codex",
        model_options=(
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.3-codex",
            "gpt-5.3-codex-spark",
        ),
        access_options=(
            ("Read Only", "read-only"),
            ("Project Only", "workspace-write"),
            ("Full Access", "danger-full-access"),
        ),
        default_config={"sandbox": "workspace-write"},
    ),
    "claude_code": BackendDescriptor(
        key="claude_code",
        label="Claude Code",
    ),
    "cursor_agent": BackendDescriptor(
        key="cursor_agent",
        label="Cursor Agent",
    ),
    "coco": BackendDescriptor(
        key="coco",
        label="CoCo",
    ),
}


def get_backend_descriptor(backend: str) -> BackendDescriptor:
    normalized = (backend or "").strip().lower()
    return _BACKEND_DESCRIPTORS.get(
        normalized,
        BackendDescriptor(key=normalized or "unknown", label=backend or "Unknown"),
    )


def normalize_backend_config(
    backend: str,
    config: dict[str, object] | None = None,
) -> dict[str, object]:
    descriptor = get_backend_descriptor(backend)
    normalized = dict(descriptor.default_config)
    if config:
        normalized.update({key: value for key, value in config.items() if value not in (None, "")})
    return normalized


def backend_option(backend: str, config: dict[str, object], key: str) -> str | None:
    value = config.get(key)
    if value is None:
        value = get_backend_descriptor(backend).default_config.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None
