# Problem

PoCo 当前的 `project`、`workspace context` 和 `task` 全都只存放在内存里。

服务重启后会同时丢失：

- `group_chat_id -> project` 绑定
- `workspace_message_id`
- 当前 `active_workdir`
- `task.notification_message_id`
- 已存在 task 的最小历史

这导致群消息无法继续被路由到既有 project，workspace 卡也无法继续被同步更新。

这轮问题不是“完整 session 模型缺失”，而是“最小运行态状态没有持久化”。
