# Decision

采纳“显式终态优先，`final_answer` 受限兜底收口”方案。

具体为：

- `turn/completed` 继续作为最权威的 codex 终态信号
- `item/completed(agentMessage)` 只更新结果文本缓存，不能单独结束 task
- `agentMessage.phase == final_answer` 决定哪些文本可以被当作最终答复缓存
- 若已收到 `final_answer`，且随后没有新的同 turn 活动，则允许在短 settle 窗口后完成
- commentary / analysis / tool activity 不能触发这个兜底；一旦 `final_answer` 之后又出现新的同 turn 活动，候选收口会被清掉

## 为什么这样选

- `main` 分支的 `turn/completed` 语义仍然是主基线
- 但 2026-04-16 的真实长任务样本表明：在多阶段 tool turn 里，PoCo 可能已经拿到 `phase=final_answer`，却没有等到可消费的 `turn/completed`
- 可以直接消除“中间进度文本被误当最终结果”的提前 complete 问题
- 只对 `final_answer` 开受限 settle fallback，可以补上“最终答复已到达但 task 仍卡 running”的真实缺口
- 只改 codex backend 内部状态机，不扩大到 task/notifier 架构重做
- 仍保留 `TaskController.reconcile_task_execution` 作为异常路径兜底，而不是把正常完成语义丢给 reconcile 猜

## 当前明确不做

- 不承诺 codex 协议所有未来事件形态都已完全覆盖
- 不把这轮修复扩展到 `claude_code`、`cursor_agent`、`coco`
