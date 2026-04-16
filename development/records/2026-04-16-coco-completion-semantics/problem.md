# Problem

## 背景

见 `need.md`。

## 相关需求

- 让 `_timeout_seconds` 在 coco 上真的生效（目前它是死字段）
- 给 coco 补弱终态兜底，语义上对齐前三个 backend

## 当前状态

### 关键代码路径

- `CocoRunner._execute_prompt` 走到 `for event in prompt_stream`，`prompt_stream` 是 `_TraeAcpPromptStream` 的 iterator。
- `_TraeAcpPromptStream.__iter__` 每次调 `self._client.read_next_message()`，**无参数、无超时**。
- `_TraeAcpClient.read_next_message()` 转到 `_read_message`，内部 `select.select(..., 0.25)` 只控制单轮 poll，外层是 `while True`，**没有 deadline**。

### 强终态（已正确处理）

- JSON-RPC response 以 `id == prompt_request_id` 到达 → 根据 `error` / `result.stopReason` 映射 completed / cancelled / failed（coco.py:532-548）
- `session/update` notification 带 `sessionUpdate=usage_update + stopReason` → completed / cancelled（coco.py:561-569）

### 流式 chunk 格式

`session/update` 带 `sessionUpdate=agent_message_chunk` 的 update 里：

- `_meta.id`：消息 id
- `_meta.type`：`"partial"` or `"full"`
- `_meta.lastChunk`：boolean —— **当前代码不消费**

观察测试里的真实消息（如 `test_coco_runner_ignores_pre_prompt_message_ids_from_loaded_session`）：`lastChunk: true` 是服务端对"这条 message 已完结"的显式标注。

## 问题定义

### 问题 A（功能 bug）：coco 没有超时

`CocoRunner._timeout_seconds=900` 是 inert 字段。如果 ACP server hang（收到 prompt 但不回 response、也不发 stop 信号），PoCo 就一直在 `_read_message` 的 `while True` select 里循环，永远不会因为 900s 过去而主动 fail task。

### 问题 B（语义对称性）：coco 没有弱终态兜底

其他三个 backend 都接了 CompletionGate。coco 的两个强终态虽然覆盖面广，但真实世界里协议 server 仍可能"发完最后 chunk 就卡住"—— 没有兜底就只能等超时（修好问题 A 之后）。`_meta.lastChunk: true` 是协议里现成的弱终态，用它 arm 几乎零成本。

## 为什么这是个真实问题

- 问题 A 是明确的 bug：字段名承诺了 timeout，行为上没实现
- 问题 B 和前三轮 decision 的精神一致：PoCo purpose 明确"状态必须可靠"
- 两件事合在一轮做心智成本低、record 页数少

## 不是什么问题

- 不是"coco 的 two-terminal 机制有缺陷"：两个强终态信号设计本身是好的
- 不是"要改 ACP protocol"
- 不是"要给 coco 改 transport 复用逻辑"：transport 层不动

## 证据

- `poco/agent/coco.py:79-86`：`_timeout_seconds` 被赋值
- `grep -n '_timeout_seconds\|timeout' poco/agent/coco.py` 除了上面两行之外，在 `_execute_prompt` / `_TraeAcpPromptStream.__iter__` / `_TraeAcpClient.read_next_message` 里完全不出现
- `poco/agent/coco.py:478-499` 的 `_TraeAcpClient._read_message` 硬编码 `select.select(..., 0.25)` 且无外层 deadline
- `tests/test_agent_runner.py` 多条测试的 `_meta` 里有 `lastChunk: true/false` 字段存在
