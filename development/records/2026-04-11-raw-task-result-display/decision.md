# Decision

采纳“task 结果原文优先”的结果展示决策。

具体为：

- `Task` 新增 `raw_result`
- `task_status` card 默认展示 `raw_result`
- 当原始结果过长时，采用分页展示，而不是摘要替代
- `workspace_overview` 不再显示 latest result preview，只保留 latest task 状态与入口

## 为什么这样选

- 更符合 agent 产品的保真要求
- 降低产品层二次转述带来的信息损失
- 不需要立刻引入新的摘要策略或质量控制逻辑
- 在飞书卡片存在体积限制时，分页比摘要更保真

## 当前明确不做

- 不做模型式自动摘要
- 不把 workspace 首卡重新做成结果展示面
- 不在这轮引入完整 timeline 或流式进度协议
