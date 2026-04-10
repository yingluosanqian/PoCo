# Decision

## 当前决策

先落地最小原位更新链：

- `Task` 保存 `notification_message_id`
- notifier 首次发送 `task_status` card 后记录 `message_id`
- 后续优先调用 Feishu `update message` API 原位更新
- 更新失败时回退到新发

## 为什么这样选

- 这能在不重做 task state 的前提下显著减少群内卡片堆积
- 失败时回退新发，风险较低
- 直接复用 Feishu 现有消息更新能力

## 风险

- 当前 `notification_message_id` 仍只在内存里，重启后无法复用
- 当前只更新 notifier 发出的 task status card，不更新 workspace / composer 原卡
