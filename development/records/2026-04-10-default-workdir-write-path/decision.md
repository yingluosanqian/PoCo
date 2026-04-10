# Decision

## 当前决策

先把 `workspace.use_default_dir` 升级为第一条真实写路径：

- 引入最小 in-memory `workspace context`
- 记录 `active_workdir`
- 记录 `workdir_source`
- 先只支持 `source=default`

## 为什么这样选

- 它风险最小，不需要先完成完整 session 持久化
- 它和已有 `project.workdir` 天然对齐
- 它能验证群侧 workdir 切换是否真的需要独立上下文层

## 风险

- 当前仍然是 in-memory，服务重启后会丢
- 真实 task 执行链路还未消费这份 context
