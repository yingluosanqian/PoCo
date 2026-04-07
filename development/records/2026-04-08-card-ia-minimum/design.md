# Design

## 设计目标

用尽可能少的卡片类型覆盖 PoCo 第一版正式交互，避免在 DM 与群里堆叠过多入口。

## 核心抽象

### 1. DM Project List Card

用途：

- 作为 DM control plane 首页

最小字段：

- project 名称
- 当前绑定状态
- 最近活动摘要
- 默认 backend

最小动作：

- `Create Project`
- `Open Project`
- `Create/Bind Group`

### 2. DM Project Detail Card

用途：

- 查看和管理单个 project

最小字段：

- project 名称
- repo / workdir 摘要
- 绑定群信息
- 默认 backend
- 最近 session 摘要

最小动作：

- `Create Group`
- `Bind Existing Group`
- `Open Workspace`
- `Archive Project`

### 3. Group Workspace Overview Card

用途：

- 作为 project 群里的工作区首页

最小字段：

- project 名称
- 当前 active session 摘要
- 最近任务状态
- 待处理确认数量
- 最近结果摘要

最小动作：

- `New Task`
- `Continue Session`
- `View Pending Approvals`
- `Refresh`

### 4. Task Composer Card

用途：

- 在群中发起新任务或延续任务

最小字段：

- 当前 project
- 当前 session 摘要
- prompt 输入区域
- backend 指示

最小动作：

- `Submit`
- `Cancel`

### 5. Approval Card

用途：

- 承载等待确认的任务动作

最小字段：

- task 摘要
- 需要确认的原因
- 风险提示
- 最近上下文摘要

最小动作：

- `Approve`
- `Reject`
- `View Details`

### 6. Result / Status Card

用途：

- 展示任务终态或关键进展

最小字段：

- task 状态
- 结果摘要或失败摘要
- 所属 session
- 下一步建议

最小动作：

- `Continue`
- `Open Workspace`
- `Dismiss`

## 模块/接口影响

- `interaction`
  需要从“命令解析”提升为“卡片动作 + 状态视图”双向层
- `project/session/task`
  需要提供适配卡片的最小 view model
- `platform/feishu`
  需要支持 DM 卡片与群卡片两类回调

## 状态变化

最小状态流建议为：

1. 用户在 DM 打开 `Project List Card`
2. 进入 `Project Detail Card` 创建或绑定群
3. 在群中展示 `Workspace Overview Card`
4. 用户通过 `Task Composer Card` 发起任务
5. 若需要人工确认，进入 `Approval Card`
6. 完成后展示 `Result / Status Card`
7. 用户可从结果卡继续回到 workspace 或继续 session

## 方案比较

### 方案 A：万能卡片

优点：

- 类型少

缺点：

- 职责混乱
- 维护成本高

### 方案 B：最小分层卡片集合

优点：

- 与当前交互模型一致
- 可控且易于实现

缺点：

- 需要少量卡片切换

### 方案 C：完整卡片体系先行

优点：

- 覆盖最全

缺点：

- 超出当前阶段范围

## 最终方案

采用方案 B。

第一版先用 6 类最小卡片覆盖 project 管理、workspace 状态、任务发起、确认和结果查看。

## 风险与兼容性

- `Task Composer Card` 若交互能力不足，可能需要退回到弹窗或二级卡片
- `Result / Status Card` 需要克制信息量，避免重新做成“卡片版日志流”
- DM 与群之间的跳转方式后续仍需细化
