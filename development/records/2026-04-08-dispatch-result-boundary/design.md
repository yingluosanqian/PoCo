# Design

## 设计目标

让业务层在不依赖平台 schema 的前提下，仍能完整表达“发生了什么、应该展示什么、应该如何刷新”。

## 核心抽象

### 1. IntentDispatchResult

业务层返回的统一结果对象。

建议最小字段：

- `status`
  `ok` / `rejected` / `error`
- `intent_key`
  本次处理的 action intent
- `resource_refs`
  相关的 `project_id` / `session_id` / `task_id`
- `view_model`
  平台无关的视图数据对象
- `refresh_mode`
  `replace_current` / `append_new` / `ack_only`
- `message`
  轻量说明文字，供回执或调试使用

职责：

- 表达业务处理结果
- 表达推荐刷新模式
- 提供渲染所需的业务视图数据

### 2. ViewModel

业务层产出的平台无关视图对象。

建议最小类型：

- `project_list`
- `project_detail`
- `workspace_overview`
- `task_composer`
- `approval`
- `result_status`

约束：

- view model 只描述“要展示什么”，不描述飞书组件长什么样

### 3. PlatformRenderInstruction

平台层根据 `IntentDispatchResult` 生成的渲染指令。

建议最小字段：

- `surface`
  `dm` / `group`
- `render_target`
  当前卡片 / 新消息 / 轻量回执
- `template_key`
  选择哪种卡片模板
- `template_data`
  平台模板所需的数据
- `refresh_mode`
  最终执行的刷新模式

职责：

- 把业务 view model 映射成平台模板选择
- 不引入新的业务决策

## 模块/接口影响

- `interaction`
  dispatcher 输出 `IntentDispatchResult`
- `view_model`
  未来需要成为独立抽象
- `platform/feishu`
  未来需要把 `IntentDispatchResult` 转成 `PlatformRenderInstruction`

## 状态变化

建议最小链路：

1. `ActionIntent` 进入 dispatcher
2. handler 返回 `IntentDispatchResult`
3. 平台适配层读取 result，生成 `PlatformRenderInstruction`
4. renderer 按 instruction 输出飞书卡片

## 方案比较

### 方案 A：handler 直接回卡片

优点：

- 看似最直接

缺点：

- 平台耦合严重

### 方案 B：result + render instruction 双层边界

优点：

- 业务和平台职责清楚
- 更符合长期演进

缺点：

- 前期要多定义一层对象

### 方案 C：平台层猜测渲染

优点：

- 前期少写对象

缺点：

- 平台层会藏业务逻辑

## 最终方案

采用方案 B。

dispatcher 只返回平台无关的 `IntentDispatchResult`；平台层只负责把结果翻译成 `PlatformRenderInstruction`，renderer 再输出具体卡片。

## 风险与兼容性

- 若 `view_model` 粒度过粗，平台层仍可能需要拆字段
- 若 `view_model` 粒度过细，又会增加对象数量
- 飞书模板能力的真实边界仍需在实现时核对官方文档
