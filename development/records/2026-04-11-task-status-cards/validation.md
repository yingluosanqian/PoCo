# Validation

## 验证方法

- `python3 -m unittest tests/test_card_dispatcher.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_client.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py tests/test_agent_runner.py tests/test_task_dispatcher.py tests/test_task_notifier.py`
- `python3 -m compileall poco tests`
- 单测验证 `task_status` waiting card 的 `Approve` / `Reject`
- 单测验证 `task.approve` / `task.reject` callback
- 单测验证 notifier 发送 interactive task status card

## 结果

- `FeishuTaskNotifier` 现在会在等待确认和终态时发送 `task_status` interactive card
- 等待确认卡已提供 `Approve` / `Reject`
- `task.approve` 已接入现有确认主链，并触发异步 `dispatch_resume`
- `task.reject` 已接入现有确认主链，并把任务置为 `cancelled`

## 是否通过

通过当前轮目标。

## 残留问题

- 当前仍是新增通知卡，不是原卡片原位更新
- 结果卡仍是最小摘要，不是 richer result view
- `Use Recent` 仍未接入真实写路径
