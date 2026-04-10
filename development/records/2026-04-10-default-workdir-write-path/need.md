# Need

## 背景

DM 配置卡和群目录切换卡都已经落地，但群侧所有 workdir 动作都还是只读占位。

## 需求信号

- 用户已经明确要求“按照建议继续”
- 当前最稳妥的下一步，是先把 `Use Default` 变成第一条真实写路径，而不是先碰高成本的 agent migration

## 场景

- 用户在群里打开 `Workdir Switcher Card`
- 点击 `Use Default`
- 当前群工作面的 workdir 状态被真正更新

## 影响

这一步决定群工作面是否开始从“可导航”走向“可配置”。
