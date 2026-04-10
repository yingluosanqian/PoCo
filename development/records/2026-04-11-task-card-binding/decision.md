# Decision

## 当前决策

先做两条收敛：

- `task.submit` 直接返回 `task_status`，并把当前 `source_message_id` 绑定为 task 的 `notification_message_id`
- `workspace_overview` 在存在 latest task 时提供 `Open Latest Task`

## 为什么这样选

- 这能让 composer -> status -> notifier update 形成单消息主链
- 同时让 workspace 有稳定入口回到 latest task
- 不需要先引入更复杂的 card graph 管理

## 风险

- 当前 latest task 仍来自内存 task state，重启后不可恢复
- workspace 首卡本身仍不会随着 task 状态自动原位更新
