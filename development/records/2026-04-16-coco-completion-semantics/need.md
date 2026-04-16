# Need

## 背景

`coco` (Trae CLI via ACP) 是 completion 语义审计队列的最后一个 backend。审代码时发现两件事：

1. `CocoRunner.__init__` 接收 `timeout_seconds: int = 900` 并赋给 `self._timeout_seconds`，但整个 `_execute_prompt` / `_TraeAcpPromptStream.__iter__` / `_TraeAcpClient.read_next_message` 链路里**没有任何一处使用它**。
2. 没有弱终态兜底：完全依赖两个强终态信号（JSON-RPC response 到 `prompt_request_id` + `session/update` 带 `sessionUpdate=usage_update + stopReason`）。

## 需求信号

- 队列本身：四个 backend 完成审计的最后一环
- 真实风险：ACP server hang 时，blocking `read_next_message()` 会一直等，外部取消 / kill 才能解脱；`_timeout_seconds=900` 字段名上看像是已经在起作用，但实际 inert
- ACP 协议里有一个现成的"这条 message 完结"信号 `_meta.lastChunk: true`，没被消费

## 来源

- 2026-04-16 completion-semantics 扩 backend 队列（codex → claude → cursor → **coco**）
- 读 `poco/agent/coco.py` 和 `tests/test_agent_runner.py::CocoRunnerTest` 过程中发现 timeout 实际无效

## 场景

两类用户风险：

- ACP server hang → task 永远 Running（除非上层 dispatcher 另有看门狗）
- ACP server 丢失 terminal 事件但保持连接 → 同款卡 Running

## 频率/影响

- hang 风险在 coco 上比其他三个更严重：别的 backend 至少有 `deadline` 判定；coco 这段代码漏了
- `lastChunk` arm 信号的价值比 codex `final_answer` / claude `stop_reason=end_turn` 弱，因为 coco 已经有两个强终态

## 备注

本轮两件事同做：
1. 把 `_timeout_seconds` 真的连上去（bug fix）
2. 加 `CompletionGate`，arm 信号是 `_meta.lastChunk: true`（保持模板对称）

不改 ACP protocol / transport 复用逻辑。
