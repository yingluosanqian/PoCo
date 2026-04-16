# Plan

## 目标

把 codex 里的 settle 状态机从裸变量升级成 `CompletionGate` 小对象，为后续三个 backend 复用铺好地基，不改对外行为。

## 范围

- 新增 `poco/agent/completion_gate.py`，定义 `CompletionGate` 数据类
  - 接口：`arm(now) -> bool`、`disarm()`、`is_armed`（property）、`tick(now) -> (should_fire, elapsed)`
  - 不做 logging，调用方通过 `arm()` 返回值判断是否首次 arm 再自己打 log
- 新增 `tests/test_completion_gate.py`，纯单测覆盖：
  - 首次 arm 返回 True，再 arm 返回 False
  - arm 总是重置 tick_seen
  - disarm 幂等
  - tick 在未 arm / 首次 / settle 前 / settle 后 四种场景的返回值
- 修改 `poco/agent/runner.py::CodexAppServerRunner._execute_prompt`：
  - 引入 `gate = CompletionGate(settle_seconds=self._completion_settle_seconds)`
  - 替换 `candidate_completion_at = current_time; candidate_tick_seen = False` → `if gate.arm(current_time): _LOGGER.info(...)`
  - 替换 `candidate_completion_at = None` → `gate.disarm()`
  - 替换 top-of-loop 的 settle 判定 → 调用 `gate.tick(monotonic())`

## 不在范围内的内容

- 不迁移 `claude_code` / `cursor_agent` / `coco`
- 不改 codex 的任何对外语义（log 文本 / update message 文本 / raw_result 优先级不变）
- 不合并其他 runner.py 的 helper

## 风险点

- 重构期间保持 codex 现有 17 条 `app_server_runner` 测试通过是硬线
- 新 Gate 接口必须能完全替代现有两个变量，不能遗留混用

## 验收标准

- `uv run --extra dev pytest -q tests/test_completion_gate.py` 全绿
- `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'app_server_runner'` 依然 17 passed
- `uv run --extra dev pytest -q tests/test_agent_runner.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py` 依然 83 passed
- runner.py 里不再存在 `candidate_completion_at` / `candidate_tick_seen` 这两个变量

## 实施顺序

1. 写 `completion_gate.py`
2. 写 `test_completion_gate.py` 并单跑通过
3. 改 `CodexAppServerRunner._execute_prompt`
4. 跑完整相关测试集
5. 更新 validation.md
