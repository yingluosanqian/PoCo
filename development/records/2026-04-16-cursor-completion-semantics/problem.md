# Problem

## 背景

见 `need.md`。

## 相关需求

- 复用 CompletionGate 给 `cursor_agent` 加弱终态兜底
- 不挑 cursor 协议里不存在的强信号，只利用 cursor 实际已经发出的信号

## 当前状态

`poco/agent/cursor_agent.py` `_execute_prompt` 的终态路径：

- **强终态**：`type=result` event → 根据 `is_error` 判 completed / failed
- **进程退出 fallback**：while-loop break，按 returncode 判 completed / failed
- **超时 fallback**：900s 到点 kill + failed

没有"已经看到 cursor 完整答复、但 `result` event 还没来"时的候选 arm。

## 问题定义

**和 2026-04-16 codex / claude 的同款问题**：如果 cursor CLI 输出完所有 assistant 内容之后不发 `result` 又不退出进程，PoCo 会挂到 900s timeout。

### cursor 的信号特点

和 codex (`phase=final_answer`) / claude (`stop_reason=end_turn`) 不同，cursor 协议里没有显式 "turn 结束" 字段。但观察现有 `test_cursor_runner_handles_assistant_message_events_and_terminal_result` 的真实 stream，发现一个稳定模式：

- 多条 `assistant` event 增量送 text（每条 content[0].text 是一个小片段）
- 最后一条 `assistant` event 的 `message.content[0].text` 是**前面所有片段拼接的完整文本**
- 之后才是 `type=result`

`_extract_cursor_output_chunk` 已经识别这种"重发完整内容"行为：

- `if full_text.startswith(current_live_text): delta = full_text[len(...):] or None` —— 相等时 delta 为 None
- `if current_live_text and full_text in current_live_text: return None, current_live_text` —— 子串时 delta 为 None

换句话说：**一个 `assistant` event 产生了 None delta，但 `_extract_cursor_final_text` 能提出 final text，意味着 cursor 正在重发完整消息 —— 最接近 "我的回复结束了" 的信号**。

## 为什么这是个真实问题

- 和 codex / claude 一样属于 PoCo purpose 硬线问题（状态可靠性）
- 已经在前两轮被证明了代价是"踩一次 15 分钟"
- CompletionGate 模板现成，应用成本极低
- 不做就要等真实 cursor 用户踩了再补

## 不是什么问题

- 不是"cursor 协议有缺陷"：`type=result` 在绝大多数路径上是可靠的
- 不是"要给 cursor 补 stop_reason"：PoCo 不能改 CLI 协议
- 不是"要用静默窗口 heuristic"：那会在正常长 tool turn 里误 fire

## 证据

- `poco/agent/cursor_agent.py:233-264` 只有 `type=result` 是显式完成路径
- `_extract_cursor_output_chunk` 第 376-381 行的 summary 检测逻辑早已存在
- `tests/test_agent_runner.py::test_cursor_runner_handles_assistant_message_events_and_terminal_result` 的 stream 证明"summary assistant event"是 cursor CLI 真实行为
