# Problem

## 当前状态

- 群里已经有 workspace overview card
- 但还没有一张专门承接 current workdir 的切换卡

## 问题定义

PoCo 当前缺少群工作面的 `Workdir Switcher Card`，导致 `working dir` 虽然在 ownership 上已被定义为 session 级变量，但用户仍没有就地确认和切换它的卡片入口。

## 不是的问题

- 不是这轮就实现真实 session 持久化的问题
- 不是这轮就实现真实目录写入的问题
