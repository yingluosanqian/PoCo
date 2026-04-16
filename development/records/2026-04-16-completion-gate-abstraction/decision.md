# Decision

## 待选问题/方案

方案 A：抽一个 `CompletionGate` 数据类，把 `_armed_at` / `_tick_seen` / `settle_seconds` 封在内部，对外暴露 `arm(now) -> bool` / `disarm()` / `is_armed` / `tick(now) -> (should_fire, elapsed)`。

方案 B：抽一个更大的"BackendStateMachine"或"TurnLifecycle"抽象，涵盖 arm/disarm + turn tracking + stream parsing + cancel。

方案 C：什么都不抽，等四个 backend 都各写一份再看要不要统一。

## 当前决策

采纳 **方案 A**。本轮抽最小的 `CompletionGate`，仅封 settle 三规则，不碰 turn tracking / stream parsing / cancel 等其他关注点。

## 为什么这样选

- **边界清晰且自然**：`candidate_completion_at + candidate_tick_seen` 这对变量就是在表达 "settle gate"，抽出来是还债，不是过度设计。
- **影响面可控**：方案 A 只是把现有逻辑换个承载形式，codex 行为完全一致，现有 17 条 app-server 用例直接做 regression 守门。
- **前置简单**：之后 claude / cursor / coco 做 completion 审计时，只需在各自 `_execute_prompt` 里 `gate = CompletionGate(settle_seconds=...)` + 三个方法，不用各自重造状态变量。
- **便于单测**：抽出来后可以直接对 Gate 本身做纯状态机测试，覆盖所有 arm/disarm/tick 排列，不再依赖构造假 stream。
- **避开方案 B**：2026-04-16 codex record 的 decision 就明确说过 "不把这轮修复扩展到更大抽象"。更大的抽象必须单独立 record 重审。

## 为什么不选其他方案

- **方案 B**：把 turn 级别的状态和 settle 级别的状态绑在一起，耦合太早。不同 backend 的 turn 概念不一样（codex 有 turnId，claude 有 sessionId，cursor 是 stdin-then-stdout），强行共用会反过来污染 Gate 的定义。
- **方案 C**：等于预期"要踩四次坑才动手"，和 constraints.md 里"先保证任务状态清晰"这条硬取舍冲突。

## 风险

- **抽象早于第二用户**：目前只有 codex 在用，Gate 的接口是基于 codex 实际需要设计的。如果 claude/cursor/coco 真正接入时发现接口不够，需要微调。但因为 Gate 只有三个方法 + 一个属性，修改面很小。
- **回归风险**：codex 行为必须完全一致。由现有 17 条 app-server 用例守门；新增的 CompletionGate 单测覆盖所有状态转换。

## 后续影响

- 下一步 "claude_code 完成语义审计" 直接复用这个 Gate，不再自己写 `candidate_completion_at`
- 若后续需要区分"强终态" vs "弱终态"（比如"看到 `turn/completed` 就无需等 tick"），可以在 Gate 上加一个 `fire_immediately(now)` 方法，不破坏现有接口
