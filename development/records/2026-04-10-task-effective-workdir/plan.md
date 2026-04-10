# Plan

## 本轮计划

- 给 `Task` 增加最小执行上下文字段
- 让 group 消息入口解析 `project_id` 和当前 `active_workdir`
- 让 Codex runner 在执行时优先消费 `task.effective_workdir`
- 补足覆盖 task/controller、gateway、runner 的自动化测试

## 完成标准

- 群内 `/run` 创建出的 task 能看到 `project_id`
- 群内 `/run` 创建出的 task 能看到 `effective_workdir`
- Codex CLI 的 `-C` 和 `cwd` 使用 task 上解析出的目录
