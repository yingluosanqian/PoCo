import queue
from dataclasses import dataclass, field
from typing import List, Optional, Protocol


@dataclass
class ProviderConfig:
    name: str
    bin: str
    app_server_args: str
    model: str
    approval_policy: str
    sandbox: str
    reasoning_effort: str = ""
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class SessionMeta:
    provider: str
    session_id: str
    cwd: str
    thread_name: str = ""
    updated_at: str = ""
    source: str = ""
    originator: str = ""
    file_path: str = ""


class ProviderNotImplementedError(RuntimeError):
    pass


class SessionLocator(Protocol):
    provider_name: str

    def get(self, session_id: str) -> Optional[SessionMeta]: ...
    def list_recent(self, limit: int = 10) -> List[SessionMeta]: ...
    def delete(self, session_id: str) -> bool: ...


class ProviderClient(Protocol):
    def start(self) -> None: ...
    def notifications(self) -> "queue.Queue[dict]": ...
    def close(self) -> None: ...
    def ensure_thread(self, thread_id: Optional[str]) -> str: ...
    def start_turn(
        self,
        thread_id: str,
        text: str,
        local_image_paths: Optional[List[str]] = None,
    ) -> str: ...
    def interrupt_turn(self, thread_id: str, turn_id: str) -> None: ...
    def steer_turn(self, thread_id: str, turn_id: str, text: str) -> None: ...
