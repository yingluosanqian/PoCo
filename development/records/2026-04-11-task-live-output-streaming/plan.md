# Plan

## 范围

- 改造 Codex runner 为最小流式输出
- 增加 task 级 `live_output`
- 让 running task 也能驱动 notifier
- 在 task status card 中渲染 live output

## 不在范围内

- 富文本进度 UI
- 长时间历史输出翻页
- 服务重启后的流式恢复

## 验收标准

- running 中 task 能携带 `live_output`
- notifier 能在 running 期间更新同一张 task card
- card 中能看到最新 live output tail
