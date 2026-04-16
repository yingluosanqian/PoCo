# Problem

## 背景

见 `need.md`。

## 相关需求

- 复用 `CompletionGate` 消除 claude_code 的弱终态兜底空白
- 不扩大到 cursor_agent / coco，这两个后续单独立 record

## 当前状态

`poco/agent/claude_code.py` `_execute_prompt` 的终态判定：

- **强终态**：`result` event（subtype=`success` → completed，其它 → failed）
- **进程退出 fallback**：`process.poll() is not None and not _has_ready_stream(...)` 跳出 while，然后根据 returncode 判成 completed 或 failed
- **超时 fallback**：`deadline` 到达后 kill 进程返回 failed

没有 "我看到 Claude 已经发完 final 消息，但 `result` 还没来" 这一种"候选终态" 处理。

## 问题定义

**如果 claude CLI 发完一条 `stop_reason == "end_turn"` 的 `assistant` 消息之后，迟迟不发 `result` 又不退出进程，PoCo 会一路卡到 900s timeout。用户看到的是 card 有完整回复文本却永远停在 `[Running]`。**

这和 2026-04-16 codex-completion-semantics 的 problem 完全同款：

> task 的可见输出已经结束，但状态仍长期停在 `running`

只是发生在 claude backend。

## 为什么这是个真实问题

- codex 那轮用真实 app-server 输出证明了"弱终态不兜底就是会踩"
- claude CLI 在 tool use / network hiccup 场景下有类似行为空间
- CompletionGate 刚抽出来就是为了避免每个 backend 再单独踩同一条路
- PoCo purpose 里"移动端可以可靠判断 task 是否真的结束"是硬线

## 不是什么问题

- 不是"`result` event 本身不可靠"。真实 claude CLI 在大多数路径上还是会发 `result`，我们仍然把它作为强终态首选
- 不是"要改 claude CLI 的输出协议"。PoCo 只能消费，不能改 CLI
- 不是"要抽新抽象"。CompletionGate 已经抽好了，本轮只是应用

## 证据

- `poco/agent/claude_code.py:296-325` 只在 `result` event 到达时写 `return`；之外的路径都靠 while-loop 走完
- `poco/agent/claude_code.py:327-341` 进程退出后无条件 yield completed（只要 returncode == 0）
- 类似 codex 的 `mcpServer/startupStatus/updated` 这类中间 progress 事件，claude 也有 `control_request` / `stream_event.message_delta` / `stream_event.message_stop` 等，不会被当作终态但也不主动兜底
