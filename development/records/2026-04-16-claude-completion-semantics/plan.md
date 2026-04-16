# Plan

## 目标

把 codex 的 final_answer settle 兜底模式，照搬到 `claude_code`，以 `assistant event stop_reason=end_turn` 作为弱终态 arm 信号。

## 范围

- `poco/agent/claude_code.py`：
  - import `CompletionGate`
  - `__init__` 新增 `completion_settle_seconds: float = 1.0` 参数（类默认值，factory 不改）
  - 新增 module-level helper `_extract_claude_message_stop_reason(message)`
  - `_execute_prompt` 内：
    - 构造 `completion_gate`
    - 在 timeout 判定之后、`select.select` 之前加 settle tick 判定
    - 在 `stream_event.content_block_delta.text_delta` 处 disarm
    - 在 `assistant` event 处依据 stop_reason arm 或 disarm
    - `result` event 处加强终态路径 INFO log
    - settle fire 处加 INFO log，completed update message 用独立文本便于区分
- `tests/test_agent_runner.py`：新增 1 条 regression test
  - `test_claude_runner_completes_via_settle_after_end_turn_assistant_without_result_event`
  - 构造 stream：init → stream_event deltas → assistant(stop_reason=end_turn) → 无限 control_response 心跳
  - 断言：在 ≤ 少量 readline 次数内完成，completed update，raw_result 来自 streamed_text
  - 用 `completion_settle_seconds=0.0` 压缩测试等待

## 不在范围内的内容

- 不改 cursor_agent / coco
- 不改 factory.py
- 不改 Settings 字段
- 不改 claude_code 强终态路径文本
- 不改既有 5 条 claude tests

## 风险点

- `stop_reason` 字段路径在 real claude CLI 输出里可能分布在两处。本轮只认 `assistant event message.stop_reason`；若后续测试复盘发现真实 CLI 发 `stream_event.message_delta` 才带，再加第二个 arm 点
- while-loop 里添加 top-of-loop tick 时必须在 timeout 判定**之后**（preserve timeout 行为）、`select.select` **之前**（避免吃一次 250ms 延迟才 fire）
- 必须在 `continue` 到下一轮循环之前确保 gate 状态已经更新（比如 disarm 路径别漏）

## 验收标准

- `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'claude_runner'` 全部 passed（新增 1 条 + 原 5 条 = 6）
- `uv run --extra dev pytest -q tests/test_agent_runner.py tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_debug_api.py tests/test_health.py` 总 passed 从现 103 升到 104
- `grep -n 'completion_gate' poco/agent/claude_code.py` 至少 5 处（arm / 若干 disarm / tick / settle 分支）
- 强终态路径行为完全一致：raw_result 优先级不变、日志文本不变

## 实施顺序

1. `_extract_claude_message_stop_reason` helper
2. `ClaudeCodeRunner.__init__` 加参数
3. `_execute_prompt` 接入 gate
4. 加新 test
5. 跑 claude_runner 子集确认
6. 跑 broad sweep 确认 baseline
7. 更新 validation
