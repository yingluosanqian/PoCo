# Plan

## 本轮计划

- 给 `Project` 增加 `workspace_message_id`
- 在 bootstrap / workspace.open / workspace.refresh 时绑定 workspace message
- 在 task notifier 中增加 workspace card update
- 补足 gateway / bootstrap / notifier 自动化测试

## 完成标准

- workspace card 有稳定 message 绑定
- task 状态变化时，workspace latest task 区块会被顺手更新
- 同一消息既是 task card 又是 workspace card 时，不重复更新
