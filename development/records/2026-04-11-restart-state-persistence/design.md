# Design

## 持久化范围

### Project

持久化：

- `id`
- `name`
- `created_by`
- `backend`
- `repo`
- `workdir`
- `workdir_presets`
- `group_chat_id`
- `workspace_message_id`
- `archived`
- 时间戳

### Workspace Context

持久化：

- `project_id`
- `active_workdir`
- `workdir_source`
- `updated_at`

### Task

持久化：

- task 身份与来源
- `project_id`
- `effective_workdir`
- `notification_message_id`
- 回复目标
- `status`
- `awaiting_confirmation_reason`
- `live_output`
- `raw_result`
- `result_summary`
- `events`
- 时间戳

## 启动恢复策略

- `completed/failed/cancelled/waiting_for_confirmation` task 原样保留
- `created/running` task 视为被服务重启打断
- 启动时将其标记为 `failed`
- 保留历史事件，并追加 `task_interrupted`

## 设计边界

这次不是完整 session 持久化。

当前恢复的是：

- project 识别
- group workspace 识别
- 当前 workdir stance
- task 卡绑定

不是：

- backend execution context 恢复
- 真正 session lineage 恢复
- 长任务断点续跑
