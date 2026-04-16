# Plan

## 目标

按 `decision.md` 实现：workspace 卡上多一个 "Session" 按钮，能够下拉选 + 手输 attach 到任意 backend_session_id，覆盖当前 project 的 active session。

## 范围

### 后端（controller / model 层）

- `poco/session/controller.py`：
  - `SessionController.attach_backend_session(project_id: str, backend_session_id: str | None, *, created_by: str) -> Session`
    - 拿到或创建该 project 的 active session
    - 覆盖 `backend_session_id`（None 表示清空 / "Start Fresh"）
    - 更新 `updated_at`
    - save 并返回
- `poco/task/controller.py`：
  - `TaskController.list_known_backend_sessions(*, backend: str) -> list[KnownSession]`
    - 遍历 `_store.list_all()`
    - 过滤 `task.agent_backend == backend and task.backend_session_id`
    - 按 `backend_session_id` 去重，保留"最近一次使用"的 task 作为 label 来源
    - 按 task 创建时间（或更新时间）倒序
    - **不设上限**
    - 新 dataclass `KnownSession`：`backend_session_id` / `project_id` / `project_name` / `first_prompt_preview` / `last_used_at` 等
  - 若跨 project 聚合需要 project 名字，接受一个 `project_name_resolver: Callable[[str], str | None]` 或在外部 join

### 交互层（intent handlers）

- `poco/interaction/card_handlers.py::WorkspaceIntentHandler`：新增 4 个 intent 分支
  - `workspace.choose_session` → `_open_choose_session(intent)` → view_model 列出符合条件的 `KnownSession` 列表 + "Enter ID" / "Start Fresh" 按钮
  - `workspace.apply_session` → `_apply_session(intent)` → 从 payload 取 `backend_session_id`（必须匹配某条已知 id）→ `SessionController.attach_backend_session` → 返回 workspace overview
  - `workspace.enter_session_id` → `_open_enter_session_id(intent)` → view_model 单输入框
  - `workspace.apply_entered_session_id` → `_apply_entered_session_id(intent)` → 从 form_value 取 id（允许任意非空字符串）→ attach → 返回 workspace overview
  - `workspace.clear_session` → `_clear_session(intent)` → attach(None) → 返回 workspace overview

### 渲染层（cards）

- `poco/platform/feishu/cards.py`：
  - 识别两个新 template_key：`workspace_choose_session` / `workspace_enter_session_id`
  - `_render_workspace_choose_session(...)`：标题 + 下拉 select + 两个按钮
    - 下拉 options: 按 KnownSession 列表构建 `[(label, backend_session_id)]`，empty list 时显示空状态文本
    - "Enter ID" 按钮 behavior: `workspace.enter_session_id`
    - "Start Fresh" 按钮 behavior: `workspace.clear_session`
    - "Apply" 按钮: `workspace.apply_session`
  - `_render_workspace_enter_session_id(...)`：单 text input + Apply 按钮 + Cancel 回到 choose 卡

### 视图模型

- `poco/interaction/card_models.py` 或 `card_handlers.py` helper：
  - `_workspace_choose_session_view_model(project, sessions: list[KnownSession], active_backend_session_id: str | None)` 返回 ViewModel 里 `template_key="workspace_choose_session"` 加数据
  - `_workspace_enter_session_id_view_model(project, current_backend_session_id: str | None)` 返回 ViewModel with `template_key="workspace_enter_session_id"`

### Dispatcher 注册

- `poco/main.py` / `poco/platform/feishu/card_gateway.py`：`CardActionDispatcher` intent map 里加 5 个新 key 指向 `WorkspaceIntentHandler`

### Workspace Overview 入口按钮

- 在 `build_workspace_overview_result` 或对应 renderer 里，`Session` 按钮和现有的 `Working Dir` / `Agent` 并列出现（group surface），行为 → `workspace.choose_session`

## 不在范围内的内容

- per-task session 覆盖
- session fork / rename / 删除
- session 列表的分页
- session 过期检查（不提前 validate backend 是否还持有该 thread）

## 风险点

- **下拉 value 长度**：飞书 card select 的 value 长度限制。codex thread_id 通常 36 字符，claude session_id 类似，落在安全范围
- **空状态**：新 project 的用户打开 choose 卡时历史为空，需要 graceful 渲染（仅显示 "Enter ID" / "Start Fresh"）
- **跨 project 历史**：`list_known_backend_sessions` 需要 project 名字，而 TaskController 没有 ProjectController 依赖。决策：在 handler 层注入 `project_controller.get_project` 做 lookup，不让 task_controller 持有 project_controller
- **Test fixtures**：已有 `test_card_gateway.py` 有完整 workspace intent 测试 setUp，可直接扩展

## 验收标准

1. `uv run --extra dev pytest -q tests/test_session_controller.py`：已有 + 新 attach 方法全绿
2. `uv run --extra dev pytest -q tests/test_task_controller.py`：已有 + 新 list 方法全绿
3. `uv run --extra dev pytest -q tests/test_card_gateway.py`：已有 + 新 5 个 intent 分支全绿（下拉 apply、手输 apply、choose view_model、enter view_model、clear）
4. 广扫测试集：所有 baseline 测试无回归
5. 空状态（项目无历史）渲染不抛异常
6. 外部任意非空 id 手输可覆盖成功

## 实施顺序

1. Session controller + 单测
2. Task controller list helper + 单测
3. Card handlers 五个 intent 分支 + dispatcher 注册
4. View model helper
5. Card renderer 两个新 template
6. Workspace overview 集成 "Session" 按钮
7. 跑测试
8. 更新 validation
