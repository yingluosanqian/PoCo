# Decision

本轮采用最小 session 方案：

- 一个 `project` 默认只有一个当前 `active session`
- 新 task 自动挂到当前 active session
- 若 project 尚无 session，则在第一次 task 创建时自动创建
- session 持久化最小 handoff 信息：
  - `latest_task_id`
  - `latest_prompt`
  - `latest_result_preview`
  - `latest_task_status`

边界：

- 不实现 session 分叉
- 不实现 `session.continue` 显式动作
- 不实现 backend resume handle
