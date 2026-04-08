# Decision

## 待选问题/方案

- 方案 A：先继续完善 card action 回调，不处理首张卡片下发
- 方案 B：先打通 DM 消息事件 -> interactive card 发送的最小闭环

## 当前决策

采用方案 B。

先让真实飞书单聊能收到一张 project list 首页卡片；更复杂的卡片动作继续在后续轮次补齐。

## 为什么这样选

- 用户当前最直接的阻塞就是“单聊看不到卡片”
- 真实可见卡片比继续堆 action 协议更值钱
- 可以保留 `DM = control plane`、`group = task fallback` 的当前边界

## 风险

- 当前仍是混合态，不是完整 card-first 正式交互
- 卡片首屏可见不等于完整交互已成立

## 后续影响

- 后续可基于真实发出的卡片继续补 action、group workspace 和 project lifecycle
