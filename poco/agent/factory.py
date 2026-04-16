from __future__ import annotations

from poco.agent.claude_code import ClaudeCodeRunner
from poco.agent.coco import CocoRunner
from poco.agent.codex_app_server import CodexAppServerRunner
from poco.agent.common import AgentRunner
from poco.agent.cursor_agent import CursorAgentRunner
from poco.agent.stub import MultiAgentRunner, StubAgentRunner, UnavailableAgentRunner


def create_agent_runner(
    *,
    backend: str,
    codex_command: str,
    codex_workdir: str,
    codex_model: str | None,
    codex_sandbox: str,
    codex_reasoning_effort: str,
    codex_approval_policy: str,
    codex_timeout_seconds: int,
    claude_command: str,
    claude_workdir: str,
    claude_model: str | None,
    claude_permission_mode: str,
    claude_timeout_seconds: int,
    cursor_command: str,
    cursor_workdir: str,
    cursor_model: str | None,
    cursor_mode: str,
    cursor_sandbox: str,
    cursor_timeout_seconds: int,
    coco_command: str,
    coco_workdir: str,
    coco_model: str | None,
    coco_approval_mode: str,
    coco_timeout_seconds: int,
) -> AgentRunner:
    normalized = backend.strip().lower() or "codex"
    runners: dict[str, AgentRunner] = {
        "codex": CodexAppServerRunner(
            command=codex_command,
            workdir=codex_workdir,
            model=codex_model,
            sandbox=codex_sandbox,
            reasoning_effort=codex_reasoning_effort,
            approval_policy=codex_approval_policy,
            timeout_seconds=codex_timeout_seconds,
        ),
        "claude_code": ClaudeCodeRunner(
            command=claude_command,
            workdir=claude_workdir,
            model=claude_model,
            permission_mode=claude_permission_mode,
            timeout_seconds=claude_timeout_seconds,
        ),
        "cursor_agent": CursorAgentRunner(
            command=cursor_command,
            workdir=cursor_workdir,
            model=cursor_model,
            mode=cursor_mode,
            sandbox=cursor_sandbox,
            timeout_seconds=cursor_timeout_seconds,
        ),
        "coco": CocoRunner(
            command=coco_command,
            workdir=coco_workdir,
            model=coco_model,
            approval_mode=coco_approval_mode,
            timeout_seconds=coco_timeout_seconds,
        ),
        "stub": StubAgentRunner(),
    }
    if normalized not in runners:
        return UnavailableAgentRunner(
            name=normalized or "unknown",
            reason=(
                f"Unsupported agent backend: {backend}. "
                "Current implemented backends are 'codex', 'claude_code', 'cursor_agent', 'coco', and 'stub'."
            ),
        )
    return MultiAgentRunner(
        default_backend=normalized,
        runners=runners,
    )
