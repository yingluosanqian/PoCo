# Validation

## 已验证

- 真实 `codex app-server` 短 turn 仍会发完整链路：`commentary/final_answer` item -> `thread/status=idle` -> `turn/completed`
- 真实 `codex app-server` 的 tool turn 会发 `commentary -> commandExecution -> final_answer -> turn/completed`
- `CodexAppServerRunner` 继续把 `turn/completed` 当成首选成功信号
- 若已收到 `phase=final_answer`，且随后没有新的同 turn 活动，runner 现在会在短 settle 窗口后完成
- 非 `final_answer` 的 `agentMessage` 文本不会被当作 `raw_result`
- 若 `final_answer` 之后还有新的 command / reasoning / agent activity，settle 候选会被清掉，不会提前 complete
- 共享 transport 下，同工作目录复用 transport、不同 reasoning effort 拆分 transport 的行为保持不变

## 2026-04-16 后续修正：settle 不再依赖静默消息窗口

### 问题补充

- 原实现把 settle 判定嵌在 `read_next_message` 返回 `None` 的分支里
- `codex app-server` 在 `final_answer` 之后仍可能持续发送非 disarm 的小消息（如 `thread/tokenUsage/updated`、未识别 method、`thread/status=idle` 等）
- 这类消息让 0.5s 读阻塞永远返回非 None，原 settle 路径永远进不来
- 实际现象：task 输出已结束，card 长期停在 `[Running]`，直到 900s 超时

### 修正

- settle 判定移到 while 循环顶部，每轮迭代都评估一次
- 为保留 decision 里 "随后没有新的同 turn 活动才允许完成" 的语义，引入 `candidate_tick_seen` 闸门：arm 所在的那一轮不 fire settle，必须再走一轮循环；任何一次 arm 都会重置该闸门
- decision 里 "活动" 的语义含义收紧为 "会清掉 candidate 的事件"（如 `item/started(reasoning/commandExecution/agentMessage)`、`thread/status=active` 等），而心跳类消息不再阻塞 settle
- 新增三处 INFO 日志（arm candidate / settle fallback 完成 / `turn/completed` 完成），下次再卡 Running 可从日志分辨路径

### 新增测试

- `test_app_server_runner_completes_via_top_of_loop_settle_when_heartbeats_prevent_quiet_window`
  - 构造 `final_answer` 后无限流 `thread/tokenUsage/updated` 心跳的 fake stream
  - 原实现会死循环直到 timeout
  - 修正后在 ≤3 次 `read_next_message` 内通过 settle 兜底完成

## 测试

- `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'app_server_runner'`
  - `17 passed, 27 deselected`
- `uv run --extra dev pytest -q tests/test_agent_runner.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py`
  - `83 passed`
