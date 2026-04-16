# Validation

## 验证目标

确认在 `claude_code` backend 接入 `CompletionGate` 后：

1. 强终态（`result` event）路径行为完全保留，log 新增一行 INFO 不改变 update 文本 / raw_result 优先级
2. 弱终态（`assistant.stop_reason == "end_turn"`）arm 后，在"无 result event + 持续非 disarm 心跳"场景下能通过 settle 兜底完成
3. tool turn（`assistant.stop_reason != "end_turn"`）不会触发 arm，后续 tool 活动也不会误 fire
4. 现有 5 条 `claude_runner_*` 用例完全不变

## 验证方法

### 代码层

- `poco/agent/claude_code.py`：
  - 新增 `import logging`、`_LOGGER`、`CompletionGate` import
  - `ClaudeCodeRunner.__init__` 新增 `completion_settle_seconds: float = 1.0`，与 codex 同
  - `_execute_prompt` 内：
    - 实例化 `CompletionGate`
    - while-loop 顶部（timeout 判定之后、`select.select` 之前）调 `gate.tick(monotonic())`
    - `stream_event.content_block_delta.text_delta` 处 `gate.disarm()`
    - `assistant` event 处解析 `stop_reason`：
      - `end_turn` → `gate.arm(now)`，首次 arm 打 INFO log
      - 其他值 → `gate.disarm()`
    - `result` event `subtype=success` 处加 INFO log
  - settle 兜底完成使用独立文本 `Task completed by the claude_code runner after the final assistant message settled.`，与强终态路径文本可区分
- 新增 module-level helper `_extract_claude_message_stop_reason(message)`

不改动：

- `poco/agent/factory.py`：`completion_settle_seconds` 走类默认 1.0，与 codex 保持一致
- `poco/config.py` / Settings：不新增字段
- 其他 backend 模块

### 测试层

- `tests/test_agent_runner.py` 新增 1 条：
  - `test_claude_runner_completes_via_settle_after_end_turn_assistant_without_result_event`
  - 构造 stdout stream：`control_response` → `system/init` → `stream_event.text_delta` → `assistant(stop_reason=end_turn)` → 无限 `control_request` 心跳
  - 用 `completion_settle_seconds=0.0` 压缩 settle 窗口
  - 断言：
    - `updates[-1].kind == "completed"`
    - `updates[-1].raw_result == "partial answer"`（来自 streamed_text）
    - `updates[-1].message == "Task completed by the claude_code runner after the final assistant message settled."`

### 验收命令

1. `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'claude_runner'`
2. `uv run --extra dev pytest tests/test_agent_runner.py tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_debug_api.py tests/test_health.py`

## 结果

- `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'claude_runner'`
  - `6 passed, 39 deselected`（原 5 条 + 新增 1 条）
- `uv run --extra dev pytest tests/test_agent_runner.py tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_debug_api.py tests/test_health.py`
  - `104 passed`（上轮 baseline 103 + 新增 1）

## 是否通过

通过。强终态行为保留、弱终态兜底按 codex 同款模板接入、无行为回归。

## 残留问题

- `stop_reason` 当前只识别 `assistant.message.stop_reason`。如果后续发现真实 claude CLI 的 `stream_event.event.type=="message_delta"` 才带 `stop_reason`，需要追加 arm 点。本 record decision 已标注为观测后再补
- `tests/test_demo_cards.py` 4 条 daemon-thread race 失败依然存在，与本轮无关

## 是否需要回滚/继续迭代

不需要回滚。按队列继续：

1. `cursor_agent` 的 completion 语义审计
2. `coco` 的 completion 语义审计

每轮开独立 record，按本轮模板复刻。
