# Plan

## 目标

把卡片后端交互进一步收敛成可实现的 payload 与 handler 设计。

## 范围

- 定义 ActionIntent 最小 payload
- 定义 handler ownership
- 定义最小幂等规则

## 不在范围内的内容

- 具体 Python 类和模块实现
- 数据库落库策略
- 完整异常码体系

## 风险点

- payload 字段可能过多
- handler 切分可能过碎
- 幂等要求可能被设计成“一刀切”

## 验收标准

- 已明确最小 payload 字段
- 已明确 project/session/task/workspace 的 handler 边界
- 已明确哪些动作默认要求幂等
- 足以支撑下一轮实现设计

## 实施顺序

1. 固化 need/problem/decision
2. 形成 payload/handler/idempotency design
3. 回写稳定层设计摘要
4. 下一轮进入实现级模块设计
