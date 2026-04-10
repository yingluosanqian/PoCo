# Validation

## 验证方法

- `python3 -m unittest tests/test_card_dispatcher.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_client.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py`
- `python3 -m compileall poco tests`
- 单测模拟先写入 manual context，再点击 `workspace.use_default_dir`
- 单测验证未配置 default workdir 时返回 warning

## 结果

- `workspace.use_default_dir` 已可更新 in-memory workspace context
- `workspace.open` 与 `workspace.open_workdir_switcher` 已开始读取当前 context
- 未配置 default workdir 时会返回明确 warning

## 是否通过

通过当前轮目标。

## 残留问题

- context 仍为 in-memory，重启会丢失
- task 执行链路尚未消费 `active_workdir`
- 其他三条 workdir 路径仍未接真实写入
