# Decision

## 当前决策

先把 DM 首页卡片上的最小真实动作接起来：

- `project.create`
- `project.open`
- `workspace.open`
- `workspace.refresh`

## 为什么这样选

- 这几项已经有现成 handler 和 renderer 边界
- 能最快验证真实卡片点击是否已进入业务层

## 风险

- `project.create` 当前仍是默认命名，不是完整 project composer
