# Problem

## 背景

见 `need.md`。

## 相关需求

- 用户不用记 thread_id 也能接管历史 session（下拉选择）
- 但如果用户有一个 PoCo 从没见过的外部 id，也要能粘贴进来（兜底文本输入）

## 当前状态

### Session 模型

- `Session`：1-per-project，auto-created。字段含 `backend_session_id`
- `SessionController.create_session(project_id, created_by)`：如果 project 已有 active session，直接返回既有的；否则新建
- 没有任何修改既有 session 的 `backend_session_id` 的方法。目前只在 `update_from_task` 里由任务结果带回
- 没有枚举历史上用过的 `backend_session_id` 的方法

### 任务历史

- `Task` 里存 `backend_session_id`、`agent_backend`、`prompt`、创建时间
- `TaskStore.list_all()` 可返回全部任务
- 没有跨项目聚合 session 的 helper

### 卡片链路

workdir 选择流程作为参照模板：

- `workspace.choose_preset` 打开 choose 卡（下拉/按钮列表）
- `workspace.apply_preset_dir` / `workspace.enter_path` / `workspace.apply_entered_path` 覆盖了"选一个"和"手输"两条子路径
- 每条 apply 完后返回 workspace overview

session attach 目前**完全没有对等链路**。

## 问题定义

**PoCo 没有"把 project 的 active session 覆盖成外部 backend_session_id"的路径**，既没有 UX、也没有 SessionController 方法、也没有从任务历史聚合 session 清单的 helper。

## 为什么这是个真实问题

- 用户明确提出需求
- purpose.md 里"在移动端接管远端 agent 工作"明确把这种接管场景作为核心
- workdir 已经有了类似的两段式（选 preset + 手输）UX 模板，照抄成本低

## 不是什么问题

- 不是"session resume 坏了"：auto resume 一直正常工作
- 不是"session 模型需要重构"：只加一个改 backend_session_id 的方法就够
- 不是"要记录 session 完整元信息"：只需要去重 + 简单 label

## 证据

- `poco/session/controller.py`：无 attach / set_backend_session 方法
- `poco/task/controller.py`：无跨项目聚合 session 的 helper
- `poco/interaction/card_handlers.py::WorkspaceIntentHandler`：无 session-related intent
- `poco/platform/feishu/cards.py`：无对应 template
