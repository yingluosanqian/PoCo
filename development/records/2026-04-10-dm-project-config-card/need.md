# Need

## 背景

`agent` 与 `working dir` 的 ownership 和卡片 IA 已经完成设计，但 DM 侧还没有真正出现一张承接 project 级配置摘要的卡。

## 需求信号

- 用户已经要求“按照设计继续”
- 上一轮已经明确 `DM Project Config Card` 是实现优先项

## 场景

- 用户在 DM 中打开某个 project
- 卡片应展示当前 agent、repo root、default workdir、workspace group
- 用户可以进入对应的配置入口，而不是只看到一个松散的 detail 卡

## 影响

这是把 `agent/workdir` ownership 模型从记录层推进到正式交互面的第一步。
