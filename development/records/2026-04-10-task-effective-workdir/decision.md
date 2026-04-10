# Decision

## 当前决策

先落地最小执行链：

- group 消息入口按 `chat_id -> project`
- task 创建时固化 `project_id` 和 `effective_workdir`
- Codex runner 优先使用 `task.effective_workdir`

## 为什么这样选

- 这直接把现有 workspace context 接到真实执行链上
- 不需要先引入完整 session 模型
- 范围受控，只影响当前 group 文本 fallback 执行路径

## 风险

- 当前只覆盖群文本 `/run`，还没覆盖未来 card-first task submit
- 当前 backend snapshot 仍未从 project 级选择真正下沉到多 runner 分发
