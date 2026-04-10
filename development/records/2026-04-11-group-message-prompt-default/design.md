# Design

## 1. 目标

让群工作区更接近“和 agent 对话”，而不是“先打开表单再发任务”。

## 2. 新的入口语义

### DM

DM 继续承担 control plane 角色。

默认行为：

- 普通消息不创建 task
- 继续优先回 project / config / management 卡片

理由：

- DM 的主要职责是管理 project、建群、配置 agent、配置 repo / workdir
- 如果 DM 普通消息也默认触发任务，会把管理面和执行面重新混在一起

### Group

已绑定 project 的 group workspace 调整为“对话式 prompt intake”。

默认行为：

- 普通文本消息：创建 task
- 斜杠命令：按命令解释
- 卡片动作：继续作为状态、确认、配置、导航入口

这意味着 group 的默认语义从：

- “workspace card 是主输入入口”

调整为：

- “聊天消息是主输入入口，workspace card 是工作台”

## 3. 命令优先级

建议采用：

1. 空消息：忽略
2. 以 `/` 开头：命令路径
3. 其余普通文本：prompt 路径

这样能保留最小操作命令，不和自然消息冲突。

## 4. 对现有模块的影响

### `FeishuGateway`

影响中等，但集中。

当前 gateway 已经能：

- 识别 DM / Group
- 解析文本
- 解析绑定 project 和 active workdir
- 把文本交给 `InteractionService`

因此不需要重写入口，只需要把“群普通文本如何解释”这件事显式传下去。

建议新增一个显式上下文字段，例如：

- `message_surface=dm|group`
- 或 `message_mode=control|workspace`

避免 `InteractionService` 自己猜测来源语义。

### `InteractionService`

这是主要改动点。

当前它只接受：

- `/run ...`
- `/status ...`
- `/approve ...`
- `/reject ...`
- `/help`

新设计应调整为：

- 斜杠命令继续解析
- 当 `surface=group` 且文本不是命令时，直接走 task creation
- 当 `surface=dm` 且文本不是命令时，不创建 task，而是返回 DM 引导或管理入口

也就是把它从“命令解释器”提升为“带场景语义的文本入口服务”。

### `Card Handlers`

影响较小。

- `task_composer` 不需要删除
- 但它从“正式主入口”降级为“辅助入口”
- `workspace_overview` 的 `Run Task` 按钮文案可能需要调整，例如改成 `Run With Form` 或更弱化的备用入口

### `Task / Dispatcher / Runner`

影响很小。

任务创建、异步派发、状态更新、approval、notifier 都可复用。

## 5. 为什么不直接删掉 Run Task 卡片

不建议立即删除。

保留它有三个价值：

- 作为过渡期 fallback
- 承接未来结构化输入场景
- 在用户需要显式表单输入时提供备用入口

但它不再应该代表正式主路径。

## 6. 推荐实现原则

- `group text = default task prompt`
- `dm text != default task prompt`
- `slash commands remain operational`
- `cards handle state, config, approval, navigation`

## 7. 风险

### 误触发任务

如果群里任何普通文本都创建 task，用户闲聊或短句也会被触发。

MVP 阶段建议接受这个成本，但至少要满足两个前提：

- 仅在已绑定 project 的群里生效
- bot 明确回 task receipt / task status，让触发结果立即可见

后续若误触发明显，再考虑补：

- 明确 mention 才触发
- 或仅回复 bot / thread 内消息才触发

### 与 card-first 方向表面冲突

这不是放弃 card-first。

更准确地说，是把 card-first 从“主输入机制”收缩成“主状态与主控制机制”。

对于 PoCo 这种 agent 产品，这更符合高频使用场景。
