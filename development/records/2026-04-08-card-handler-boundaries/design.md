# Design

## 设计目标

把卡片交互从“概念上统一”推进到“可以直接编码”的协议边界。

## 核心抽象

### 1. ActionIntent Payload

建议最小 payload：

- `intent_key`
  例如 `project.create`、`task.approve`
- `surface`
  `dm` / `group`
- `project_id`
  可空；DM 列表页时可为空
- `session_id`
  可空
- `task_id`
  可空
- `actor_id`
  触发用户
- `source_message_id`
  来源卡片或消息 id
- `request_id`
  本次动作唯一标识，用于幂等
- `payload`
  动作附加字段，例如表单输入内容

约束：

- 业务 handler 不直接依赖按钮文案
- 除 `payload` 外，其余字段尽量固定

### 2. Handler Ownership

建议按资源边界分四类 handler：

- `ProjectIntentHandler`
  处理 `project.create`、`project.open`、`project.bind_group`、`project.archive`

- `WorkspaceIntentHandler`
  处理 `workspace.open`、`workspace.refresh`

- `SessionIntentHandler`
  处理 `session.continue`

- `TaskIntentHandler`
  处理 `task.submit`、`task.approve`、`task.reject`

约束：

- project handler 不直接推进 task 状态
- task handler 不负责 project lifecycle
- workspace handler 只处理视图级导航与刷新，不直接创建业务实体

### 3. Idempotency Rule

按动作级别区分：

- 写操作默认必须幂等
  例如 `project.create`、`project.bind_group`、`task.submit`、`task.approve`、`task.reject`

- 读/导航操作允许轻量非幂等
  例如 `project.open`、`workspace.refresh`、`session.continue`

建议最小规则：

- 相同 `request_id` 的写操作重复到达时，不重复执行副作用
- 已进入终态的 `task.approve` / `task.reject` 重复提交时返回稳定结果，而不是再次修改状态

## 模块/接口影响

- `interaction`
  未来需要 `CardActionDispatcher`
- `project/session/task`
  未来需要资源级 intent handler
- `storage`
  未来至少需要记录已消费的写操作 request id

## 状态变化

最小处理流建议：

1. 飞书卡片回调进入平台适配层
2. 平台适配层转换成统一 `ActionIntent Payload`
3. Dispatcher 按 `intent_key` 路由到对应 handler
4. handler 返回业务结果 + refresh decision
5. 平台层按 refresh mode 更新卡片

## 方案比较

### 方案 A：扁平 handler

优点：

- 初期文件少

缺点：

- 资源边界会迅速混乱

### 方案 B：资源级 handler + 幂等写操作

优点：

- 结构清晰
- 更适合长期演进

缺点：

- 前期设计要求更高

### 方案 C：先不做幂等

优点：

- 实现更快

缺点：

- 审批和提交会变得危险

## 最终方案

采用方案 B。

用统一 payload 包装层承接卡片动作，按资源边界拆 handler，并对写操作默认启用幂等保护。

## 风险与兼容性

- `request_id` 的来源需要在实现时与飞书回调能力核对
- 若部分动作天然跨资源，后续可能需要 orchestration 层，但当前不提前加
