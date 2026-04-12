# Design

## 核心抽象

### `TraeAcpClient`

职责：

- 启动和关闭 `traecli acp serve`
- 处理 `initialize`
- 发送 `session/new` / `session/load`
- 发送 `session/set_mode`
- 发送 `session/prompt`
- 顺序读取 ACP 消息
- 统一回收 `stdin/stdout/stderr` 和子进程

它不负责：

- 判断 task 是否应 `completed`
- 把任意 update 直接翻译成 PoCo task 状态

### `CocoRunner`

职责：

- 将 PoCo task 映射到一次 ACP prompt 执行
- 保存和回写 `backend_session_id`
- 只消费属于当前 task 的有效输出
- 将协议事件转成 `AgentRunUpdate`

它不负责：

- 直接解析底层进程资源细节

## 状态关系

- `PoCo project/group session`：产品级稳定容器
- `backend_session_id`：Trae backend 的稳定上下文标识
- `task`：当前 prompt 的一次执行
- `ACP transport process`：一次 task 使用的短生命周期通信通道

也就是：

- 稳定的是 `backend_session_id`
- 短生命周期的是 ACP transport
- `task` 不能直接等同于整个 Trae session

## 输出归属规则

`CocoRunner` 需要把 ACP 消息分三类：

1. 会话准备类
   - `initialize`
   - `session/new`
   - `session/load`
   - `session/set_mode`
   这些不会写入 task output

2. 本轮 prompt 输出类
   - 仅在发出本次 `session/prompt` 之后开始观察
   - 仅接收可归属到当前 assistant message 的 chunk
   - 历史 replay 或 load 后的非本轮 update 不写入 `live_output`

3. 终态类
   - 当前 prompt 的正式完成响应
   - 或被设计认可的等价终态 update
   - 才能驱动 `completed` / `failed`

## 完成语义

优先级：

1. `session/prompt` 的正式响应
2. 被验证可靠的终态 update
3. 进程异常退出视为 `failed`

如果只有 chunk、没有可靠终态证据：

- 允许继续保持 `running`
- 不允许仅因“看起来像最后一块”就乐观完成，除非该信号被验证稳定

## 与 codex 的对齐点

- 都采用“稳定 backend session + 短生命周期本地传输进程”
- 都要求把协议适配和 task 语义分开
- 都要求有明确的本轮边界和完成信号

## 与 codex 的不同点

- codex 有显式 `thread/start|resume + turn/start + turn/completed`
- Trae ACP 当前未证明有同等级清晰的 turn 语义
- 因此 `coco` 不能机械照搬 codex 的事件判定

## 模块影响

- `poco/agent/runner.py`
  - 新增 `TraeAcpClient`
  - 收敛 `CocoRunner`
- `tests/test_agent_runner.py`
  - 增加 task 边界、终态和资源清理测试
- `development/developer-docs/backends.md`
  - 更新 `coco` 的真实能力与限制说明

