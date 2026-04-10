# Plan

## 本轮计划

- 在 workspace overview card 增加 `Run Task` 入口
- 新增 `TaskIntentHandler`
- 新增 `task_composer` renderer
- 让 `task.submit` 创建 task、继承当前 workdir，并异步派发
- 补足 card gateway / renderer 自动化测试

## 完成标准

- 群卡能打开 task composer
- task composer 能提交 prompt
- 提交后 task 会继承当前 `active_workdir`
- 提交后会触发异步 dispatch start
