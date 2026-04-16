# Validation

## 验证目标

1. `POCO_CODEX_TRANSPORT_IDLE_SECONDS` 可控且默认 1800s
2. `CodexAppServerRunner.warm` 能后台启动一次 transport，重复调用幂等
3. `MultiAgentRunner.warm` 按 backend 分发，不支持的 backend 静默返回 False
4. `TaskController.warm_runner` 在 runner 不支持 warm 时返回 False 不抛
5. `workspace.apply_agent` 的 card 动作在有 workdir 时会触发 `task_controller.warm_runner`，无 workdir 时不触发
6. 所有现有测试零回归

## 验证方法

### 代码层

- `poco/config.py::Settings` 新增 `codex_transport_idle_seconds: int`，默认 1800，env 变量 `POCO_CODEX_TRANSPORT_IDLE_SECONDS`
- `poco/agent/factory.py::create_agent_runner` 新增同名 int 参数，转成 float 后透传给 `CodexAppServerRunner(transport_idle_seconds=...)`
- `poco/main.py` 从 `settings.codex_transport_idle_seconds` 读取并传入
- `poco/agent/codex_app_server.py`：
  - 新增 `Thread` import
  - `__init__` 新增 `_warming_keys: set[tuple[str, str]]`
  - 新增 `warm(workdir, reasoning_effort)` 方法：cache hit / 已在 warming → return False；否则记入 `_warming_keys`，起 daemon thread 调 `_start_transport`；成功写入 cache，失败静默 log
  - 竞态处理：warm 结束时检查 cache，若已被 `_acquire_transport` 抢先填入活 transport，则清理自己的副本
- `poco/agent/stub.py::MultiAgentRunner` 新增 `warm(backend, workdir, reasoning_effort)` 分发，通过 `getattr` 嗅探子 runner 的 warm 方法
- `poco/task/controller.py::TaskController` 新增 `warm_runner(backend, workdir, reasoning_effort)` 薄封装，参数不全或 runner 不支持返回 False
- `poco/interaction/card_handlers.py::WorkspaceIntentHandler._apply_agent` 末尾：
  - 计算 `warm_workdir = (context.active_workdir if context else None) or project.workdir`
  - 从 `project.backend_config` 读取 `reasoning_effort`
  - 调 `self.task_controller.warm_runner(backend=project.backend, workdir=warm_workdir, reasoning_effort=...)`
  - 只有 warm_workdir 非空才调用

### 测试层

新增 6 条测试：

- `tests/test_config.py`
  - `test_codex_transport_idle_seconds_has_thirty_minute_default`
  - `test_codex_transport_idle_seconds_respects_env_override`
- `tests/test_agent_runner.py`
  - `test_app_server_runner_warm_schedules_background_start_once`：三次 warm 调用合计一次 `_start_transport`，验证幂等 + cache 写入
  - `test_app_server_runner_warm_swallows_start_failure`：`_start_transport` 抛 RuntimeError 时 warm 不抛，cache 不被污染，`_warming_keys` 正确清理
- `tests/test_card_gateway.py`
  - `test_workspace_apply_agent_triggers_runner_warm`：project 有 workdir 时 warm_runner 被正确参数调用一次
  - `test_workspace_apply_agent_skips_warm_when_workdir_unknown`：project 无 workdir 时不触发

### 验收命令

1. `uv run --extra dev pytest -q tests/test_config.py`
2. `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'warm'`
3. `uv run --extra dev pytest -q tests/test_card_gateway.py -k 'apply_agent'`
4. `uv run --extra dev pytest tests/test_agent_runner.py tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_debug_api.py tests/test_health.py tests/test_card_gateway.py tests/test_feishu_client.py tests/test_config.py`

## 结果

- `tests/test_config.py`：4 passed（原 2 + 新增 2）
- `tests/test_agent_runner.py -k warm`：3 passed（1 现有 coco reuse + 新增 2 codex warm）
- `tests/test_card_gateway.py -k apply_agent`：2 passed（新增 2）
- broad sweep（上面列出的 10 个测试文件）：**187 passed**（上轮 179 + 新 8）

## 是否通过

通过。idle 可配、warm 行为幂等且抑制失败、hook 在正确的时机触发、所有现有测试行为零变化。

## 残留问题

- warm thread 持有 `self._lock` 期间（即 `_start_transport` 的 Popen + initialize 约 2-5s 内）会短暂阻塞其他 `_acquire_transport`。现有 `_acquire_transport` 本身也会用 `_start_transport` 在同一把锁里冷起，行为没变得更糟；如果未来要彻底解决这条锁路径，另立 record
- 只挂了 `workspace.apply_agent` 一个 hook。用户没走这条 card 路径（如直接在 DM 新建项目后立刻发群消息）还是会冷起第一次
- coco 的 `transport_idle_seconds=30` 没改（不在本轮范围），如有需要单独一轮
- `tests/test_demo_cards.py` 4 条 daemon-thread race 失败依然存在，与本轮无关

## 是否需要回滚/继续迭代

不需要回滚。后续可以做的增量：

- 加 `task.open_composer` 或 "group 绑 project 后首次 workspace overview 发送" 作为第二、第三个 hook 点
- 考虑 `task.submit` 之前先 warm（对已绑但第一次用的用户覆盖）
- 抽 `transport_idle_seconds` 为通用 backend 参数后也给 coco 放宽
