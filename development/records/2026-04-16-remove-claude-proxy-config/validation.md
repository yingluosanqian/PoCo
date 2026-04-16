# Validation

## 验证目标

确认 `anthropic_base_url` / `anthropic_api_key` 的用户采集路径已完整删除：

1. 卡片表单不再包含这两个字段
2. `ClaudeCodeRunner._execute_prompt` 不再读 `effective_backend_config["anthropic_*"]`、不再往子进程 env 注入
3. 三条对应测试同步删除（验证的正是被移除的行为）
4. 其它路径（strong terminal、claude 完成兜底、permission_mode 表单、`/debug/env` 诊断）全部零回归

## 验证方法

### 代码层

改动：

- `poco/agent/catalog.py`：从 `claude_code` 的 `config_fields` 元组里移除两个 `BackendConfigField`
- `poco/agent/claude_code.py::_execute_prompt`：移除 5 行 env 注入代码

删除测试：

- `tests/test_agent_runner.py::test_claude_runner_injects_anthropic_proxy_env`
- `tests/test_card_gateway.py::test_workspace_apply_agent_persists_claude_proxy_settings`
- `tests/test_feishu_client.py::test_workspace_choose_agent_card_contains_claude_proxy_inputs`

不改动：

- `poco/env_inventory.py`：`/debug/env` 白名单仍然列 `ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN`（这些变量依然被 claude CLI 从进程环境读取，端点的诊断用途不变）
- `tests/test_debug_api.py`：其断言依赖上面这个白名单，保持不变
- sqlite 里存量 project `backend_config` 残留字段：保留不动（inert，新 runner 不再读）

### 验证搜索

```
grep -rn 'anthropic_base_url\|anthropic_api_key' poco/ tests/
```
无输出，确认用户侧采集路径完全清除。

## 结果

- `uv run --extra dev pytest -q tests/test_agent_runner.py -k 'claude_runner'`
  - `5 passed, 40 deselected`（上轮 baseline 是 6，删除 `test_claude_runner_injects_anthropic_proxy_env` 后剩 5，符合预期）
- `uv run --extra dev pytest tests/test_agent_runner.py tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_debug_api.py tests/test_health.py tests/test_card_gateway.py tests/test_feishu_client.py`
  - `177 passed`

## 是否通过

通过。用户侧采集路径完全清除，claude CLI 仍可以通过进程环境读 `ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY`（这是运维职责），`/debug/env` 诊断入口保持可用。

## 残留问题

- sqlite 里存量 project `backend_config` 残留的这两个键值不会被 runner 读，也不会再被卡片表单展示。无功能影响，但理论上占用一点存储。不主动清理以避免迁移脚本带来的风险
- `tests/test_demo_cards.py` 4 条 daemon-thread race 失败依然存在（和本轮无关）

## 是否需要回滚/继续迭代

不需要。可以回到 `coco` 的 completion 语义审计队列。
