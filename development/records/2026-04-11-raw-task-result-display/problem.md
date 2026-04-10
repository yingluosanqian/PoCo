# Problem

PoCo 当前 task 结果链仍主要围绕 `result_summary` 组织。

这会导致：

- task card 展示的是压缩后的结果，而不是原始结果
- workspace 首卡也试图携带 latest result preview
- 用户看到的是“被转述后的结果”，而不是 agent 的真实返回

对 agent 产品来说，这会损伤最核心的可信度。

真正的问题不是“卡片能不能显示很多字”，而是：

当前产品把摘要放在了 task 结果的主视图位置上。

这与用户对 agent 工作台的预期不一致。
