# Decision

采纳“显式终态优先，弱信号延迟收口，delta-only 长静默兜底”方案。

具体为：

- `turn/completed` 继续作为最权威的 codex 终态信号
- `thread/status=idle` 不再立即触发 `completed`，而只作为候选收口信号
- `item/completed(agentMessage)` 也不再直接结束 task，而进入短暂 settle 窗口等待后续事件
- 若只有 delta 输出且长期没有任何后续协议活动，则按较长静默窗口兜底完成

## 为什么这样选

- 可以直接修复“提前 complete”与“输出完还 running”这两个相反问题
- 只改 codex backend 内部状态机，不扩大到 task/notifier 架构重做
- 仍保留 `TaskController.reconcile_task_execution` 作为异常路径兜底，而不是把正常完成语义丢给 reconcile 猜

## 当前明确不做

- 不承诺 codex 协议所有未来事件形态都已完全覆盖
- 不把这轮修复扩展到 `claude_code`、`cursor_agent`、`coco`
