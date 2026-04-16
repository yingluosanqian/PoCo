# Need

## 背景

2026-04-16 三轮改动之后：

- codex 已经有完整的 completion-semantics 护栏：`turn/completed` 强终态 + `final_answer` settle 弱终态兜底
- `CompletionGate` 已经抽出来，是一个可复用的三规则状态机
- runner.py 已经按 backend 拆开，`claude_code.py` 是独立文件

但 `claude_code` 当前的完成判定还是老版本：只有 `result` event 是强终态，没有弱终态兜底。

## 需求信号

- 用户今天实际发生过"claude session ready 后长时间无响应"现象，虽然当时定位是 `ANTHROPIC_BASE_URL` 没继承，但一旦 claude CLI 真正发完 `assistant` 消息却不发 `result` event（CLI bug、网络抖动、pipe buffer 问题等），PoCo 就会一路挂到 900s timeout
- codex 之前踩过一模一样的"弱终态没兜底"坑，claude 同款路径早晚也会触发
- 计划队列里这一轮就是 "Feature 1 - claude_code 完成语义审计"

## 来源

- 和用户确认过的优先级：Refactor 3 (CompletionGate) → Refactor 1 (拆 runner.py) → **Feature 1 (claude_code completion 审计)** → 然后 cursor_agent / coco
- CompletionGate 被抽出来的动机之一就是此刻能直接复用到 claude

## 场景

修复"Claude CLI 发完 assistant 消息但 `result` 迟迟不到或不到"时，PoCo 卡 Running 到超时的类同问题。

## 频率/影响

- 用户感知：飞书 task card 停在 `[Running]` 状态、最后一次输出其实已经是完整 final answer，和 codex 早期的同款 bug 表现一致
- 不修就继续在潜伏期

## 备注

- 本轮只动 `claude_code.py`，不碰 cursor/coco
- `completion_settle_seconds` 仍走类默认 1.0，不新增 Settings 字段（与 codex 保持一致）
