# Plan

1. 引入 `Session` 模型和 store
2. 让 task 保存 `session_id`
3. 在文本和 card 两条 task 创建路径上自动解析 active session
4. 在 task 生命周期中回写 session summary
5. 在 workspace card 上展示真实 active session
6. 增加 sqlite 持久化与跨重启验证
