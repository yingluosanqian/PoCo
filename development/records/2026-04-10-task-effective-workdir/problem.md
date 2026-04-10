# Problem

## 当前状态

- group workspace 已经能维护 `active_workdir`
- task 创建和 Codex 执行仍未消费这份上下文

## 问题定义

PoCo 当前缺少一条从群工作面上下文到 task 执行参数的最小落地链，导致 `working dir = session stance` 还没有成为真实执行行为。

## 不是的问题

- 不是现在就实现完整 session 持久化的问题
- 不是现在就实现 `Use Recent` 的问题
- 不是现在就实现多 backend 动态切换的问题
