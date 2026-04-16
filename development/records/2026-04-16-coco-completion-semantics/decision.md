# Decision

## 待选问题/方案

方案 A：两件事分两轮做 —— 先修 timeout bug，再加 CompletionGate。

方案 B：合并一轮做 —— timeout + CompletionGate 一起落地。

方案 C：只修 timeout，coco 跳过 CompletionGate（依赖两个强终态就够了）。

## 当前决策

采纳 **方案 B**：合并一轮。

### 具体实施约束

#### 问题 A（timeout）

- `_TraeAcpClient.read_next_message` 新增可选参数 `poll_timeout_seconds: float | None = None`
  - `None`：保持当前行为（无限 block），`.request()` 内部调用沿用此路径
  - 非 None：select 每轮用这个值，**总等待时间到该值就返回 None**；调用方后续用 `process.poll()` 区分"poll 超时"和"process 退出"
- `_TraeAcpPromptStream.__init__` 新增 `timeout_seconds: float` 和 `completion_settle_seconds: float` 参数
- `_TraeAcpPromptStream.__iter__` 内：
  - 计算 `deadline = monotonic() + self._timeout_seconds`
  - 每轮循环先查 deadline；超时 → yield `_TraePromptEvent(kind="failed", message=f"Trae CLI timed out after {self._timeout_seconds:.0f} seconds.")`
  - 然后查 CompletionGate（见下）
  - 调 `read_next_message(poll_timeout_seconds=min(0.25, remaining))`
  - 若返回 None 且 process 仍 alive → 只是 poll 超时，continue
  - 若返回 None 且 process 已退出 → 沿用现有"stream closed"失败路径

#### 问题 B（CompletionGate）

- 在 `_TraeAcpPromptStream.__iter__` 内实例化 `CompletionGate(settle_seconds=self._completion_settle_seconds)`
- **arm 条件**：收到 `session/update` 的 `agent_message_chunk`，且 `_meta.lastChunk == True`
- **disarm 条件**：收到任何 `agent_message_chunk` 但 `lastChunk` 不是 True（正在继续流式输出）
- 强终态事件（match prompt_request_id 或 usage_update + stopReason）不动
- settle fire → yield `_TraePromptEvent(kind="completed", message="Task completed by the coco runner after the final chunk settled.", raw_result=...)`

#### 参数透传

- `CocoRunner.__init__` 新增 `completion_settle_seconds: float = 1.0`
- 在构造 `_TraeAcpPromptStream` 时，把 `self._timeout_seconds` 和 `self._completion_settle_seconds` 传进去

#### 不改的部分

- `_TraeAcpClient.request()` / `_TraeAcpClient._read_message()` 的公共接口语义
- `_execute_prompt` 的 strong terminal 分支文本
- factory.py / Settings
- 其他 backend

## 为什么这样选

- **分两轮 vs 合并**：两件改动都落在同几个方法内，分两轮意味着写两份 record 两次 diff；合并成本更低，review 面也更清晰
- **`_meta.lastChunk` 是 cleanest arm 信号**：比 cursor 的 "summary assistant" heuristic 确定得多，字段语义就是"结束"
- **`poll_timeout_seconds=None` 默认保留现有 `.request()` 阻塞语义**：避免无意改动 initialize / open_session 这类短同步调用

## 为什么不选其他方案

- **方案 A**：分两轮纯流程复杂度，没有实质收益
- **方案 C**：跳过 CompletionGate 就和前三个 backend 的队列语义不对称；`lastChunk` 成本太低，没有不加的理由

## 风险

- 单元测试里 `FakeSession.read_next_message` 的签名原本是 `() -> dict | None`。加参数会导致所有 FakeSession 要么改签名，要么用 `**kwargs` 接住。改 test fixture 接受 kwargs 风险极小
- `lastChunk: true` 判定必须精确。协议里布尔可能以 `True` / `"true"` / `1` 形式出现，先用 Python `is True` 精确匹配（保守），观察真实 server 行为后可放宽
- 把 `timeout_seconds` 和 `completion_settle_seconds` 透传到 `_TraeAcpPromptStream` 是小 refactor，但稀松的初始化风险需要 test 兜底

## 后续影响

- 四个 backend 的 completion 语义审计全部收口
- 下一个自然话题是"跨 backend 共享骨架"或新的 feature 队列
