# Decision

## 当前决策

采用“慢变量放 DM，快变量放群”的分层模型：

- `agent` 归 `project`
- `working dir` 归 `session`
- `task` 只消费当前上下文，不负责重新做重配置

对应交互面：

- `DM` 负责 project 级配置：
  - 选择 agent
  - 绑定 repo root
  - 管理默认 workdir 和 workdir presets
- `Group` 负责 session 级工作上下文：
  - 展示当前 agent
  - 切换当前 workdir
  - 发起 task

## 为什么这样选

- `agent` 更像 project identity，切换成本高，且容易中断上下文连续性
- `working dir` 更像当前工作站位，应允许在同一 project 下更灵活切换
- 这符合已批准的正式交互模型：
  - `DM -> control plane`
  - `Group -> project workspace`

## 明确不选

- 不把 `agent` 设计成群内可随手切换的普通动作
- 不把 `working dir` 固定死在 bot 全局或 task 临时输入里
- 不把 `agent` 和 `working dir` 都堆进同一个配置面板

## 风险

- session 抽象还没真正落地，`working dir` 的 session ownership 仍需后续实现支撑
- `agent` 虽然默认锁定，但仍需要为少数迁移场景设计显式的高级入口
