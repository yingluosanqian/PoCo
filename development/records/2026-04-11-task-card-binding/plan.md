# Plan

## 本轮计划

- `task.submit` 创建 task 时记录当前 `source_message_id`
- `task.submit` 返回 `task_status`，不再退回 workspace
- 给 workspace 增加 latest task 汇总和 `task.open`
- 补足 gateway / renderer / notifier 自动化测试

## 完成标准

- composer 提交后，当前卡直接变成 task status
- 后续 notifier 能优先更新这张卡
- workspace 存在 latest task 时能打开它
