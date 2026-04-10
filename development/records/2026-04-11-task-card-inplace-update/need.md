# Need

## 背景

`task_status` card 已经能发出来，但当前仍主要是每次状态变化都新发一张通知卡。

## 需求信号

- 已有 `Approve` / `Reject`
- 如果每次状态变化都追加新卡，群里很快会堆满 task status 消息

## 场景

- task 先进入等待确认并发出卡片
- 用户点击 `Approve`
- task 完成后，用户更希望看到原卡被更新，而不是再追加一张新的终态卡

## 影响

这一步决定 PoCo 的 card-first task 流是否开始从“能用”走向“更干净可持续”。
