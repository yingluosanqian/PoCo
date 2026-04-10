# Problem

## 当前状态

- `task.submit` 已可在群卡中发起任务
- dispatcher / notifier 已能在等待确认和终态时回推消息
- 但这些通知仍主要是文本，不是 task status card

## 问题定义

PoCo 当前缺少一条从 task 状态更新到 approval/result card 的最小回推链，导致 card-first task 流仍不能独立完成确认和结果消费。

## 不是的问题

- 不是现在就实现完整 session timeline 的问题
- 不是现在就实现可编辑消息更新策略的问题
- 不是现在就实现 richer result formatting 的问题
