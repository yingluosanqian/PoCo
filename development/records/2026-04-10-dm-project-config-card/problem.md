# Problem

## 当前状态

- DM 已有 project list card
- `project.open` 仍停留在较薄的 detail 视图

## 问题定义

PoCo 当前缺少真正承接 project 级慢变量的 `DM Project Config Card`，导致 `agent`、`repo`、`default workdir` 虽然已有设计归属，但在实际交互中还没有稳定入口。

## 不是的问题

- 不是这轮就实现真实 repo 绑定和 workdir 写入的问题
- 不是这轮就实现 agent migration 的问题
