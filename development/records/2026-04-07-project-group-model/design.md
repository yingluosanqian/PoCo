# Design

## 设计目标

为 PoCo 建立清晰的正式交互容器模型，避免多个 project 混在同一聊天空间中，并与此前的 `session/handoff` 设计兼容。

## 核心抽象

### 1. Group-bound Project

飞书群作为一个 project 的正式消息容器。

职责：

- 提供 project 的默认消息归属空间
- 承接该 project 的任务发起、状态通知和确认动作
- 作为多人围绕同一 project 观察与协作的基础边界

### 2. Project

表示一条长期工作的归属对象。

职责：

- 绑定代码仓、执行器配置、默认工作目录等长期属性
- 作为 session 的上层容器

### 3. Session

表示 project 下的一段连续工作流。

职责：

- 把若干 task 组织成可恢复的连续过程
- 承接 handoff context

### 4. Task

表示一次具体 agent 执行单元。

职责：

- 执行具体 prompt / action
- 回写状态和结果

## 模块/接口影响

- `platform/feishu`
  未来需要识别群身份，并把群映射到 project
- `interaction`
  未来需要以 project 为默认归属，而不是直接按聊天上下文创建 task
- `storage`
  未来需要新增 group-project binding 和 project store
- `task/session`
  session 必须调整为 project 下级对象

## 状态变化

当前：

- 消息直接进入 task 级处理

后续建议：

1. 飞书消息先识别来源群
2. 群映射到唯一 project
3. project 决定当前 session 或新建 session
4. session 再创建或推进 task

## 方案比较

### 方案 A：单聊天框切 project

优点：

- 表面上更灵活

缺点：

- 认知负担高
- 手机场景易混乱

### 方案 B：一个 project 一个群

优点：

- 边界天然清晰
- 默认归属稳定
- 适合 MVP

缺点：

- 初始化成本更高

### 方案 C：多入口并存

优点：

- 看起来能力最全

缺点：

- 当前过度复杂

## 最终方案

采用方案 B。

PoCo 的正式交互主路径中，一个飞书群绑定一个 project；project 之下再承载 session 和 task。这样既保持了 project 边界清晰，也不会把群直接误用为 session。

## 风险与兼容性

- 单聊后续若要承接正式 project 操作，需要额外定义例外语义
- 群成员变化未来会带来 project 权限同步问题
- 若未来支持 Slack 等平台，需要重新映射“project 容器”的等价物
