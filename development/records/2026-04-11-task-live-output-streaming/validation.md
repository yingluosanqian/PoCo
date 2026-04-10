# Validation

## 已验证

- `CodexCliRunner` 现在会流式 yield progress updates，并带上 `output_chunk`
- `Task` 现在保存 `live_output`
- `TaskController` 现在支持带 callback 的执行路径，并在 progress 时追加 live output
- `AsyncTaskDispatcher` 现在会在 running + live output 时触发 notifier
- `FeishuTaskNotifier` 对 running 更新做最小节流
- `task_status` card 在 running 时会显示 `Live Output`
- 单测已覆盖：
  - codex runner 流式 progress update
  - dispatcher 运行中通知
  - notifier 发送 running card
  - renderer 显示 live output
