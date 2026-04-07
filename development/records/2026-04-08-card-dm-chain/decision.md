# Decision

## 待选问题/方案

- 方案 A：先接完整群工作区 card 链
- 方案 B：先接最小 DM project 管理 card 链

## 当前决策

采用方案 B。

先实现 DM 侧 project 列表、project 创建、project 打开和最小 workspace 打开链路；群工作区完整交互留到下一轮。

## 为什么这样选

- DM 管理侧依赖更少，适合作为第一条可跑 card 链
- 能更快验证 dispatcher、handler、renderer、gateway 的分层是否正确

## 为什么不选其他方案

- 不选方案 A：会把 project/session/task/group 复杂度一起拉进来

## 风险

- 用户可见能力仍然偏窄
- 可能需要下一轮再补群工作区来验证完整价值

## 后续影响

- 下一轮可以在此基础上继续接 group workspace cards
