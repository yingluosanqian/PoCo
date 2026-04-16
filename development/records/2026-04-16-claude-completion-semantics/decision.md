# Decision

## 待选问题/方案

方案 A：直接复用 codex 的 CompletionGate 模式。`assistant` event 的 `stop_reason == "end_turn"` 作为弱终态 arm 信号，下一条 text_delta / 新 `assistant` event 作为 disarm 信号，`result` event 保留为强终态优先。

方案 B：把 `result` event 的 arrival 窗口压短（比如 strong timeout 30s 内必须到），到时间就默认完成。

方案 C：什么都不做，继续依赖 900s 全局 timeout。

## 当前决策

采纳 **方案 A**。

具体实现约束：

- `ClaudeCodeRunner.__init__` 新增 `completion_settle_seconds: float = 1.0` 参数，和 codex 一致。factory.py 不改（继承类默认值，与 codex 同）。
- `_execute_prompt` 内实例化 `CompletionGate(settle_seconds=self._completion_settle_seconds)`。
- 在 while-loop 顶部（timeout 判定之后、`select.select` 之前）调 `gate.tick(monotonic())`，`should_fire` 为真则 yield completed 并 return。
- arm 时机：收到 `assistant` event，且解析出的 `stop_reason == "end_turn"`。同轮用 `gate.arm(now)` 返回值决定是否打首次 arm log。
- disarm 时机：
  - 任何 `stream_event` 的 `content_block_delta` text_delta（有新文本流出）
  - 任何 `assistant` event 但 `stop_reason` 不是 `end_turn`（claude 选择继续，比如 `tool_use`）
- `result` event 继续作为强终态，语义和文本完全不变，只加一行 INFO log 表明走的是强终态路径。
- settle 触发时 yield 的 completed update 文本保留"Task completed by the claude_code runner."（现有成功路径文本一致），只是额外加 `after the final assistant message settled.` 这类区分后缀，以便飞书卡片 / 日志能看清是哪条路径收口。
  - 不对，和 codex 一致：单独一条文本 `Task completed by the claude_code runner after the final assistant message settled.` — 避免和强终态混同，方便 grep 日志

## 为什么这样选

- CompletionGate 就是为这个场景设计的；复用零成本，行为和 codex 一样稳
- `stop_reason == "end_turn"` 是 Anthropic 协议里 model 自己声明"我这一轮结束了"的最权威信号；比任何"静默窗口"更语义化
- 方案 B 会在网络抖动 / 真实长 tool turn 情况下错误地 fire，等于把 bug 换了方向
- 方案 C 是放任问题，和 purpose 冲突

## 为什么不选其他方案

- 方案 B：错误语义，会制造新的提前 complete 问题
- 方案 C：见 need

## 风险

- **stop_reason 字段位置**：Claude Code CLI 输出里 `stop_reason` 可能挂在 `assistant.message.stop_reason`，也可能只在更早的 `stream_event.event.delta.stop_reason`（`message_delta` 类型）。先只认 `assistant` event 路径，这是 CLI 目前稳定输出的。如果后续观察到 `stream_event.message_delta` 才带 `stop_reason` 而 `assistant` event 没有，再加第二个 arm 点。
- **tool turn 误 arm**：如果一个 assistant 消息是 tool_use 而不是 end_turn，但 stop_reason 字段解析错误，可能误 arm。通过判定 `stop_reason == "end_turn"` 字面匹配规避；其他值一律走 disarm。
- **回归风险**：5 条现有 claude tests 必须继续绿。新加的 regression test 覆盖"end_turn + 无 result + heartbeats"。

## 后续影响

- cursor_agent / coco 之后做同款审计时照着本 record + codex 的 validation 复刻
- 若后续 claude CLI 协议演进（比如新 `stop_reason` 值），本文件是入口
