# Design

## Session 对象

最小字段：

- `id`
- `project_id`
- `created_by`
- `status`
- `latest_task_id`
- `latest_prompt`
- `latest_result_preview`
- `latest_task_status`
- 时间戳

## 生命周期

- 首次在 project 下创建 task 时自动创建 active session
- 后续 task 默认复用该 active session
- task 在创建、确认、完成、失败、被重启打断时，都会同步刷新 session handoff

## 与现有结构的关系

- `project` 继续是长期容器
- `session` 成为 task 的直接上层归属
- `workspace context` 继续承接 session 级 `working dir`
- `task` 继续承接实际执行参数

## 当前显示策略

- workspace overview 直接显示 active session summary
- task 结果仍然原文优先
- session 只提供轻量连续性交接，不替代 task 详情
