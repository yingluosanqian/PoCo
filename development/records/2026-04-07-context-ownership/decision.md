# Decision

## 待选问题/方案

- 方案 A：把上下文完全交给 Codex 等 backend 维护
- 方案 B：由 PoCo 自己完整维护全量会话记忆
- 方案 C：分层持有，PoCo 维护产品级连续性交接上下文，backend 维护执行期上下文

## 当前决策

采用方案 C。

PoCo 负责维护产品级连续性交接上下文；Codex、Claude Code、Cursor Agent 等 backend 负责维护各自执行期上下文。PoCo 不尝试复制 backend 的全部内部记忆，但必须维护足以支撑移动端恢复工作流的稳定对象与摘要。

## 为什么这样选

- 这最符合项目目的中“碎片化打断后恢复”的要求
- 这保留了 backend 的执行自治，不把 PoCo 变成重型 memory 系统
- 这避免把产品连续性完全绑定到单一 backend，便于后续支持 Claude Code 和 Cursor Agent
- 这也让 `/status`、后续潜在的 `/continue`、确认历史和恢复提示具备稳定依附对象

## 为什么不选其他方案

- 不选方案 A：若完全依赖 Codex 内部上下文，PoCo 无法独立解释工作流连续性，也无法为多 backend 提供统一产品语义
- 不选方案 B：若 PoCo 自己持有全量记忆，会过早扩大系统复杂度，并侵入 backend 内部执行模型

## 风险

- 若 PoCo 持有的连续性交接信息过少，恢复体验仍会很弱
- 若 PoCo 持有的信息过多，又容易演化成重型 memory 系统
- backend 若没有暴露任何可恢复句柄，PoCo 只能退化到摘要式交接

## 后续影响

- 下一轮设计需要引入最小 `session/handoff` 抽象
- task 不再是唯一长期对象，session 将成为移动端连续性交互的上层归属
- 执行器适配层需要考虑是否暴露可选的 resume handle，但这不是当前强制前提
