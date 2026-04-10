# Need

在最小运行态持久化已经落地后，PoCo 仍缺少真正的 `session` 对象。

这会导致：

- task 之间仍然只是松散堆叠
- workspace 卡只能展示占位文案
- 产品无法明确回答“当前正在延续哪一条工作流”

本轮需要引入最小 `session/handoff`，但不进入完整多分支 session 或 backend resume handle。
