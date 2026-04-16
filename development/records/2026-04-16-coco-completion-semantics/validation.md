# Validation

## 验证目标

1. `CocoRunner._timeout_seconds` 真的在 prompt stream 循环里生效（服务器 hang 时能主动 fail）
2. `CompletionGate` 弱终态兜底接入 coco，arm 信号为 `_meta.lastChunk: true`
3. 现有两个强终态分支（JSON-RPC response + usage_update + stopReason）行为完全保留
4. `.request()` 等内部同步调用的无限等待语义不变（`poll_timeout_seconds=None` 默认路径）

## 验证方法

### 代码层

- `poco/agent/coco.py`：
  - 顶部 import `CompletionGate`
  - `CocoRunner.__init__` 新增 `completion_settle_seconds: float = 1.0`
  - `CocoRunner._execute_prompt` 构造 `_TraeAcpPromptStream` 时透传 `timeout_seconds` / `completion_settle_seconds`
  - `_TraeAcpClient.read_next_message` / `_read_message` 新增 `poll_timeout_seconds: float | None = None` 参数
    - `None` → 保留当前无限等待（供 `.request()` 等内部同步调用使用）
    - 非 None → 累计 select 等待不超过该值，超时返回 `None`
  - `_TraeAcpClient.is_process_closed()` 新增：基于 `process.poll()` + `_has_ready_stream`
  - `_TraeAcpPromptStream.__init__` 新增 `timeout_seconds` / `completion_settle_seconds` 参数
  - `_TraeAcpPromptStream.__iter__` 重写：
    - 计算 `deadline = monotonic() + self._timeout_seconds`
    - 循环顶部 deadline 判定：超时 → yield `failed` with "Trae CLI timed out after N seconds."
    - 然后 `gate.tick()`，should_fire → yield `completed` with "Task completed by the coco runner after the final chunk settled."
    - `read_next_message(poll_timeout_seconds=min(0.25, remaining))`
    - `message is None` → 若 `is_process_closed()` 则 failed，否则 continue
  - `_translate_message` 新增 `completion_gate` 参数：
    - `lastChunk: True` 的 agent_message_chunk → `gate.arm(now)`
    - 其它 agent_message_chunk → `gate.disarm()`
  - 新增 helper `_extract_coco_acp_last_chunk_flag(update)`（严格匹配 `is True`，不接受 `"true"` / `1`）

### 测试层

- 把所有 7 个 `FakeSession.read_next_message(self) -> ...:` 签名改成 `read_next_message(self, **kwargs) -> ...:` 接住新参数（Python mock 惯例）
- 把 `test_coco_runner_does_not_complete_on_last_chunk_without_terminal_signal` 重命名为 `test_coco_runner_fails_when_stream_closes_after_last_chunk`（原断言完全保留，`is_process_closed=True` 确保闭流分支被选中）
- 新增两条 regression test：
  - `test_coco_runner_completes_via_settle_after_last_chunk_while_stream_stays_open`：lastChunk=true + 流保持开启 + 零 settle → 通过 settle 路径完成，raw_result 来自 live_text
  - `test_coco_runner_times_out_when_acp_server_hangs`：timeout_seconds=0 + read 永远返回 None → 第一次迭代就 failed，message 含 "timed out"

### 验收命令

1. `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'coco_runner'`
2. `uv run --extra dev pytest tests/test_agent_runner.py tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_debug_api.py tests/test_health.py tests/test_card_gateway.py tests/test_feishu_client.py`

## 结果

- `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'coco_runner'`
  - `9 passed, 38 deselected`（原 7 条，重命名 1 条 + 新增 2 条）
- `uv run --extra dev pytest tests/test_agent_runner.py tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_debug_api.py tests/test_health.py tests/test_card_gateway.py tests/test_feishu_client.py`
  - `179 passed`（上轮 baseline 177 + 新增 2）

## 是否通过

通过。`_timeout_seconds` 真正生效、settle 兜底接入、两个强终态路径零变化、`.request()` 等同步调用路径完全不动。

## 残留问题

- `_meta.lastChunk` 严格匹配 `is True`。若未来 server 改用 `"true"` / `1` 等其他真值表示，需要调整 helper
- 闭流 vs settle 的优先级：process 关闭时 `is_process_closed()` 胜过未 fire 的 settle gate。这是刻意行为（闭流是比 settle 更强的信号）
- `tests/test_demo_cards.py` 4 条 daemon-thread race 失败依然存在，与本轮无关

## 是否需要回滚/继续迭代

不需要回滚。四个 backend 的 completion 语义审计**全部收口**。
