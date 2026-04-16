# Need

## 背景

2026-04-16 的 codex completion-semantics 修正引入了 `candidate_completion_at` + `candidate_tick_seen` 这对裸变量，埋在 `_execute_prompt` 主循环里。行为对但读起来隐晦。

## 需求信号

- 列的下一步计划是把同一套语义（"收到 final 信号 + 下一 tick 仍未被 disarm 就允许完成"）迁移到 `claude_code` / `cursor_agent` / `coco`
- 如果继续用裸变量复制粘贴四份，三个新 backend 必然会踩掉 tick_seen 重置、arm-then-disarm 边界这类小坑

## 来源

- 和用户讨论后选定的先后顺序：Refactor 3 (CompletionGate) → Refactor 1 (拆 runner.py) → Feature 1 (其他三个 backend 的 completion 审计)

## 场景

纯内部重构。对外行为、对 task 语义、对飞书卡片、对 notifier 链路都不改。

## 频率/影响

当前每加一个 backend 要审的完成语义就会重新出一轮相同的 bug（提前 complete / 卡 Running）。把这套状态机抽一层，之后复用成本降到最低。

## 备注

本轮只抽类和迁移 codex 一个 backend。其他三个 backend 的实际应用留给后续 record。
