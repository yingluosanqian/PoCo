# Decision

## 当前决策

围绕 `agent` 与 `working dir`，正式采用两张主卡的最小信息架构：

1. `DM Project Config Card`
2. `Group Workdir Switcher Card`

其中：

- `DM Project Config Card` 承接 project 级慢变量
- `Group Workdir Switcher Card` 承接 session 级快变量

## 为什么这样选

- 它直接映射已批准的 ownership 模型
- 它避免把 agent 和 working dir 塞进同一张万能卡
- 它让 DM 与 Group 的职责保持清楚，不会回退成混合配置面板

## 明确不选

- 不把 `agent` 暴露成群首卡里的一级切换动作
- 不把 `working dir` 放回 DM 作为每次都要跳转的低频设置
- 不把 repo root、default workdir、recent dirs、task composer 全都堆进同一张卡

## 风险

- 如果一级信息过多，DM project config card 会重新膨胀成杂物箱
- 如果群内 switcher 过深，用户会在高频动作上感到阻力
