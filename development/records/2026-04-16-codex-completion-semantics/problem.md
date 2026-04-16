# Problem

PoCo 当前 `CodexAppServerRunner` 的完成判定过于依赖少量协议事件的“乐观解释”。

已出现两类相反但同源的问题：

- task 还没有真正输出完，就被提前判成 `completed`
- task 的可见输出已经结束，但状态仍长期停在 `running`

真正的问题不是单个条件分支写错，而是：

- runner 把 `thread/status=idle`、`agentMessage item/completed`、短暂无消息 等信号混在一起直接当成终态
- 同时又缺少对“只有 delta、没有明确 terminal event”这类弱终态场景的保守兜底

这会直接破坏 PoCo 当前阶段的硬约束：

- 任务状态不清晰
- 移动端用户无法可靠判断 task 是否真的结束
- notifier / reconcile 的后续链路会建立在不稳定终态上

## 本轮不做

- 不重构所有 backend 的完成语义
- 不引入新的跨 backend 通用状态机抽象
- 不改变 task / notifier 的外部交互模型
