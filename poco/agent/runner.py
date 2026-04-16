from __future__ import annotations

# Stdlib modules re-exposed so existing test patches like
# ``patch("poco.agent.runner.shutil.which", ...)`` keep reaching the backend code.
import os  # noqa: F401
import select  # noqa: F401
import shutil  # noqa: F401
import subprocess  # noqa: F401

from poco.agent.claude_code import (
    ClaudeCodeRunner,
    _ClaudeActiveSession,
    _ClaudePendingControl,
    _extract_claude_message_text,
)
from poco.agent.coco import (
    CocoRunner,
    _TraeAcpClient,
    _TraeAcpPromptStream,
    _TraeAcpTransport,
    _TraePromptEvent,
    _TraePromptTurnState,
    _coco_content_text,
    _extract_coco_acp_message_id,
    _extract_coco_acp_output_chunk,
    _extract_coco_acp_session_id,
    _extract_coco_acp_stop_reason,
)
from poco.agent.codex_app_server import (
    CodexAppServerRunner,
    _CodexActiveTurn,
    _CodexAppServerSession,
    _CodexAppServerTransport,
    _codex_reasoning_summary,
    _codex_reasoning_token_count,
    _error_notification_message,
    _extract_thread_id,
    _extract_turn_id,
    _turn_error_message,
)
from poco.agent.codex_cli import CodexCliRunner
from poco.agent.common import (
    AgentRunUpdate,
    AgentRunner,
    UpdateKind,
    _cleanup_subprocess,
    _compact_json,
    _first_non_empty,
    _has_ready_stream,
    _jsonrpc_error_message,
    _normalized_prompt,
    _optional_string,
    _parse_json_event,
    _requires_confirmation,
    _string_or_none,
)
from poco.agent.cursor_agent import (
    CursorAgentRunner,
    _extract_cursor_error_detail,
    _extract_cursor_final_text,
    _extract_cursor_output_chunk,
    _extract_cursor_session_id,
    _extract_cursor_terminal_result,
    _extract_message_text_preserving_whitespace,
    _normalize_cursor_model,
    _normalize_cursor_sandbox,
)
from poco.agent.factory import create_agent_runner
from poco.agent.stub import MultiAgentRunner, StubAgentRunner, UnavailableAgentRunner

__all__ = [
    "AgentRunUpdate",
    "AgentRunner",
    "ClaudeCodeRunner",
    "CocoRunner",
    "CodexAppServerRunner",
    "CodexCliRunner",
    "CursorAgentRunner",
    "MultiAgentRunner",
    "StubAgentRunner",
    "UnavailableAgentRunner",
    "UpdateKind",
    "_CodexAppServerSession",
    "_TraeAcpClient",
    "_cleanup_subprocess",
    "create_agent_runner",
]
