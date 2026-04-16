# Validation

## 已验证

- 真实 `codex app-server` 短 turn 仍会发完整链路：`commentary/final_answer` item -> `thread/status=idle` -> `turn/completed`
- 真实 `codex app-server` 的 tool turn 会发 `commentary -> commandExecution -> final_answer -> turn/completed`
- `CodexAppServerRunner` 继续把 `turn/completed` 当成首选成功信号
- 若已收到 `phase=final_answer`，且随后没有新的同 turn 活动，runner 现在会在短 settle 窗口后完成
- 非 `final_answer` 的 `agentMessage` 文本不会被当作 `raw_result`
- 若 `final_answer` 之后还有新的 command / reasoning / agent activity，settle 候选会被清掉，不会提前 complete
- 共享 transport 下，同工作目录复用 transport、不同 reasoning effort 拆分 transport 的行为保持不变

## 测试

- `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'app_server_runner'`
  - `16 passed, 27 deselected`
- `uv run --extra dev pytest -q tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py`
  - `39 passed`
