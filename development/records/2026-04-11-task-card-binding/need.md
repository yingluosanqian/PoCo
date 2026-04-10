# Need

## 背景

task status card 已经能原位更新，但 `task.submit` 之后当前卡和后续 notifier 之间还不够紧。

## 需求信号

- 用户从 `task_composer` 提交任务后，希望当前卡直接进入 task 状态
- workspace 首卡也需要能稳定打开当前 project 的最新 task

## 场景

- 用户在群里打开 `task_composer`
- 提交任务后，当前卡直接变成 `task_status`
- 回到 workspace 时，能看到并打开 latest task，而不是只能重新靠通知卡寻找

## 影响

这一步决定 task flow 是否从“多张相关卡并行增长”继续收敛到更稳定的单对象视图。
