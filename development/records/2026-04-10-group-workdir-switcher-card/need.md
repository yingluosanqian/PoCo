# Need

## 背景

DM `Project Config Card` 已经落地，但群工作面的快变量还没有真正卡片化入口。

## 需求信号

- 上一轮已经明确下一步应实现 `Group Workdir Switcher Card`
- `working dir` 已被定义为 session 级快变量，需要就地切换入口

## 场景

- 用户在群里看到 workspace overview
- 用户点击 `Change Workdir`
- 卡片进入专门的 workdir switcher，而不是被迫回到 DM

## 影响

这是把 `working dir = session stance` 从设计层推进到正式群工作面的第一步。
