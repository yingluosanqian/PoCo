# Plan

## 范围

- 定义 `DM Project Config Card` 的首屏信息和动作分层
- 定义 `Group Workdir Switcher Card` 的首屏信息和动作分层
- 明确哪些信息常驻、哪些信息二级展开、哪些动作应谨慎隐藏

## 不在范围内

- 不实现真实卡片 schema
- 不实现 backend 存储或 session 持久化
- 不实现 agent migration 的完整流程

## 验收标准

- DM 卡片上 agent、repo、default workdir 的呈现优先级清楚
- 群卡片上 current workdir 的呈现和切换路径清楚
- 方案不会让群工作面承担 project 级重配置
