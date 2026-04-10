# Validation

## 验证方法

- `python3 -m unittest tests/test_card_dispatcher.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_client.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py`
- `python3 -m compileall poco tests`
- 本地 card action 模拟 `project.open` 和 `project.configure_agent`

## 结果

- `project.open` 已返回 `project_config` 视图
- DM project config card 已展示 project 级慢变量摘要
- 配置按钮已可进入只读子卡，并能返回 project config card

## 是否通过

通过当前轮目标。

## 残留问题

- 子卡尚未接真实配置写入
- 群内 `Workdir Switcher Card` 仍未进入实现
