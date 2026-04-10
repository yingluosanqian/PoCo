# Plan

1. 为 `project/task/workspace context` 增加 sqlite store
2. 让 `create_app()` 可根据配置选择 `sqlite` 或 `memory`
3. 默认运行态使用 sqlite
4. 在启动阶段恢复最小持久化状态
5. 对被重启打断的进行中 task 做启动期收敛
6. 增加跨重启回归测试
