# Design

## 设计目标

在不复制 backend 全量内部记忆的前提下，为 PoCo 增加一层最小产品级连续性交接能力，使移动端用户能够在中断后恢复同一条工作流。

## 核心抽象

### 1. Session

表示一条面向用户的连续工作流归属对象。

职责：

- 绑定一个消息会话或用户工作上下文
- 聚合同一连续目标下的多个 task
- 提供“继续什么”的稳定引用

### 2. Handoff Context

表示 PoCo 在任务之间交接给用户或 backend 的最小连续性信息。

至少应包含：

- 最近任务结论摘要
- 当前未解决问题
- 最近确认历史
- 当前推荐继续点

职责：

- 为移动端展示恢复语义
- 为后续 task 创建提供最小继承上下文
- 不承担 backend 内部推理细节

### 3. Backend Execution Context

表示 backend 自己维护的执行期上下文。

职责：

- 支撑单次或可恢复执行
- 保存 backend 私有的 prompt、scratch、内部状态
- 可选地暴露 resume handle 给 PoCo，但不是产品层唯一依赖

## 模块/接口影响

- `task`
  未来需要从“孤立 task”演进到“task 隶属于 session”
- `interaction`
  未来需要把用户命令路由到 session，而不只是 task
- `agent`
  未来需要明确 backend 是否支持 resume handle / thread id 等可选能力
- `storage`
  未来需要最小 session store，而不是只存 task

## 状态变化

当前：

- 用户命令直接创建 task
- task 独立完成或等待确认

后续建议：

1. 用户命令首先落到一个 session
2. session 决定当前命令是新开工作流还是延续现有工作流
3. task 在执行前获得 handoff context
4. task 结束后回写新的 handoff context

## 方案比较

### 方案 A：只依赖 backend 内部上下文

优点：

- 实现看似最省事

缺点：

- 产品层没有稳定连续性对象
- 多 backend 难统一

### 方案 B：PoCo 自己保存全量对话与推理上下文

优点：

- 表面上控制力最强

缺点：

- 复杂度过高
- 明显超出当前 MVP 约束

### 方案 C：PoCo 持有 session/handoff，backend 持有 execution context

优点：

- 责任边界清晰
- 复杂度可控
- 兼容多 backend 扩展

缺点：

- 需要谨慎定义 handoff 信息的最小集合

## 最终方案

采用方案 C。

PoCo 只维护产品级连续性交接所需的最小 session/handoff 信息；backend 继续维护执行期上下文。两者通过最小交接接口衔接，而不是共享完整内部状态。

## 风险与兼容性

- 初期 handoff 过于简陋时，用户仍可能觉得“上下文断了”
- 不同 backend 若 resume 能力差异太大，PoCo 需要接受能力分层
- 后续若接入多平台，session 身份映射需要重新审视
