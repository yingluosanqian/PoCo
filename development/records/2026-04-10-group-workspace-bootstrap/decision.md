# Decision

## 当前决策

在 `project.create` 的群 bootstrap 成功后，best-effort 向新群发送第一张 `workspace_overview` 卡片。

## 为什么这样选

- 这条链最符合“单聊管理，群聊执行”的正式交互模型
- 首卡发送失败不应回滚已成功创建的 project 和群
- 可以先复用现有 `workspace_overview` 模板和 renderer，避免额外发明新协议

## 风险

- 当前群首卡仍然只是 overview，不包含完整执行动作
- 首卡投递失败时，只能先靠 debug 和后续补发定位问题
