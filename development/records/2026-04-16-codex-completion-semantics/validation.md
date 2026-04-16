# Validation

## 已验证

- `CodexAppServerRunner` 不再在收到 `thread/status=idle` 后立即判定完成，而是进入 settle 窗口等待后续事件
- 若 `idle` 之后还有新的当前 turn 输出，runner 会继续消费输出，而不是提前 `completed`
- 若只有 delta 输出、没有明确 terminal event，runner 现在会在长静默后兜底完成
- 若 app-server 消息流提前结束但已拿到输出，runner 会用现有输出收口，而不是抛出异常
- 共享 transport 下，无关 thread/turn 的消息不再清掉当前 task 的候选收口状态

## 测试

- `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'app_server_runner'`
  - `12 passed, 27 deselected`
- `uv run --extra dev pytest -q tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py`
  - `39 passed`
