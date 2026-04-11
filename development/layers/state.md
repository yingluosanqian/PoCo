# State Layer

## 本层定义

本层描述系统现状。

它负责说明系统现在有什么能力、有什么缺陷、背着什么负担，而不是描述未来理想状态。

## 本层关注的问题

- 系统当前能做什么
- 当前不能做什么
- 当前哪里脆弱、昂贵或难以维护
- 现有能力和负担分别是什么

## 输入

- 代码现状
- 运行现状
- 已知缺陷
- 历史设计负担
- 当前验证结果

## 输出

- 当前能力描述
- 当前缺陷描述
- 当前技术负担描述
- 与问题定义相关的事实基线

## 禁止事项

- 不要把理想方案写成当前状态
- 不要混淆“能力缺失”和“需求尚未定义”
- 不要把主观判断当事实
- 不要只说“很乱”“不好用”而不给出具体状态描述

## 进入下一层的条件

满足以下条件后，才能进入问题层：

- 能明确描述当前能力
- 能明确描述当前缺陷
- 能明确描述当前负担
- 这些描述足以支撑问题定义

## 如何区分三类状态

### 当前能力

系统已经稳定具备，且能被后续工作依赖的内容。

### 当前缺陷

系统应该完成但目前做不到，或做得不可靠的内容。

### 当前负担

系统虽然能运行，但未来演进要持续为之付出成本的结构性问题。

## PoCo 当前系统状态

### 当前能力

- repo 内已经建立基础开发治理结构，包括 `purpose`、`constraints`、`problems`、`decisions`、`plan`、`design`、`implementation`、`validation`、`state` 九层说明
- repo 内已经提供最小模板，可用于后续建立 `need`、`problem`、`decision`、`plan`、`design`、`validation` 实例记录
- 项目目的与项目约束已有第一版明确表述，可作为后续判断基准
- 已建立第一份可追溯演进记录，覆盖 `need/problem/decision/plan/design/validation`
- 已存在 Python 服务端 MVP 骨架，包括 `FastAPI` 应用、飞书事件网关、飞书请求校验、tenant access token 获取、文本消息回发、任务控制层、内存状态存储和 stub agent runner
- 已存在 Codex-first agent adapter，当前机器上可检测到本机 `codex` CLI
- 已存在进程内后台任务调度器与关键状态回推机制
- 已存在本地 demo HTTP 联调入口，可在不接飞书时直接验证任务流
- 已存在 `/debug/feishu` 调试快照，可查看最近回调、回复目标和错误
- 已存在 Feishu 长连接消息接收模式，可在本地开发时绕开公网 webhook 入口
- 已存在 card-first 的最小平台无关协议骨架和 dispatcher，可承接后续卡片交互实现
- 已存在最小 DM card 链路，包括 project 内存模型、card handlers、Feishu card gateway、renderer 和 demo card 入口
- 已存在真实 Feishu interactive card 发送能力，DM 消息当前可主动回发 project list card
- 已存在 DM 首页卡片上的首批真实 callback 动作，当前至少可点击创建 project，并在真实飞书模式下自动拉起对应工作群；新群会收到第一张 workspace overview card
- 已存在 DM `Project Config Card` 的最小实现，当前至少可只读展示 agent、repo、default workdir、workspace group，并进入对应的只读配置入口卡
- 已存在 Group `Workdir Switcher Card` 的最小实现，当前至少可只读展示 current agent、current workdir、source，并进入对应的只读目录切换入口卡
- 已存在最小 in-memory workspace context，当前 `Use Default` 已可把 `active_workdir` 和 `source=default` 写入当前群工作面的上下文状态
- 已存在第二条真实 workdir 写路径，当前 `Enter Path` 已可把手工输入目录写入 in-memory workspace context，并标记 `source=manual`
- 已存在最小 preset 存储与应用链路，当前可在 DM 中新增 project-level presets，并在群工作面应用为 `source=preset`
- 已存在从群工作面到 task 执行参数的最小落地链，当前群文本 `/run` 会解析绑定 project，并把当前 `active_workdir` 固化到 task 的 `effective_workdir`
- 已存在最小按-task 工作目录执行能力，当前 Codex runner 会优先在 task 指定目录下运行
- 已存在最小 card-first 发任务链，当前系统仍保留 `task_composer` / `task.submit` 这条内部任务创建路径，并可继承当前 workdir、触发异步 dispatch
- 已存在最小 task status card 链，当前等待确认和终态会发送 `task_status` card，并可通过卡片执行 `Approve` / `Reject`
- 已存在最小 task card 原位更新链，当前 notifier 首次发送 task status card 后会记录 message id，并在后续状态变化时优先更新同一张卡
- 已存在最小 task card 绑定链，当前 `task.submit` 会直接把当前 composer card 替换为 `task_status`，workspace 首卡也可打开 latest task
- 已存在最小 workspace 同步链，当前 workspace card 会绑定 message id，并在 task 状态变化时同步刷新 latest task 状态区块
- 已存在群文本直达 task 的底层主链，当前绑定 project 的群消息在 `/run ...` 形式下已经可直接创建 task，并继承当前 workdir
- 已存在群对话式 task intake，当前绑定 project 的群普通文本消息也会默认创建 task，并继承当前 workdir
- 已存在最小结果保真链，当前 `Task` 已保存 `raw_result`，task status card 会优先展示原始结果，超长结果可分页查看
- 已存在最小 task 卡信息收敛，当前 task id、status、agent、effective workdir 已进入标题，卡片正文默认只承载模型输出或确认说明
- 已存在最小运行期透明链，当前 running task 可携带 `live_output`，并驱动节流后的 task card 原位更新
- 已存在 group 文本直达单卡链，当前群文本创建 task 时会先收到一张初始 task card，后续状态与 live output 都会更新这张卡
- 已存在默认 sqlite 状态后端，当前 `project`、`workspace context` 和 `task` 已可跨服务重启恢复
- 已存在最小启动恢复逻辑，当前重启后仍可识别既有 `group_chat_id -> project` 绑定、workspace 卡绑定和当前 workdir 状态
- 已存在最小 `session/handoff` 运行态层，当前 project 下会自动创建并复用 active session，task 已开始保存 `session_id`
- 已存在最小 active session 展示，当前 workspace card 不再只显示占位文案，而会显示持久化的 session summary
- 当前 session 模型已收敛为“一个群一个稳定 session”，workspace card 不再暴露 session lifecycle 动作
- 已有最小自动化验证，覆盖核心任务状态流、飞书 challenge 校验、签名校验、Codex runner、后台调度器和本地 demo 接口
- 仓库当前结构仍较简单，尚无重型历史实现包袱

