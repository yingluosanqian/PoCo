# Plan

## 本轮计划

- 新增 `task_status` card renderer
- 扩展 `TaskIntentHandler` 支持 `task.approve` / `task.reject`
- 让 `FeishuTaskNotifier` 优先发送 interactive task status card
- 补足 approve/reject card callback 和 notifier 自动化测试

## 完成标准

- 等待确认任务会收到带 `Approve` / `Reject` 的卡片
- 完成任务会收到结果状态卡
- 点击 `Approve` 会触发异步 resume
- 点击 `Reject` 会把任务转成 cancelled
