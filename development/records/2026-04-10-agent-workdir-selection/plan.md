# Plan

## 范围

- 定义 `project / session / task` 三层上下文归属
- 定义 `agent` 与 `working dir` 的默认 ownership
- 定义 DM 与群卡片中各自负责的配置动作
- 为后续实现提供最小信息架构方向

## 不在范围内

- 不实现真实 repo/workdir 绑定
- 不实现 agent migration
- 不实现 session 持久化或 context resume 机制

## 验收标准

- 能清楚回答 `agent` 属于哪一层
- 能清楚回答 `working dir` 属于哪一层
- 能清楚回答二者分别应该在 DM 还是群里配置
- 方案不会破坏既有 `DM control plane + group workspace` 决策
