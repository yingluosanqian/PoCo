# Problem

## 当前状态

- project 已经有 `backend`、`repo`、`workdir` 等字段
- DM 和群的卡片交互已经开始成形
- 但系统还没有明确：
  - `agent` 属于哪一层对象
  - `working dir` 属于哪一层对象
  - 这两者应该分别在 DM 还是群里由用户选择

## 问题定义

PoCo 当前缺少一套正式的执行上下文配置模型，导致 `agent` 和 `working dir` 的归属层级、切换成本与交互入口都不清楚，容易破坏上下文连续性或让工作流变得笨重。

## 为什么这是真问题

- `agent` 和 `working dir` 决定了任务到底“由谁做”以及“在哪做”
- 它们如果被放错层级，会直接破坏 session continuity
- 它们如果被放错入口，会把 DM control plane 和 group workspace 再次混在一起

## 不是的问题

- 不是现在立刻实现 repo/workdir 绑定的问题
- 不是所有高级执行参数都必须现在一起暴露给用户的问题
- 不是为了灵活性就允许 task 级随意重配置的问题
