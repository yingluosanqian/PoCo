# Problem

## 当前状态

- notifier 已能发送 `task_status` interactive card
- 但 task 还没有保存这张通知卡对应的消息标识
- 后续状态变化只能继续新发

## 问题定义

PoCo 当前缺少一条从首次 task status card 发送结果到后续状态更新的消息标识保存与复用链，导致 task 卡片还不能原位更新。

## 不是的问题

- 不是现在就实现任意历史消息回补的问题
- 不是现在就实现完整 timeline 聚合的问题
