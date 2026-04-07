# Design

## 设计目标

在保留“project 需要独立工作区”的前提下，为 PoCo 增加明确的 project 管理入口，使用户能在单聊中完成 project lifecycle 管理，再把正式执行导向 project 群。

## 核心抽象

### 1. DM Control Plane

单聊作为 project 管理入口。

职责：

- 创建 project
- 列出和查看 project
- 为 project 创建或绑定群
- 管理 project 的长期配置

### 2. Group Workspace

群聊作为 project 的正式执行空间。

职责：

- 承载 `/run`、`/status`、`/approve`、`/reject`
- 接收状态通知和结果回推
- 作为多人围绕同一 project 观察工作的默认空间

### 3. Project Lifecycle

表示一个 project 从创建到绑定工作区的长期流程。

至少应包含：

- project 元数据
- 绑定的 group 信息
- 默认 backend / repo / workdir 配置

## 模块/接口影响

- `interaction`
  未来需要区分 DM 管理命令与群内执行命令
- `platform/feishu`
  未来需要识别消息来自单聊还是群聊，并路由到不同入口语义
- `storage`
  未来需要支持 project metadata 和 group binding
- `task/session`
  继续在 project 之下工作，不再把单聊直接当 project 执行入口

## 状态变化

当前认知：

- project 与群直接绑定，但管理入口未定义

后续建议：

1. 用户在 DM 中创建 project
2. 用户在 DM 中触发“建群/绑定群”
3. project 获得唯一 group workspace
4. 群中的命令默认落到该 project
5. project 下继续承载 session 和 task

## 方案比较

### 方案 A：单聊既管理又执行

优点：

- 看似入口更少

缺点：

- 单聊容易被执行噪声污染
- project 边界仍不稳定

### 方案 B：单聊管理，群执行

优点：

- 职责分工清晰
- 同时满足管理便利和执行清晰

缺点：

- 需要定义两段式用户流程

### 方案 C：只保留群执行，不定义单聊管理

优点：

- 执行模型简单

缺点：

- 缺少自然的 control plane

## 最终方案

采用方案 B。

单聊承担 control plane；群承担 project workspace。这样 project 管理动作与 project 执行动作分离，但仍通过同一个 bot 体系保持连贯。

## 风险与兼容性

- DM 与群之间的跳转体验需要后续补设计
- 若未来支持更多平台，需要为“control plane”和“workspace”寻找等价入口
- 单聊若保留个人快速执行能力，需要明确它与正式 project workspace 的差异
