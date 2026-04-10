# Validation

## 验证方法

- `python3 -m unittest tests/test_card_dispatcher.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_client.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py tests/test_agent_runner.py tests/test_task_dispatcher.py tests/test_task_notifier.py`
- `python3 -m compileall poco tests`
- 单测验证 Feishu message update API 调用
- 单测验证 notifier 首发后保存 `notification_message_id`
- 单测验证第二次通知优先走 update 而不是 send

## 结果

- `Task` 已保存最小 `notification_message_id`
- `FeishuMessageClient` 已支持 interactive message update
- `FeishuTaskNotifier` 已优先更新已有 task status card，失败时再回退到新发

## 是否通过

通过当前轮目标。

## 残留问题

- `notification_message_id` 目前仍是内存态
- 当前只覆盖 notifier 发出的 task status card
- richer result view 仍未实现
