# Decision

## 当前决策

先落地最小 group card task 链：

- `workspace_overview` 增加 `Run Task`
- 新增 `task_composer`
- 新增 `task.submit`
- `task.submit` 直接复用已有 `project_id + effective_workdir + async dispatch` 主链

## 为什么这样选

- 这能最直接把 card-first 工作流推进到“真能发任务”
- 不需要先发明复杂 session/task 卡片体系
- 可以直接复用已经完成的 workspace context 和 task execution 改造

## 风险

- 当前 task 完成/等待确认后的回推仍主要是文本，不是结果卡
- 当前 task composer 仍是最小输入框，不含 richer parameters
