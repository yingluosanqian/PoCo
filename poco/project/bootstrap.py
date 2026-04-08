from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from poco.project.models import Project


class ProjectBootstrapError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProjectBootstrapResult:
    group_chat_id: str | None = None


class ProjectBootstrapper(Protocol):
    def bootstrap_project(
        self,
        *,
        project: Project,
        actor_id: str,
    ) -> ProjectBootstrapResult: ...


class NullProjectBootstrapper:
    def bootstrap_project(
        self,
        *,
        project: Project,
        actor_id: str,
    ) -> ProjectBootstrapResult:
        return ProjectBootstrapResult()
