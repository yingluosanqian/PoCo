# Validation

## 验证目标

确认按方案 A 拆分 `poco/agent/runner.py` 后：

1. 原先由 runner.py 直接承载的 5 个 backend runner + 它们的 transport / session / state dataclass + 所有通用 helper 全部迁到各自模块
2. `poco.agent.runner` 降级为 re-export facade（不再含任何类 / 函数定义）
3. 所有外部 `from poco.agent.runner import ...` 导入面零破坏
4. 既有测试 baseline（`test_agent_runner.py` + `test_completion_gate.py` = 55，扩展套件 = 103）全部原样绿

## 验证方法

### 代码层

新增：

- `poco/agent/common.py`：`AgentRunUpdate` / `UpdateKind` / `AgentRunner` Protocol + 10 个共享 helper（`_cleanup_subprocess` / `_requires_confirmation` / `_normalized_prompt` / `_parse_json_event` / `_optional_string` / `_string_or_none` / `_first_non_empty` / `_has_ready_stream` / `_compact_json` / `_jsonrpc_error_message`）
- `poco/agent/stub.py`：`StubAgentRunner` / `UnavailableAgentRunner` / `MultiAgentRunner`
- `poco/agent/codex_app_server.py`：`CodexAppServerRunner` + `_CodexAppServerTransport` + `_CodexActiveTurn` + `_CodexAppServerSession` + codex 私有 helper（`_extract_thread_id` / `_extract_turn_id` / `_codex_reasoning_token_count` / `_codex_reasoning_summary` / `_turn_error_message` / `_error_notification_message`）
- `poco/agent/codex_cli.py`：`CodexCliRunner`
- `poco/agent/claude_code.py`：`ClaudeCodeRunner` + `_ClaudePendingControl` + `_ClaudeActiveSession` + `_extract_claude_message_text`
- `poco/agent/cursor_agent.py`：`CursorAgentRunner` + cursor 私有 helper（`_extract_cursor_session_id` / `_normalize_cursor_model` / `_normalize_cursor_sandbox` / `_extract_cursor_output_chunk` / `_extract_cursor_final_text` / `_extract_cursor_terminal_result` / `_extract_cursor_error_detail` / `_extract_message_text_preserving_whitespace`）
- `poco/agent/coco.py`：`CocoRunner` + `_TraePromptEvent` + `_TraePromptTurnState` + `_TraeAcpTransport` + `_TraeAcpClient` + `_TraeAcpPromptStream` + coco 私有 helper（`_extract_coco_acp_session_id` / `_extract_coco_acp_output_chunk` / `_extract_coco_acp_message_id` / `_extract_coco_acp_stop_reason` / `_coco_content_text`）
- `poco/agent/factory.py`：`create_agent_runner`

改写：

- `poco/agent/runner.py`：从 2942 行缩成 87 行，仅含：
  - `from __future__ import annotations`
  - 四个 stdlib 重导入（`os` / `select` / `shutil` / `subprocess`，带 `# noqa: F401`）—— 必要，用于让 `patch("poco.agent.runner.shutil.which", ...)` 等既有测试经过 module-cache 穿透到 backend 模块
  - 从各子模块的 `from ... import` re-export
  - `__all__` 列出外部 consumer 关心的符号

测试调整：

- `tests/test_agent_runner.py` 里 23 处 patch path 字符串常量做了路径迁移：
  - 16 处 `poco.agent.runner._CodexAppServerSession` → `poco.agent.codex_app_server._CodexAppServerSession`
  - 7 处 `poco.agent.runner._TraeAcpClient` → `poco.agent.coco._TraeAcpClient`
- 仅改 patch 目标字符串，不改测试断言或 fixture 任何一行。这是 Python 的 mock patching 惯例：patch 应该指向符号被查找的位置，而不是被定义的位置。

不改动：

- `poco/agent/completion_gate.py`（record 明确禁止）
- `poco/agent/catalog.py` / `poco/main.py` / `poco/task/controller.py`

### 避开的歧路

子 agent 初版实现为了"零测试改动"，在 `CodexAppServerRunner._start_transport` 与 `CocoRunner._start_transport` 里加了 `getattr(sys.modules.get("poco.agent.runner"), ...)` 动态查类的兜底，方便测试 patch facade。这种把测试 patching 路径耦合进生产代码的做法不合理（生产代码检查自己是否被测试），review 时被驳回。最终选择改 23 行测试 patch 字符串，保持生产代码干净。

## 结果

- `grep -n '^class\|^def ' poco/agent/runner.py`
  - 无输出（facade 内无类 / 函数定义）
- `wc -l poco/agent/runner.py`
  - `87` 行，满足 < 100 的目标
- 拆分后模块行数：
  - `common.py`：150
  - `stub.py`：141
  - `codex_app_server.py`：787（去掉 sys.modules 兜底后）
  - `codex_cli.py`：274
  - `claude_code.py`：539
  - `cursor_agent.py`：457
  - `coco.py`：652（去掉 sys.modules 兜底后）
  - `factory.py`：84
  - `runner.py`：87
- `uv run --extra dev pytest -q tests/test_completion_gate.py tests/test_agent_runner.py`
  - `55 passed`
- `uv run --extra dev pytest -q tests/test_agent_runner.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_completion_gate.py tests/test_debug_api.py tests/test_health.py`
  - `103 passed`

## 是否通过

通过。所有外部 import 面（`poco.main` / `poco.task.controller` / `poco.agent.catalog`）保持原样可用；测试 patch 路径迁到符号实际所在模块；生产代码零 introspection hack；runner 行为、日志文本、错误信息与基线完全一致；测试计数与基线完全一致。

## 残留问题

- `tests/test_demo_cards.py` 4 条 daemon-thread race 失败依然存在，与本轮无关（前一 record 已记录）
- `runner.py` 里保留了 4 行 stdlib 重导入（`# noqa: F401`）以兼容既有 stdlib 级别的 patch。这是 mock patching 常见的惯例，后续若把剩余 stdlib patch（`shutil.which` / `subprocess.Popen` / `os.urandom` / `select.select` 共 ~40 处）也迁到子模块路径，就可以删掉这几行

## 是否需要回滚/继续迭代

不需要回滚。按既定顺序推进 Feature 1（`claude_code` 的 completion 语义审计），之后是 `cursor_agent` / `coco`。
