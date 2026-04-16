# Plan

## 目标

把 CompletionGate 弱终态兜底接入 `cursor_agent`，arm 信号定义为"summary assistant event（无新 output_chunk 但有 final_text）"，disarm 信号为"任何新 output_chunk"。

## 范围

- `poco/agent/cursor_agent.py`：
  - import `CompletionGate`
  - `__init__` 新增 `completion_settle_seconds: float = 1.0`
  - `_execute_prompt` 内：
    - 实例化 gate
    - while-loop 顶部加 `gate.tick(monotonic())` 判定
    - 在提取完 `output_chunk` / `extracted_final_text` 后：
      - `output_chunk` 非空 → `gate.disarm()`
      - `output_chunk is None` AND `extracted_final_text` 非空 AND `live_text` 非空 → `gate.arm(monotonic())`，首次 arm 打 INFO log
    - settle fire 处用独立 completed message 文本
  - 不改 `_extract_cursor_output_chunk` / `_extract_cursor_final_text` / `_extract_cursor_terminal_result` 任何逻辑
- `tests/test_agent_runner.py`：新增 1 条 regression test
  - `test_cursor_runner_completes_via_settle_after_summary_assistant_without_result_event`
  - 构造 stream：session init → 多个增量 assistant 消息 → summary assistant (repeat 完整文本) → 无限非 disarm 事件（比如空 chat_id 心跳）
  - `completion_settle_seconds=0.0`
  - 断言：`updates[-1].kind == "completed"`、`raw_result` 来自 live_text/final_text、message 是 settle 分支文本

## 不在范围内的内容

- 不改 coco
- 不改 factory.py
- 不改 Settings
- 不改 cursor_agent 强终态路径（`type=result`）的对外文本、raw_result 优先级、log 现有 INFO 行
- 不改现有 6 条 cursor tests 的断言

## 风险点

- arm / disarm 判定必须用已经提取好的 `output_chunk` / `extracted_final_text` 结果，不重复解析 event
- arm 条件顺序：先判 `output_chunk` 非空 → disarm；再判"summary assistant"→ arm。避免"既有 new delta 又 arm"的矛盾
- 保持 log / message 文本改动最小，便于线上 grep

## 验收标准

- `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'cursor_runner'`：7 passed（原 6 + 新 1）
- `uv run --extra dev pytest tests/test_agent_runner.py tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_debug_api.py tests/test_health.py`：105 passed（上轮 104 + 新 1）
- `grep -n 'completion_gate' poco/agent/cursor_agent.py`：至少 4 处（arm / disarm / tick / settle 分支）

## 实施顺序

1. 修改 `CursorAgentRunner.__init__` 加参数
2. 修改 `_execute_prompt` 接入 gate
3. 加新 test
4. 跑 cursor 子集确认
5. 跑 broad sweep
6. 更新 validation
