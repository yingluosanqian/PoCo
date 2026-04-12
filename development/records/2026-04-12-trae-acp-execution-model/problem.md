# Problem

PoCo 当前的 `coco/traecli` 执行链还没有形成和现有 task/session 模型一致的运行时边界。

表面现象包括：

- task 已有输出但卡片仍停在 `running`
- 输出内容可能串入旧 session 的历史片段
- PoCo 主进程出现 `Too many open files`，随后 `/health` unavailable

真正的问题不是“Trae CLI 偶尔不稳定”，而是：

- PoCo 还没有明确 `Trae ACP session`、`PoCo session`、`task` 三者之间的关系
- 当前实现把 ACP 当成类似 codex app-server 的协议后端直接接入，但没有先定义本轮 prompt 的边界和完成条件
- 子进程生命周期和协议事件归属都没有被设计清楚

## 为什么这是真问题

- 它直接破坏 PoCo 的核心目的：用户需要在手机上低摩擦地发起、跟进、确认和收取结果
- 它违反当前约束：任务状态不清晰、服务可用性下降、实现边界靠运行时猜测而不是明确设计
- 它不是单个局部 bug；已经跨 `runner / task / notifier / session` 模块

## 不是什么问题

- 不是 UI 首要问题
- 不是是否支持 `Trae CLI` label 的问题
- 不是要不要立刻做断线重连的问题
- 不是所有 backend 都要统一重构的问题

## 证据

- task 会出现输出存在但未可靠完成收口
- `session/load` 后能观察到非当前 prompt 的 `session/update`
- PoCo 日志已出现 `OSError: [Errno 24] Too many open files`
- 随后出现 `sqlite3.OperationalError: unable to open database file`
- 当前 `poco status` 可见 health unavailable

