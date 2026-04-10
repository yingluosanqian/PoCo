# Validation

## 验证方法

- `python3 -m unittest tests/test_card_dispatcher.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_client.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py tests/test_agent_runner.py tests/test_task_dispatcher.py tests/test_task_notifier.py`
- `python3 -m compileall poco tests`
- 单测验证 `task.submit` 返回 `task_status`
- 单测验证 task 保存当前 card 的 message id
- 单测验证 workspace latest task 入口

## 结果

- `task.submit` 现在会直接把当前 card 替换成 `task_status`
- 新 task 已会保存当前 card 的 `source_message_id`
- notifier 后续状态变化已可优先更新这张 card
- workspace 首卡已可打开 latest task

## 是否通过

通过当前轮目标。

## 残留问题

- workspace 首卡仍不会主动跟随 task 状态原位更新
- latest task 仍基于内存 task state
- richer result view 仍未实现
