# Plan

## 目标

为 PoCo 的“上下文连续性”问题建立明确边界，使后续实现可以在不引入重型 memory 系统的前提下，支持移动端恢复同一条工作流。

## 范围

- 定义产品级连续性交接上下文由谁维护
- 定义 backend 执行期上下文由谁维护
- 定义下一轮实现所需的最小对象和接口方向
- 明确后续实现应先补哪一层，而不是直接扩展现有 task 模型

## 不在范围内的内容

- 完整聊天记录持久化
- 通用 knowledge base / memory 平台
- 多用户协作冲突解决
- backend 内部上下文协议统一化
- 直接实现 `/continue` 等新指令

## 风险点

- 容易再次把“上下文需求”直接翻译成某个存储实现
- 容易把 session continuity 和 backend execution context 混为一谈
- 若没有明确最小边界，后续实现会在 PoCo 与 backend 之间来回漂移

## 验收标准

- 已明确 PoCo 与 backend 的上下文责任边界
- 已明确下一轮设计需要新增的最小抽象
- 已明确当前不做什么，避免直接滑向重型 memory 系统
- 稳定层与本轮 record 足以支撑后续实现前的设计工作

## 实施顺序

1. 记录 need/problem/decision
2. 形成最小 design 方向
3. 同步稳定层中的 problem/decision/design/state 摘要
4. 待下一轮明确实现预算后，再进入代码设计与实现
