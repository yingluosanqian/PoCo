# Decision

## 当前决策

把 `workspace.apply_entered_path` 作为第二条真实 workdir 写路径：

- 从 `workspace.enter_path` 输入卡读取路径
- 写回当前 in-memory workspace context
- 把 `workdir_source` 标记为 `manual`

## 为什么这样选

- 它直接复用上一轮引入的 workspace context
- 它是对用户最直接的 fallback 路径
- 它比先做 preset/recent 更容易验证真实写入链是否成立

## 风险

- 当前只做最小字符串校验，尚未引入安全边界
- 真实 task 执行链路仍未消费新的 `active_workdir`
