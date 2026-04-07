# Plan

## 目标

明确 PoCo 正式交互模型中的 `group -> project -> session -> task` 关系，为下一轮实现提供稳定边界。

## 范围

- 定义飞书群与 project 的绑定关系
- 定义 project、session、task 的层级关系
- 定义单聊在 MVP 阶段的定位
- 为后续实现准备清晰的默认命令归属逻辑

## 不在范围内的内容

- 完整 project 管理后台
- 复杂 project 权限体系
- 多 project 单聊切换命令流
- 卡片式 project 导航界面

## 风险点

- 若群和 project 绑定关系定义不清，后续消息路由仍会混乱
- 若单聊定位不清，正式路径和调试路径会彼此污染
- 若 session 与 project 的边界不清，后续上下文实现容易再次漂移

## 验收标准

- 已明确正式交互主路径采用“一个 project 一个群”
- 已明确 `project / session / task` 的层级关系
- 已明确单聊在 MVP 的临时定位
- 稳定层和本轮 record 足以支撑后续代码设计

## 实施顺序

1. 固化 need/problem/decision
2. 形成最小设计表达
3. 回写稳定层的 decisions/design/state/plan
4. 后续进入实现前再补具体 project 绑定与存储设计
