# Plan

## 目标

1. 让 `CocoRunner._timeout_seconds` 真正在 prompt stream 循环里生效
2. 给 coco 加 `CompletionGate`，arm 信号为 `_meta.lastChunk: true`，对齐前三个 backend

## 范围

- `poco/agent/coco.py`：
  - `_TraeAcpClient.read_next_message` / `_read_message` 新增 `poll_timeout_seconds: float | None = None` 参数
  - `_TraeAcpPromptStream.__init__` 新增 `timeout_seconds` / `completion_settle_seconds` 参数
  - `_TraeAcpPromptStream.__iter__` 重写循环：deadline 检查 + CompletionGate tick + 有限 poll 读
  - `CocoRunner.__init__` 新增 `completion_settle_seconds: float = 1.0`
  - `CocoRunner._execute_prompt` 构造 `_TraeAcpPromptStream` 时传入两个 timeout
  - 新增 helper `_extract_coco_acp_last_chunk_flag(update)`（或内联判断）
- `tests/test_agent_runner.py`：
  - 微调所有现有 `FakeSession.read_next_message` 签名接受 `**kwargs`（保持向后兼容），避免触发 TypeError
  - 新增两条 regression test：
    - `test_coco_runner_times_out_when_acp_server_hangs`：FakeSession 的 `read_next_message` 无限返回 None，CocoRunner 应在 timeout 内 yield failed
    - `test_coco_runner_completes_via_settle_after_last_chunk_without_terminal_signal`：FakeSession 发 `lastChunk: true` 之后持续返回 None，应通过 settle 完成

## 不在范围内的内容

- 不改 `_TraeAcpClient.request()` 的外部语义（同步 request 仍然无限等待 response）
- 不改 `_TraeAcpClient.initialize` / `open_session` / `set_mode` / `set_model`
- 不改 factory.py、Settings
- 不改其他 backend

## 风险点

- `FakeSession.read_next_message()` 在 ~7 条 coco test 里都是固定签名，需要统一改成接受 `**kwargs`
- `poll_timeout_seconds=None` 必须严格保留"无限等待"语义，避免影响 `.request()` 内部调用
- `deadline` 到达时必须保证 yield 的 failed event message 指出是 timeout，与 codex / claude / cursor 文本风格对齐
- `lastChunk: true` 判定不能因为 lastChunk 为 `False` 或缺失而误触发

## 验收标准

- `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'coco_runner'`：9 passed（原 7 + 新 2）
- `uv run --extra dev pytest tests/test_agent_runner.py tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_debug_api.py tests/test_health.py tests/test_card_gateway.py tests/test_feishu_client.py`：**179 passed**（上轮 177 + 新 2）
- `grep -n 'completion_gate\|_timeout_seconds\|deadline' poco/agent/coco.py` 能看到 gate 相关调用与 deadline 执行

## 实施顺序

1. 加 `_extract_coco_acp_last_chunk_flag` helper（或直接内联）
2. `_TraeAcpClient.read_next_message` 加 `poll_timeout_seconds` 参数
3. `_TraeAcpPromptStream` 构造签名 + `__iter__` 重写
4. `CocoRunner.__init__` / `_execute_prompt` 对接
5. 现有 coco test 的 `FakeSession.read_next_message` 签名微调
6. 新增两条 regression test
7. 跑 coco 子集确认
8. 跑 broad sweep
9. 更新 validation
