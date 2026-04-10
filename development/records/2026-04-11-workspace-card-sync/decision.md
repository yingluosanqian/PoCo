# Decision

## 当前决策

先落地最小 workspace 同步链：

- `Project` 保存 `workspace_message_id`
- workspace 打开/刷新时更新这份绑定
- bootstrap 首卡发送后也保存 message id
- task notifier 在更新 task card 后，若存在独立 workspace card，则顺手更新它的 latest task 区块

## 为什么这样选

- 这能让 workspace card 开始承担项目面板职责
- 不需要先引入更重的 card subscription 体系
- 如果 workspace card 与当前 task card 是同一张消息，会自动跳过重复更新

## 风险

- `workspace_message_id` 目前仍是内存态
- 当前只同步 latest task 相关摘要，不是整张 workspace 的 richer live model
