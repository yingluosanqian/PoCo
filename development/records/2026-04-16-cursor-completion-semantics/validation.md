# Validation

## 验证目标

确认 `cursor_agent` 接入 `CompletionGate` 后：

1. 强终态（`type=result` event）路径行为完全保留
2. 弱终态（summary assistant event：`output_chunk` 为 None 但 `extracted_final_text` 非空，且已有非空 `live_text`）能 arm gate
3. 任何带新 `output_chunk` 的后续事件能立即 disarm
4. 现有 7 条 cursor tests 完全不变

## 验证方法

### 代码层

- `poco/agent/cursor_agent.py`：
  - 新增 `from poco.agent.completion_gate import CompletionGate`
  - `CursorAgentRunner.__init__` 新增 `completion_settle_seconds: float = 1.0`
  - `_execute_prompt` 内：
    - 实例化 `CompletionGate`
    - while-loop 顶部（timeout 判定之后、`select.select` 之前）调 `gate.tick(monotonic())`
    - 事件处理：
      - `output_chunk` 非空 → `gate.disarm()`
      - `output_chunk is None` AND `extracted_final_text` AND `live_text` AND `event.type != "result"` → `gate.arm(monotonic())`，首次 arm 打 INFO log
    - settle fire 路径用独立 completed message：`Task completed by the cursor_agent runner after the final assistant message settled.`
  - 不改任何 `_extract_cursor_*` helper 逻辑
  - 不改强终态 `type=result` 路径

不改动：

- `poco/agent/factory.py`：`completion_settle_seconds` 走类默认
- `poco/config.py` / Settings
- 其他 backend 模块

### 测试层

- `tests/test_agent_runner.py` 新增 1 条：
  - `test_cursor_runner_completes_via_settle_after_summary_assistant_without_result_event`
  - 构造 stdout stream：`system/init` → 两条增量 assistant(各带部分文本) → summary assistant（完整文本 `"hello world"`）→ 无限 `type=status` 心跳
  - `completion_settle_seconds=0.0`
  - 断言：
    - `updates[-1].kind == "completed"`
    - `updates[-1].raw_result == "hello world"`
    - `updates[-1].message == "Task completed by the cursor_agent runner after the final assistant message settled."`

### 验收命令

1. `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'cursor_runner'`
2. `uv run --extra dev pytest tests/test_agent_runner.py tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_debug_api.py tests/test_health.py`

## 结果

- `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'cursor_runner'`
  - `8 passed, 38 deselected`（原 7 条 + 新增 1 条）
- `uv run --extra dev pytest tests/test_agent_runner.py tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_debug_api.py tests/test_health.py`
  - `105 passed`（上轮 baseline 104 + 新增 1）

## 是否通过

通过。arm 信号基于 cursor CLI 实际观察到的 summary assistant 行为，disarm 基于新 output_chunk，两者互斥且互补；强终态与文本完全保留。

## 残留问题

- arm 信号依赖 cursor CLI 的 summary assistant 行为。若未来协议更改不再重发完整消息，兜底会不触发，退回到当前"纯强终态 + timeout"。不会引入新 bug
- 如果 cursor 的某个 tool-use 中间阶段恰好产生了"无新 output_chunk 但携带 final_text"的 event，可能误 arm。disarm 规则（下一条带新 output_chunk 立即 disarm）兜底
- `tests/test_demo_cards.py` 4 条 daemon-thread race 失败依然存在，与本轮无关

## 是否需要回滚/继续迭代

不需要回滚。队列最后一轮：`coco` 的 completion 语义审计。
