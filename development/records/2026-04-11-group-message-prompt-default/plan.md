# Plan

本轮先完成正式交互语义调整，再进入实现。

## 范围

- 明确 DM 与 Group 的默认消息语义
- 明确群普通文本消息与斜杠命令的优先级
- 明确卡片在新模型下的职责收缩
- 明确对现有模块边界的影响

## 不在范围内

- session continuity 的完整实现
- richer timeline 或多消息线程模型
- 语音、图片、文件等非文本 prompt intake
- workdir / agent 选择交互的重新设计

## 验收标准

当这轮结束时，应该能清楚回答：

- 群里一条普通文本消息是否默认创建 task
- DM 里普通文本消息是否默认创建 task
- `/help`、`/status`、`/approve`、`/reject` 是否继续保留
- `Run Task` 卡片在新模型里是否仍然保留，以及为什么

## 实施顺序

1. 先调整交互决策和设计记录
2. 再修改 `FeishuGateway` / `InteractionService` 的文本解释策略
3. 最后更新卡片文案、README 和验证
