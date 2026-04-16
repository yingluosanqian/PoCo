# Validation

## 验证目标

确认引入 `CompletionGate` 后：

1. codex 现有完成语义完全一致（17 条 app-server 用例继续 passed）
2. Gate 本身纯状态行为可被单测覆盖
3. `runner.py` 里不再出现 `candidate_completion_at` / `candidate_tick_seen` 裸变量

## 验证方法

### 代码层

- 新增 `poco/agent/completion_gate.py`：`CompletionGate` 数据类，暴露 `is_armed` / `arm(now) -> bool` / `disarm()` / `tick(now) -> (should_fire, elapsed)`
- `poco/agent/runner.py`：
  - 顶部 import `CompletionGate`
  - `CodexAppServerRunner._execute_prompt` 内：
    - 用 `completion_gate = CompletionGate(settle_seconds=self._completion_settle_seconds)` 替代两个裸变量
    - top-of-loop 改调 `completion_gate.tick(monotonic())`
    - arm 点改调 `completion_gate.arm(current_time)`（返回 True 时打首次 arm log）
    - 8 处 `candidate_completion_at = None` 全部改调 `completion_gate.disarm()`
- `grep` 确认 runner.py 里不再存在两个旧变量

### 测试层

- 新增 `tests/test_completion_gate.py`，11 条纯单测：
  - `test_new_gate_is_idle`
  - `test_first_arm_returns_true`
  - `test_subsequent_arm_returns_false`
  - `test_arm_always_resets_tick_seen`
  - `test_disarm_clears_state`
  - `test_disarm_is_idempotent`
  - `test_first_tick_after_arm_never_fires`
  - `test_fires_after_tick_and_settle`
  - `test_does_not_fire_before_settle_elapses`
  - `test_disarm_between_arm_and_fire_prevents_firing`
  - `test_re_arm_after_fire_requires_fresh_tick`

## 结果

- `uv run --extra dev pytest -q tests/test_completion_gate.py`
  - `11 passed`
- `uv run --extra dev pytest -q tests/test_completion_gate.py tests/test_agent_runner.py`
  - `55 passed`
- `uv run --extra dev pytest -q tests/test_agent_runner.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_completion_gate.py tests/test_debug_api.py tests/test_health.py`
  - `103 passed`
- `grep -n 'candidate_completion_at\|candidate_tick_seen' poco/agent/runner.py`
  - 无输出

## 是否通过

通过。

## 残留问题

- `tests/test_demo_cards.py` 4 条 daemon-thread race 失败依然存在，和本轮无关（已在前一 record 里记录）
- Gate 目前只被 codex 使用。真正价值要等 claude_code / cursor_agent / coco 的 completion 审计接入时才能验证接口是否够用
- 其他 backend 迁移时若发现接口不够，再在本 record 后续迭代中补充

## 是否需要回滚/继续迭代

不需要回滚。后续按既定顺序推进：

1. 拆 `poco/agent/runner.py`（Refactor 1）
2. `claude_code` 的 completion 审计（Feature 1）
3. 然后是 `cursor_agent` / `coco`
