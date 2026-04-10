# Problem

## 当前状态

- 群工作区卡片已经能打开 workdir switcher
- workspace context 已能真实修改
- task 执行链已能消费 `effective_workdir`
- 但卡片侧还没有 task composer 和 `task.submit`

## 问题定义

PoCo 当前缺少一条从 group workspace card 到 task 创建与异步派发的最小卡片执行链，导致 card-first 主交互面仍不能独立完成发任务动作。

## 不是的问题

- 不是现在就实现 approval/result 全卡片化的问题
- 不是现在就实现 `Use Recent` 的问题
- 不是现在就实现完整 session timeline 的问题
