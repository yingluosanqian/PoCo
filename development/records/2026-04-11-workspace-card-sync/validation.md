# Validation

## 验证方法

- `python3 -m unittest tests/test_card_dispatcher.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_client.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py tests/test_agent_runner.py tests/test_task_dispatcher.py tests/test_task_notifier.py`
- `python3 -m compileall poco tests`
- 单测验证 workspace.open 绑定 `workspace_message_id`
- 单测验证 bootstrap 首卡绑定 `workspace_message_id`
- 单测验证 task notifier 会顺手更新 workspace card

## 结果

- `Project` 已保存最小 `workspace_message_id`
- workspace.open / refresh 已会绑定当前 workspace card message
- bootstrap 首卡发送后也会绑定 workspace message
- task notifier 现在会在 task 状态变化时同步刷新 workspace latest task 区块

## 是否通过

通过当前轮目标。

## 残留问题

- `workspace_message_id` 仍是内存态
- 当前还没有多 workspace card 的冲突策略
- richer workspace live model 仍未实现
