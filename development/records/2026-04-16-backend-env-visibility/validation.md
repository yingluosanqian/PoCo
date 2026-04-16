# Validation

## 验证目标

确认新增 `/debug/env` 端点能真实解决"PoCo 进程有没有继承到某个关键环境变量"的排障盲区，同时不引入 value 泄漏风险。

## 验证方法

### 代码层

- 新增 `poco/env_inventory.py`：定义白名单（codex / claude_code / cursor_agent / coco / proxy 五类）和 `build_env_inventory()` 聚合函数
- `poco/main.py` 新增路由 `GET /debug/env`
- `poco/main.py` 在 `/health` 的 warnings 里追加 `/debug/env` 引导提示

### 测试层

`tests/test_debug_api.py` 新增 5 条用例：

- `test_env_endpoint_reports_present_and_length`：白名单内已设置的 key 正确汇报 `present=True` 和值长度
- `test_env_endpoint_marks_missing_keys_absent`：白名单内未设置的 key 正确汇报 `present=False` 和 `length=0`
- `test_env_endpoint_never_leaks_values`：响应正文不出现预设 secret、代理 host、model 名等任何 value 片段
- `test_env_endpoint_only_contains_whitelisted_keys`：响应里的 key 集合严格等于白名单集合
- `test_health_warnings_mention_env_debug_endpoint`：`/health` 的 warnings 里包含 `/debug/env` 引导字符串

## 结果

- `uv run --extra dev pytest -q tests/test_debug_api.py`
  - `8 passed`（原有 3 条 + 新增 5 条）
- `uv run --extra dev pytest -q tests/test_health.py tests/test_debug_api.py tests/test_agent_runner.py`
  - `53 passed`

## 是否通过

通过。

## 残留问题

- `tests/test_demo_cards.py` 的 4 条用例在 clean `main` 上就已失败（daemon reconcile loop 和 tempdir cleanup 的竞态，sqlite 文件被删后线程仍在读），和本轮改动无关
- 白名单目前是常量，未来新增 backend 时需要手动同步；决策里已说明这是有意识收敛
- `/debug/env` 未加鉴权，与既有 `/debug/feishu` 同级，继承相同的暴露面假设

## 是否需要回滚/继续迭代

不需要回滚。后续可以做的增量：

- 把白名单按 backend 下沉到各 backend class 自己声明，main 只做聚合
- `poco status` CLI 增量接入这同一份数据源
- 独立 record 讨论"per-project env 注入"的配置路径
