# Problem

PoCo 当前虽然已经能在重启后恢复 `project/workspace/task`，但还没有产品级连续性交互对象。

当前缺口表现为：

- `task` 仍是主要长期对象
- `workspace` 仍然缺少真实 `active session`
- 新 task 创建时没有稳定 session 归属
- 跨 task 的最小 handoff 信息没有沉淀点

这会让“连续协作”停留在概念层，而不是运行态事实。
