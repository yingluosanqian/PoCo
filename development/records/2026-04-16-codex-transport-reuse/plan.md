# Plan

## 目标

1. 把 `transport_idle_seconds` 默认拉长到 1800s 且变成可配置
2. 新增后台预热 API 和 MultiAgentRunner 层的分发
3. 在 `workspace.apply_agent` 处挂一个预热 hook

## 范围

- `poco/config.py`：Settings 新增 `codex_transport_idle_seconds`
- `poco/agent/factory.py`：新增 `codex_transport_idle_seconds` 参数
- `poco/main.py`：从 settings 读取并传入
- `poco/agent/codex_app_server.py`：新增 `warm(workdir, reasoning_effort)` 方法，实现后台线程预热
- `poco/agent/stub.py`：`MultiAgentRunner.warm(backend, workdir, reasoning_effort)` 分发
- `poco/task/controller.py`：`TaskController.warm_runner_for_project(project)` helper
- `poco/interaction/card_handlers.py`：`_apply_agent` 末尾调用 `warm_runner_for_project`
- 测试：
  - `tests/test_config.py` 覆盖新字段
  - `tests/test_agent_runner.py` 覆盖 `CodexAppServerRunner.warm` 幂等 + cache 写入
  - `tests/test_card_gateway.py` 覆盖 apply_agent 触发 warm

## 不在范围内的内容

- 不改其他 backend 的 warm 行为（默认 no-op）
- 不改 `_acquire_transport` / `_release_transport`
- 不添加 `task.open_composer` hook（可作后续）
- 不改 `AgentRunner` Protocol 的必选方法（warm 是可选，通过 getattr 嗅探）

## 风险点

- warm 后台线程和主 `_acquire_transport` 并发争用同一 cache_key：靠"先到先得 + 后到者清理自己的重复"策略规避
- env override 解析遵循 `_setting_int` 约定
- warm 失败不抛出，只 log；既有测试不应感知到 warm 调用（除非显式 patch）
- hook 在 `_apply_agent` 末尾触发，不能阻塞 card 响应

## 验收标准

- `uv run --extra dev pytest -q tests/test_config.py`：新字段测试通过，原测试不变
- `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'app_server'`：原 17 条 + 新增 warm 测试全绿
- `uv run --extra dev pytest tests/test_agent_runner.py tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_debug_api.py tests/test_health.py tests/test_card_gateway.py tests/test_feishu_client.py tests/test_config.py`：全绿
- `grep -n 'POCO_CODEX_TRANSPORT_IDLE_SECONDS' poco tests` 命中 config + 测试

## 实施顺序

1. 加 Settings 字段 + factory 参数 + main 注入 + config test
2. 加 `CodexAppServerRunner.warm` + 单测
3. 加 `MultiAgentRunner.warm` 分发
4. 加 `TaskController.warm_runner_for_project`
5. 加 `_apply_agent` 的 hook + 对应 card_gateway 测试
6. 跑完整 broad sweep
7. 更新 validation
