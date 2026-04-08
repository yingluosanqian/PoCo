# Decision

## 当前决策

把 `project.create` 升级成带群 bootstrap 的动作：

- 在真实飞书模式下，同步调用飞书建群 API
- 创建成功后，把返回的 `chat_id` 绑定回 project
- 建群失败时，回滚刚创建的 project，而不是留下半成品

## 为什么这样选

- 这条路径最符合“单聊管理 project，群承载工作区”的交互模型
- 回滚比留下未绑定群的 project 更符合当前用户预期
- 可以先落在最小 bootstrap，不必这轮同时做完整群 workspace 初始化

## 风险

- 真实飞书环境下仍依赖 bot 的建群权限
- 当前群命名策略仍然很简单，后续可能还要继续调整
