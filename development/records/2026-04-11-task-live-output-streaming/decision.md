# Decision

采纳“最小流式输出”方案。

具体为：

- `CodexCliRunner` 以流式方式读取进程输出
- `Task` 新增 `live_output` tail
- `TaskController` 在运行期间按增量更新 task
- `AsyncTaskDispatcher` 对 running + live output 也触发 notifier
- `FeishuTaskNotifier` 对 running 更新做节流
- `task_status` 在 running 时展示 `Live Output`

## 为什么这样选

- 用户能及时看到 task 正在发生什么
- 不需要把飞书卡片做成逐 token 刷新终端
- 能复用现有 task card、message binding、in-place update 主链

## 当前明确不做

- 不做逐 token 级别刷新
- 不做完整 timeline / terminal replay
- 不做真正的 streaming result finalization 协议
