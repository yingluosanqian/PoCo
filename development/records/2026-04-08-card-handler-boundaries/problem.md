# Problem

## 背景

PoCo 已经有 card-first 方向、最小信息架构、统一 action intent 概念和 refresh mode，但还没有把它们变成真正可编码的后端接口边界。

没有这一步，后续实现会出现三个高风险问题：

- payload 字段随写随加
- handler 职责混乱
- 重复点击和回调重试没有幂等规则

## 相关需求

- 最小而稳定的 action payload
- 清楚的 handler ownership
- 可预测的幂等策略

## 当前状态

- 当前只有 `scope/kind/target_id/source_surface` 级别的抽象描述
- 当前没有定义请求 id、actor、surface id 等最小字段
- 当前没有把 project/session/task handler 切开
- 当前没有定义重复动作该如何处理

## 问题定义

PoCo 当前缺少一套足够明确的卡片回调 payload 结构、handler 归属边界和幂等约束，导致 card-first 设计还不能安全进入实现。

## 为什么这是个真实问题

- 如果 payload 不稳定，前后端和卡片 schema 会一起漂移
- 如果 handler 边界不清，project/session/task 的职责会再次混在一起
- 如果幂等规则缺失，审批和任务提交会成为高风险操作

## 不是什么问题

- 不是最终数据库 schema 的问题
- 不是具体函数命名风格的问题
- 不是实现阶段再“顺手处理”的问题

## 证据

- 当前 records 还未定义 payload 最小字段格式
- 当前 records 还未定义异常动作和幂等处理策略
