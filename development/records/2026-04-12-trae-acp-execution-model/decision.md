# Decision

采纳“`stable backend session + per-task ACP transport`”方案，并按 codex 的执行模型对齐 `coco`。

具体为：

- `backend_session_id` 继续代表稳定的 Trae backend session
- 每个 task 仍可拉起一个短生命周期的 `traecli acp serve` 传输进程
- 但 PoCo 必须显式定义“当前 task 的 prompt 边界、输出归属、完成信号、进程回收”
- `CocoRunner` 不再直接同时承担协议适配和 task 语义判定

## 为什么这样选

- 它与当前 PoCo 的 task-dispatch 架构兼容，不需要立刻引入 project 级常驻 runtime manager
- 它更接近现有 `CodexAppServerRunner` 的稳定模式：稳定的是 backend session，而不是本地 server 进程
- 它能优先解决当前最严重的问题：状态不清、输出串台、资源泄漏

## 为什么不选其他方案

### 不选继续沿用 `-p --json`

- 不满足流式要求
- 已经被用户明确否定

### 不选“先继续打补丁”

- 当前问题已经跨模块
- 若继续在实现层临时补规则，会继续放大 task/session 边界混乱

### 不选立即改成常驻 ACP runtime

- 会显著增加并发、存活检测、重启恢复、stop 映射复杂度
- 当前阶段优先级应是先把单条执行链做稳

## 当前明确不做

- 不在这一轮引入重连
- 不在这一轮实现 project 级常驻 ACP 进程池
- 不在这一轮统一重构所有 backend 的 runner 抽象

