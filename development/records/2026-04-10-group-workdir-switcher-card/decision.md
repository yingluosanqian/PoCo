# Decision

## 当前决策

先在群工作面落地 `Workdir Switcher Card` 的最小只读版本，并补四个只读入口：

- `workspace.use_default_dir`
- `workspace.choose_preset`
- `workspace.use_recent_dir`
- `workspace.enter_path`

## 为什么这样选

- 这符合已批准的快变量卡片 IA
- 这让群里的 `Change Workdir` 不会变成空按钮
- 这轮仍可保持范围受控，不抢跑真实 session 写入

## 风险

- 入口已经存在，但仍是 read-only placeholder
- 如果后续不继续接真实切换，用户会感到“可看不可用”
