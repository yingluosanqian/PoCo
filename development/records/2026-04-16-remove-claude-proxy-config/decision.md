# Decision

## 问题

用户不再需要通过卡片表单/task config 采集 `anthropic_base_url` 与 `anthropic_api_key`。

## 当前决策

直接删除这两个通路，不保留过渡期。

### 改动点

- `poco/agent/catalog.py`：从 `claude_code` 的 `config_fields` 元组里删掉两个 `BackendConfigField` 条目
- `poco/agent/claude_code.py::_execute_prompt`：删掉读取 `effective_backend_config["anthropic_*"]` 并往 env 注入的 5 行代码
- `tests/test_agent_runner.py::test_claude_runner_injects_anthropic_proxy_env`：整条删除（验证的正是被移除的行为）
- `tests/test_card_gateway.py::test_workspace_apply_agent_persists_claude_proxy_settings`：整条删除
- `tests/test_feishu_client.py::test_workspace_choose_agent_card_contains_claude_proxy_inputs`：整条删除

### 不改动

- `poco/env_inventory.py`：`/debug/env` 里继续列 `ANTHROPIC_*` 三个 key。claude CLI 仍会读这些环境变量，PoCo 只是不再注入而已；端点的诊断用途不变
- `tests/test_debug_api.py`：其断言依赖 env_inventory 的白名单，不变
- sqlite 里已存的 project `backend_config` 残留字段：保留不动（inert，不会被新 runner 消费；不加迁移脚本以免破坏）
- 历史 record 文件里的文字引用：保留不动（记录是历史事实）

## 为什么这样选

- **不留过渡期**：字段本来就是"用户 opt-in"，没有存量系统依赖；保留只会让用户被过期 UI 迷惑
- **env_inventory 保留**：三个 env 对 claude CLI 仍有效，端点的价值是"诊断 PoCo 进程继承了什么"，和"PoCo 是否注入"是两个问题
- **sqlite 残留不动**：inert 字段零伤害，迁移脚本带风险

## 风险

- 如果生产环境里真的有用户靠这条卡片表单在用，卡片一关他们就要改走环境变量。用户明确确认了不再需要
- 删 3 条 test 后 broad sweep 总数会掉 3（从 105 掉到 102）。这是正常的"功能删除 → 相关用例同步删除"
