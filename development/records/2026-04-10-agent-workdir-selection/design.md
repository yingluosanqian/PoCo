# Design

## 设计目标

让用户既能明确控制执行上下文，又不会因为配置入口过多而破坏移动端的连续工作流。

## 核心设计

### 1. 三层上下文模型

- `Project`
  - 持有 `agent_backend`
  - 持有 `repo_root`
  - 持有 `default_workdir`
  - 持有 `workdir_presets`
- `Session`
  - 持有 `project_id`
  - 持有 `agent_backend_snapshot`
  - 持有 `active_workdir`
  - 持有 `context_summary`
- `Task`
  - 持有 `session_id`
  - 持有 `effective_agent`
  - 持有 `effective_workdir`

### 2. Agent 作为 project identity

`agent` 不应被当作普通执行参数，而应被视为 project 的长期执行者。

因此：

- project 创建时在 DM 中选择 agent
- project 正常运行后，群内默认只展示当前 agent，不鼓励切换
- 如需变更 agent，应在 DM 中作为高级迁移动作处理，而不是普通切换器

### 3. Working Dir 作为 session stance

`working dir` 不应归 bot 全局，也不应在每次 task 中重新裸输入。

因此：

- project 在 DM 中维护 `default_workdir` 和 `workdir_presets`
- session 在群内持有当前 `active_workdir`
- 群内工作卡片允许切换当前 workdir、回退到 default、或选择 recent/preset

### 4. 交互面拆分

#### DM 卡片负责

- 创建 project 时选择 agent
- 查看 project 配置摘要
- 绑定 repo root
- 管理默认 workdir
- 管理 workdir presets
- 处理少量高级动作，如 agent migration

#### Group 卡片负责

- 展示当前 project 和当前 agent
- 展示当前 active workdir
- 切换当前 session 的 workdir
- 在当前上下文下发起 task

## 为什么这是更优雅的方案

- 它把“长期身份”与“当前站位”分开了
- 它把“管理动作”与“执行动作”分开了
- 它既保住了 agent continuity，也保住了 workdir flexibility
- 它符合已批准的 card-first 和 `DM / Group` 分层模型

## 后续实现含义

后续代码实现时，应优先补：

1. `session` 对象与 `active_workdir`
2. DM project detail card 中的配置摘要和入口
3. group workspace card 中的 workdir 切换入口

而不是先做 task 级自由输入。
