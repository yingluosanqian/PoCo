# Implementation Layer

## 本层定义

本层负责在被批准的边界内落地实现。

本层不是重新定义问题、重新做决策或重新扩展范围的地方。

## 本层关注的问题

- 如何把已批准方案落成代码
- 如何最小化对既有系统的无关扰动
- 如何确保实现与计划、设计一致

## 输入

- 已批准的 `problem`
- 已批准的 `decision`
- 已定义的 `plan`
- 必要时的 `design`

## 输出

- 代码变更
- 与实现直接相关的最小文档更新
- 可验证的实现结果

## 禁止事项

- 不要在实现时扩大问题边界
- 不要把未批准内容顺手做掉
- 不要用“代码里顺便处理”代替设计或决策
- 不要把 scratch、废案、中间分析文件提交进 repo

## 进入下一层的条件

满足以下条件后，才能进入验证：

- 实现结果与批准范围一致
- 关键行为已有可验证输出
- 相关文档已补足到最低要求

## AI 实现约束

- AI 必须把实现视为受约束执行，而不是自由探索
- AI 必须在边界不清时停止，而不是继续猜测
- AI 必须显式说明未验证部分
- AI 不得把临时工作产物写入稳定目录

## 实现与设计的边界

- 设计回答“怎么组织”
- 实现回答“怎么落地”

当实现需要改动抽象、接口或边界时，应返回设计层，而不是继续扩写代码

## PoCo 当前实现摘要

### 当前实现目标

先搭建 Python 服务端 MVP 骨架，验证飞书优先主链路在代码结构上可落地。

### 当前实现范围

- `FastAPI` 作为 webhook 服务入口
- 飞书事件网关的最小适配
- 飞书 callback verification token 与签名头校验
- 飞书 tenant access token 获取、文本消息回发与 interactive card 发送
- 平台无关的任务控制层
- Codex-first agent adapter 与本机 Codex CLI 调用
- 进程内后台任务调度与关键状态回推
- 本地 demo HTTP 联调入口
- 内存版任务状态存储
- stub agent runner
- card-first 的最小平台无关协议骨架，包括 `ActionIntent`、`IntentDispatchResult`、`PlatformRenderInstruction`、`CardActionDispatcher` 和最小幂等缓存
- 最小 project 领域模型、DM card handlers、Feishu card gateway、card renderer 和本地 demo card 入口
- DM 收到消息后主动回发 project list card 的最小 bootstrap 链路
- DM 首页卡片上的首批真实 callback 动作，包括 `project.create`、`project.open`、`workspace.open` 和 `workspace.refresh`
- `project.create` 在真实飞书模式下会同时调用建群 API，并把返回的 `chat_id` 绑定回 project；失败时会回滚 project 创建
- 建群绑定成功后，会 best-effort 向新群发送第一张 workspace overview card
- DM 侧已把 `project.open` 升级为 `Project Config Card`，并提供只读的 agent / repo / default dir / dir preset 入口卡
- Group 侧已新增 `Workdir Switcher Card` 的最小实现，并提供 default / preset / recent / manual path 的只读入口卡
- `workspace.use_default_dir` 已升级为真实写路径，会更新当前 in-memory workspace context 中的 `active_workdir`
- `workspace.apply_entered_path` 已升级为真实写路径，会把手工输入目录写入当前 in-memory workspace context，并标记 `source=manual`
- `project.add_dir_preset` 与 `workspace.apply_preset_dir` 已升级为真实写路径，允许在 DM 管理 project-level presets，并在群工作面应用 `source=preset`
- group 文本 `/run` 已开始解析 `chat_id -> project`，并把当前 workspace context 固化到 task 的 `project_id` / `effective_workdir`
- Codex runner 已开始优先消费 task 的 `effective_workdir`，而不是只使用全局 `POCO_CODEX_WORKDIR`

### 当前明确未实现

- 飞书卡片 2.0 驱动的完整正式交互面
- 飞书卡片端到端正式工作流，以及 project/session/task/group 的完整 card handlers
- 飞书加密事件体处理
- Claude Code 与 Cursor Agent 执行适配
- 跨进程可恢复的任务队列
- 持久化数据库
