# Decision

本轮采用最小持久化方案：

- 默认状态后端切换为 `sqlite`
- 持久化 `project`
- 持久化 `workspace context`
- 持久化 `task`

边界如下：

- 不在本轮实现完整 `session` store
- 不在本轮实现跨进程可恢复 worker
- 仅在启动时把 `created/running` task 标记为被重启打断

结论上，PoCo 先保证“重启后还能认出已有 workspace”，再进入完整 session continuity。
