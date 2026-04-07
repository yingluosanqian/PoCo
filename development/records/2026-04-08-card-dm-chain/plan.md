# Plan

## 目标

实现一条最小 DM card 链路。

## 范围

- project 内存模型
- project controller
- DM project handlers
- Feishu card renderer
- Feishu card gateway
- demo card endpoints
- 自动化测试

## 不在范围内的内容

- 群工作区完整交互
- 真实飞书端到端验证
- project/session/task 全量 handlers

## 风险点

- renderer 仍然只是最小模板，不等于最终卡片样式
- gateway 仍需后续与真实飞书卡片协议进一步对齐

## 验收标准

- DM project list card 可生成
- card action 可创建 project 并返回 project detail card
- 测试通过

## 实施顺序

1. 落 project 领域模型
2. 落 handlers / renderer / gateway
3. 暴露 demo endpoints
4. 补测试与验证
