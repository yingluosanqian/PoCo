# Design Layer

## 本层定义

本层负责描述被采纳方案如何组织成可实现的结构。

它关注抽象、接口、模块、状态和边界，而不是具体代码细节。

## 本层关注的问题

- 这轮变更需要什么核心抽象
- 模块和接口如何变化
- 状态如何流动或持久化
- 为什么采用当前方案而不是其他设计

## 输入

- 计划
- 当前系统状态
- 已知约束
- 需要比较的候选方案

## 输出

- 设计记录
- 抽象说明
- 接口与模块影响
- 状态变化说明
- 方案比较和最终选择

## 禁止事项

- 不要把实现细节堆成设计
- 不要只给结论，不给边界和影响
- 不要在没有设计记录时做显著抽象升级
- 不要用设计层重新改写已批准范围

## 进入下一层的条件

满足以下条件后，才能进入实现：

- 核心抽象已经明确
- 模块和接口影响已经明确
- 状态变化已经明确
- 主要方案比较已经完成

## 何时需要 design record

出现以下任一情况时，应建立 `design`：

- 新增核心抽象
- 新增或重构模块边界
- 接口变化影响多个调用方
- 状态模型变化
- 存在多个明显可选方案

## PoCo 当前设计方向

### 当前设计目标

在飞书优先的前提下，先设计一条完整的单平台主链路，而不是直接实现平台接入代码。

### 当前核心抽象

- 飞书消息入口适配层
- 飞书传输模式适配，允许 webhook 与 long connection 共用同一消息网关
- `DM control plane + group workspace` 的双入口交互模型
- group workspace 中“普通文本默认即 prompt”的对话式任务入口
- `project -> session -> task` 的执行上下文分层，其中 `agent` 归 project，`working dir` 归 session
- 最小运行态持久化层：`project / workspace context / task -> sqlite`
- 最小 `session/handoff` 运行态层：`project -> active session -> task`
- card-first interaction model，正式交互由卡片驱动而不是文本命令驱动
- 分层卡片信息架构：DM 管理卡片与群工作区卡片
- 面向执行上下文配置的最小卡片 IA：`DM Project Config Card` 与 `Group Workdir Switcher Card`
- task 结果保真展示链：`raw_result` 为主，卡片分页为辅
- task 运行期透明链：runner 增量输出 -> `live_output` tail -> 节流后的 task card 原位更新
- 统一 card action intent 协议与固定 refresh mode
- 统一 ActionIntent payload、资源级 handler ownership 与写操作幂等约束
- `IntentDispatchResult -> PlatformRenderInstruction -> Renderer` 的平台解耦链路
- 平台无关的任务控制核心
- 最小 `session/handoff` 连续性交接层
- 服务器侧 agent 执行层
- 最小任务状态存储
- 人工确认检查点

### 当前设计边界

- 飞书平台细节应限制在入口适配层
- 核心执行必须围绕任务和状态，而不是裸命令透传
- project 管理动作不应与正式执行消息混在同一入口
- `DM` 与 `Group` 不应共享完全相同的默认消息语义
- `agent` 不应被当作群内可随手切换的普通参数
- `working dir` 不应被当作 bot 全局常量，也不应退化为 task 级裸输入
- 文本命令不应继续定义正式用户体验
- 产品级连续性交接上下文应由 PoCo 维护，但不复制 backend 的完整执行期上下文
- 当前设计只服务单平台、单主链路 MVP，不覆盖多平台协作扩展

### 当前设计取向

优先采用“薄平台适配 + 独立任务核心”的结构，避免在 MVP 阶段走向完全耦合或过度抽象两端。

在正式交互面上，优先采用“少量分层卡片”而不是万能卡片或完整卡片体系。

在群发任务入口上，优先采用“自然消息是主入口、卡片是工作台”的结构，而不是继续把卡片输入框作为唯一 prompt intake。

在执行上下文配置上，优先采用“慢变量放 DM，快变量放群”的结构，而不是单一配置面板或 task 级随意重配置。

在卡片信息架构上，优先把 `agent` 配置收敛到 DM project config card，把 `working dir` 切换收敛到 group workdir switcher card，而不是让两者共享首屏。

在状态恢复上，优先保证“重启后还能识别既有 workspace 和当前工作面”，而不是提前承诺完整 session 恢复。

在 session 设计上，优先采用“单 project 单 active session”的最小连续性模型，而不是一开始就进入多 session 分叉。
