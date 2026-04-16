from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from poco.agent.catalog import backend_option, normalize_backend_config
from poco.platform.common.platform import Platform


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Project:
    id: str
    name: str
    created_by: str
    backend: str = "codex"
    backend_config: dict[str, object] = field(default_factory=dict)
    model: str | None = None
    sandbox: str = "workspace-write"
    repo: str | None = None
    workdir: str | None = None
    workdir_presets: list[str] = field(default_factory=list)
    group_chat_id: str | None = None
    workspace_message_id: str | None = None
    platform: Platform = Platform.FEISHU
    archived: bool = False
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.backend_config = normalize_backend_config(
            self.backend,
            {
                **self.backend_config,
                **({"model": self.model} if self.model else {}),
                **({"sandbox": self.sandbox} if self.sandbox else {}),
            },
        )
        self.model = backend_option(self.backend, self.backend_config, "model")
        self.sandbox = backend_option(self.backend, self.backend_config, "sandbox") or "workspace-write"

    def bind_group(self, group_chat_id: str) -> None:
        self.group_chat_id = group_chat_id
        self.updated_at = utc_now()

    def bind_workspace_message(self, message_id: str) -> None:
        self.workspace_message_id = message_id
        self.updated_at = utc_now()

    def archive(self) -> None:
        self.archived = True
        self.updated_at = utc_now()

    def add_workdir_preset(self, preset: str) -> None:
        normalized = preset.strip()
        if normalized and normalized not in self.workdir_presets:
            self.workdir_presets.append(normalized)
            self.updated_at = utc_now()

    def set_model(self, model: str | None) -> None:
        normalized = model.strip() if model else None
        if normalized:
            self.backend_config["model"] = normalized
        else:
            self.backend_config.pop("model", None)
        self.model = backend_option(self.backend, self.backend_config, "model")
        self.updated_at = utc_now()

    def set_sandbox(self, sandbox: str | None) -> None:
        normalized = sandbox.strip() if sandbox else None
        if normalized:
            self.backend_config["sandbox"] = normalized
        else:
            self.backend_config.pop("sandbox", None)
        self.backend_config = normalize_backend_config(self.backend, self.backend_config)
        self.sandbox = backend_option(self.backend, self.backend_config, "sandbox") or "workspace-write"
        self.updated_at = utc_now()

    def set_backend_config(self, backend_config: dict[str, object]) -> None:
        self.backend_config = normalize_backend_config(self.backend, backend_config)
        self.model = backend_option(self.backend, self.backend_config, "model")
        self.sandbox = backend_option(self.backend, self.backend_config, "sandbox") or "workspace-write"
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "created_by": self.created_by,
            "backend": self.backend,
            "backend_config": dict(self.backend_config),
            "model": self.model,
            "sandbox": self.sandbox,
            "repo": self.repo,
            "workdir": self.workdir,
            "workdir_presets": list(self.workdir_presets),
            "group_chat_id": self.group_chat_id,
            "workspace_message_id": self.workspace_message_id,
            "platform": self.platform.value,
            "archived": self.archived,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