### 当前缺陷

- 当前飞书接入已具备第一层真实协议支持，但仍未覆盖加密事件体和真实端到端联调
- 当前长连接接入已覆盖消息事件和卡片回调，但真实飞书环境下的复杂卡片工作流仍未完成持续验证
- 当前 agent 执行已优先接入 Codex CLI，但仍未具备长任务编排、后台队列和真实执行器事件回传
- 当前后台调度仍基于进程内线程，不适合跨进程或重启后的任务追踪
- 当前系统仅维护 task state，尚未维护 session continuity 或产品级 handoff context
- 当前虽已具备最小 sqlite 持久化和最小 active session，但尚未实现完整 session continuity 或 backend execution context 恢复
- 当前 session 虽已可见且稳定，但仍未具备 session timeline 或 richer handoff 展示
- 当前系统已开始把 `agent` 与 `working dir` 的 ownership 落到实现里，真实写路径已覆盖 `Use Default`、`Enter Path` 和 `Choose Preset`
- 当前 workdir 已开始进入文本和 card 两条 task 创建路径，approval/result 也已有最小 card 链、原位更新和 task-card 绑定能力，但仍未形成完整 timeline 或 richer progress 视图
- 当前 group workspace 已开始转向“普通文本默认即 prompt”的正式语义，workspace 首卡不再承担发任务入口职责
- 当前 `agent` 与 `working dir` 的卡片信息架构已部分进入实现：DM 配置卡和群目录切换卡都已具备入口，但 `Use Recent` 仍未接入真实目录切换
- 当前系统尚未实现完整 project lifecycle 与正式 workspace card 工作流，正式交互模型仍未闭环
- 当前 DM 已能主动下发首页卡片，并具备第一批真实 callback 动作；但 project 命名、timeline、session/task 正式交互仍未形成完整正式工作流
- 当前正式实现仍是 DM 首屏卡片 + group workspace/task/status 混合态，workspace 和 task 已开始联动，但尚未形成完整 card-first 正式交互面
- 当前虽已有 card callback HTTP 入口和真实 interactive renderer，但尚未接入完整 group workspace、session/task handlers 和真实飞书端到端验证
- 当前权限模型、审计机制和敏感操作保护仍停留在约束层，没有落成实现
- 当前用户工作流已可接近真实消息交互，但尚未形成真实可用的手机端生产链路
- 当前仍缺少对真实飞书端到端流量的持续观测与错误可视化

### 当前负担

- 当前产品问题尚未正式收敛，容易把“消息入口形式”误当成核心问题
- 第一版实现依赖 stub runner，因此任务模型与真实 agent 事件之间仍有落差
- 若下一步直接并行推进真实飞书接入、持久化、权限和真实执行器，范围仍然容易再次失控
- 当前项目仍高度依赖发起人的脑内模型，很多产品判断尚未沉淀成更多可复述记录

### 当前阶段判断

PoCo 目前已从“纯项目定义期”进入“受控实现期”。

已经具备的条件：

- 项目存在理由已有第一版
- 项目边界与不可接受路径已有第一版
- 第一轮问题、决策、计划、设计已建立 record
- Python MVP 骨架已经落地，并完成最小验证

尚未具备的条件：

- 尚未具备完整平台级可用性
- 尚未具备完整执行器体系
- 尚未具备持久化、可恢复后台队列、权限与安全闭环
- 尚未具备完整 session 持久化和可恢复 worker 闭环
