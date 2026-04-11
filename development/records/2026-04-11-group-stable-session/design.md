# Design

## 模型收敛

正式模型改为：

- `DM -> project control plane`
- `Group -> project workspace`
- `Group session = project workspace session`

## Session 语义

session 仍存在，但作用收敛为：

- 承载 task 的稳定上层归属
- 持久化最小 handoff 信息
- 为后续 timeline 提供基础对象

而不再承担：

- 多 session 分叉
- 群内 session 切换
- 群内 session lifecycle 操作

## 交互面

workspace 卡继续显示当前 session 摘要，但不再提供 lifecycle 按钮。
