# Design

## 设计目标

让 PoCo 的卡片交互具备统一、可维护的后端协议，而不是把行为分散在每一张卡片内部。

## 核心抽象

### 1. Action Intent

卡片点击事件在后端应先被解释成结构化意图，而不是直接执行某个按钮动作。

建议最小结构：

- `scope`
  `project` / `session` / `task` / `workspace`
- `kind`
  `open` / `create` / `bind` / `submit` / `approve` / `reject` / `continue` / `refresh`
- `target_id`
  指向 project、session 或 task
- `source_surface`
  `dm` / `group`

示例：

- `project.create`
- `project.bind_group`
- `workspace.open`
- `task.submit`
- `task.approve`
- `session.continue`
- `workspace.refresh`

### 2. Refresh Mode

卡片刷新不自由发挥，限定为三类：

- `replace_current`
  用新卡替换当前卡的主视图
- `append_new`
  新发一张状态卡，不回写旧卡
- `ack_only`
  仅返回轻量回执，不刷新主卡

### 3. Refresh Policy

不同动作和不同卡片使用预先定义的刷新策略。

## 模块/接口影响

- `interaction`
  未来需要新增 card action dispatcher
- `project/session/task`
  未来需要支持意图级动作，而不只支持文本命令
- `platform/feishu`
  未来需要把卡片回调事件转换成 `ActionIntent`

## 状态变化

建议最小映射如下：

### DM 管理卡片

- `Create Project`
  intent: `project.create`
  refresh: `replace_current`

- `Open Project`
  intent: `project.open`
  refresh: `replace_current`

- `Create/Bind Group`
  intent: `project.bind_group`
  refresh: `replace_current`

### 群工作区卡片

- `New Task`
  intent: `task.submit`
  refresh: `replace_current` 到 `Task Composer Card`

- `Submit`
  intent: `task.submit`
  refresh: `append_new`
  结果：回发新的 `Result / Status Card` 或 `Approval Card`

- `Continue Session`
  intent: `session.continue`
  refresh: `replace_current`

- `Approve`
  intent: `task.approve`
  refresh: `append_new`

- `Reject`
  intent: `task.reject`
  refresh: `append_new`

- `Refresh`
  intent: `workspace.refresh`
  refresh: `replace_current`

### 回执原则

- 会改变当前主视图语义的动作，优先 `replace_current`
- 会产生新状态事件的动作，优先 `append_new`
- 纯辅助动作或无状态副作用，允许 `ack_only`

## 方案比较

### 方案 A：自由 action / 自由刷新

优点：

- 前期实现阻力小

缺点：

- 后期极难维护

### 方案 B：统一意图协议 + 固定刷新模式

优点：

- 规则稳定
- 易于扩展
- 符合 MVP 克制原则

缺点：

- 前期需要先做协议设计

### 方案 C：按卡片各自定规则

优点：

- 可局部优化

缺点：

- 系统行为不一致

## 最终方案

采用方案 B。

卡片回调先进入统一 `ActionIntent`，再由后端决定执行逻辑和刷新模式；刷新行为限定为 `replace_current`、`append_new`、`ack_only` 三类。

## 风险与兼容性

- 若飞书卡片更新能力有限，`replace_current` 和 `append_new` 的实现边界需要在实现时再次核对官方文档
- 某些复杂交互可能需要未来引入第四种刷新模式，但当前不提前加
