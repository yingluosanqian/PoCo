# Decision

## 当前决策

先把 `project.open` 升级成真正的 `DM Project Config Card`，并补最小只读子卡：

- `project.configure_agent`
- `project.configure_repo`
- `project.configure_default_dir`
- `project.manage_dir_presets`

## 为什么这样选

- 这符合已批准的卡片 IA
- 这能让入口按钮不是死按钮
- 这轮仍可保持“只读入口优先”，避免过早进入复杂写操作

## 风险

- 子卡目前还只是 read-only placeholder
- 如果后续不继续接真实写入，用户可能会感到“可见但不可改”
