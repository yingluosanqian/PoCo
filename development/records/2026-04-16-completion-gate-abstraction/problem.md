# Problem

## 背景

见 `need.md`。

## 相关需求

- 需要把 codex 的完成 settle 状态机复用到其他三个 backend
- 需要降低跨 backend 实现这套语义时的心智成本和出错率

## 当前状态

在 `poco/agent/runner.py` 的 `CodexAppServerRunner._execute_prompt` 里：

- `candidate_completion_at: float | None` 存 arm 时刻
- `candidate_tick_seen: bool` 记录 arm 之后是否已经过了至少一个循环 tick
- 两个变量在 `while True` 循环内直接赋值，散落在 8 处以上
- top-of-loop 的 settle 判定直接写成裸 if/else

读这段逻辑需要同时把三条规则记在脑子里：

1. arm 只能在 `phase=final_answer` 的 `item/completed` 时设置
2. arm 当轮不 fire settle，下一 tick 才可以
3. 任何非 disarm 的事件在下一 tick 进入 top-of-loop 时都会触发 settle 判定（这是 settle 的关键保护，不是可选的）

## 问题定义

**这套状态机的抽象边界在代码里是隐式的，存在于"开发者的注意力"里，不在类型系统或调用界面里。**

具体后果：

- 新 backend 迁移时，开发者必须先完整重读现有 codex 实现，再逐字复刻三条规则
- 任何一条漏了都会变成 "task 卡 Running" 或 "task 提前 complete"，和 2026-04-16 revision 想解决的就是同一类问题
- 单测里也没有"纯状态机"的验证面 —— 必须通过整条 app-server 流程来间接验证

## 为什么这是个真实问题

- 已经决定要把 completion 审计扩到其他三个 backend（decision 队列里下一件事）
- 此刻不抽层，四份会分别长出细微差异，之后再合并时代价比现在直接抽高数倍
- 纯内部重构，不挑战任何 `purpose` / `constraints` 边界

## 不是什么问题

- 不是"现在 codex 的完成语义有 bug" —— 2026-04-16 那轮修正后 17 条用例全绿
- 不是"要做跨 backend 通用状态机" —— 本轮只抽这一个 settle gate，不做其他
- 不是"要改对外行为" —— 行为完全一致

## 证据

- `poco/agent/runner.py:490-519, 613-634, 665, 715-724` 多处对 `candidate_completion_at` 和 `candidate_tick_seen` 的赋值
- 2026-04-16 codex-completion-semantics 的 validation.md 已经把这套语义的口径固定下来了
