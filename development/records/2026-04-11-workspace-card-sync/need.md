# Need

## 背景

`task_status` 已经能原位更新，但 workspace 首卡上的 latest task 区块仍主要靠手动 `Refresh`。

## 需求信号

- workspace 已经是 group 主入口
- latest task 已经是 workspace 首卡里的关键摘要
- 如果 task 状态变化后 workspace 首卡不跟着动，用户就要在 task card 和 workspace card 之间自己做同步

## 场景

- 用户在 workspace 提交任务
- task 进入等待确认或完成
- 除了 task card 本身更新，workspace 首卡的 latest task 区块也应同步反映这次变化

## 影响

这一步决定 workspace card 是否开始真正承担“项目工作面”的职责，而不只是静态入口。
