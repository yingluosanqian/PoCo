# Decision

## 当前决策

先落地最小 task status card 链：

- notifier 在等待确认和终态时发送 `task_status` interactive card
- `task_status` 在等待确认时提供 `Approve` / `Reject`
- `task.approve` / `task.reject` 复用已有确认主链

## 为什么这样选

- 这直接补上 card-first task 流中最关键的断点
- 不需要先重做 dispatcher 或 task state 结构
- 可以复用现有 task model、confirmation flow 和 async resume

## 风险

- 当前仍是新发通知卡，不是原消息 inplace 更新
- 当前结果卡仍是最小摘要，不是完整富结果视图
