# Plan

## 范围

- 复用现有 `workspace_overview` 结果和 Feishu renderer
- 在 project bootstrap 成功并绑定群后投递首卡
- 修正 workspace 卡片按钮的 `surface`
- 补测试和最小文档

## 验收标准

- 新建群后会收到第一张 workspace overview card
- 群内 workspace 卡片上的按钮会以 `group` surface 回调
- 首卡发送失败不会回滚已成功创建的 project
