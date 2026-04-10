# Validation

## 验证方法

- `python3 -m unittest tests/test_card_dispatcher.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_client.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py`
- `python3 -m compileall poco tests`
- 单测模拟 DM `project.add_dir_preset`
- 单测模拟群 `workspace.apply_preset_dir`

## 结果

- DM `Manage Dir Presets` 已可新增 project-level preset
- 群 `Choose Preset` 已可展示并应用 preset
- 应用后 workspace context 会更新为 `source=preset`

## 是否通过

通过当前轮目标。

## 残留问题

- preset 仍不支持删除或重命名
- `Use Recent` 仍未接入真实写路径
- task 执行链路仍未消费新的 `active_workdir`
