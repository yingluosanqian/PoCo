# TODO

这份文档记录一些已经讨论过、但当前**不是最高优先级**的方向。

## Codex App Server

### 1. 把 thread / session 可见化

当前 PoCo 已经在用 Codex app-server 的 `thread/start`、`thread/resume`、`turn/start`、`turn/interrupt`，但这些对象对用户仍然比较隐身。

后续可以考虑：

- 显示当前群绑定的 `thread id / session id`
- 显示这个 thread 是新建的还是 resume 的
- 显示 thread 对应的 `cwd`
- 显示当前 attach 的 session 的标题、第一句话或摘要
- 支持更明确的 `attach / detach / new thread`

这是当前三个方向里优先级相对更高的一项。

### 2. 把 runtime options 产品化

当前 Codex 主要通过这些底层配置运行：

- `model`
- `sandbox`
- `approval_policy`
- `reasoning_effort`

后续可以考虑把这组配置收成更容易理解的 profile，而不是一直直接暴露底层字段。

例如：

- `Safe`
- `Balanced`
- `Full Access`

再由 profile 映射到底层参数。

### 3. 把 turn 做成更完整的可管理对象

当前 turn 主要只用了：

- `start`
- `interrupt`

后续可以继续考虑：

- turn 状态展示
- `stop / steer / retry` 的统一设计
- turn 失败后的恢复语义
- turn 和 session/thread 关系的展示

## 备注

以上内容目前先作为待办记录，不在当前阶段优先实现。

## Claude Session 管理

这部分同样已经讨论过，但当前优先级低于其它 provider 接入工作。

后续可以考虑：

- 显示当前群绑定的 Claude `session id`
- 显示当前会话的 `cwd`
- 显示会话第一句话或摘要
- 明确区分：
  - `resume existing session`
  - `attach existing session`
  - `start new session`
- 在 DM / TUI / 群状态里把当前 Claude 会话显性化

这部分先保留在 TODO，不在当前阶段优先实现。
