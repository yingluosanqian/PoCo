# Validation

当前这轮是交互决策与实现前设计，验证以结构一致性为主。

## 已验证

- 代码现状中，群文本任务链已存在，`/run ...` 当前可直接创建 task
- 代码现状中，DM 普通消息当前优先触发 project list card
- 代码现状中，`task_composer` 只是 task 创建的一条补充路径，不是唯一执行链
- 当前变更的主要影响点确实集中在 `FeishuGateway` 和 `InteractionService`

## 实现后补充验证

- `InteractionService` 现已按 `message_surface` 区分 DM 与 Group 默认语义
- 已绑定 project 的 group 普通文本消息现在会直接创建 task
- group 中未知斜杠命令不会被误当成 prompt，而是回帮助信息
- DM 的普通消息链仍保持 control plane 语义，不会默认创建 task
- 相关单测已覆盖：
  - group 普通文本直接发 task
  - group `/run ...` 兼容路径仍可用
  - group 未知斜杠命令返回 help
  - DM 仍返回 project list card

## 本轮结论

“群普通文本默认即 prompt”对架构的影响为中等：

- 会改变正式交互语义
- 但不会要求重写 task / dispatcher / runner 主链

因此这轮适合以入口语义改造为主，而不是扩大到底层执行重构。
