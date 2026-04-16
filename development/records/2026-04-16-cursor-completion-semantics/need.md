# Need

## 背景

`cursor_agent` backend 当前只把 `type=result` event 当终态；此外依赖 process exit fallback 和 900s timeout。和 codex / claude_code 审计前是同款格局。

## 需求信号

- 按 feature 1 队列，`cursor_agent` 是第三个要审的 backend
- CompletionGate 模式在 codex、claude 上已各自落地，模板成熟
- 真实 cursor CLI 在"输出完但 result 没发"时会踩同样的"卡 Running 到 timeout"坑

## 来源

- 2026-04-16-completion-gate-abstraction decision 明确下一步
- 2026-04-16-claude-completion-semantics 已照同模板走通一轮

## 场景

排障时发现 cursor task card 有完整输出却停在 `[Running]` 的场景。

## 频率/影响

- 频率低于 codex，因为 cursor 的 `type=result` 在多数路径上会如期发出
- 但和 claude 一样属于"踩了就要人工重启/等 15 分钟"级别的坑

## 备注

本轮只改 `cursor_agent.py`，不改 coco。
