# Plan

## 本轮计划

- 给 `Task` 增加 `notification_message_id`
- 给 `FeishuMessageClient` 增加 interactive message update
- 让 `FeishuTaskNotifier` 先更新、失败再新发
- 补足 client / notifier 自动化测试

## 完成标准

- 首次 task status 通知后，task 保存 message id
- 后续状态变化优先更新同一张卡
- 更新失败时仍能回退为新发，避免丢通知
