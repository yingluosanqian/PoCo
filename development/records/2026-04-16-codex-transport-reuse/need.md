# Need

## 背景

codex app-server 的冷启动成本明显（`subprocess.Popen codex` + `initialize` + MCP 冷启动），经验上 2-5 秒。PoCo 已有 transport 复用缓存，但两条路径下用户仍然会看到冷启动：

1. **idle 超时回收**：`transport_idle_seconds=300`（5 分钟）偏短，用户隔几分钟再发任务就要等冷起
2. **首次任务**：用户发第一条消息时 transport 还没建起来，必须等 task 启动阶段完整走一遍冷路径

## 需求信号

- 用户直接反馈："希望尽可能复用 codex app server，不需要反复起"
- 冷启动时间用户可感知（task card 长时间停在 `Codex tools are starting`）

## 来源

2026-04-16 用户直接反馈。

## 场景

日常使用 PoCo 的典型路径：打开飞书 → 找到项目群 → 输入任务。两次任务之间可能相隔 5 min ~ 1 hr。

## 频率/影响

- 频率：高频，典型使用都会触发
- 影响：每次 2-5s 用户可感知延迟

## 备注

本轮只针对 codex（用户明确点名的 backend）。claude / cursor / coco 的 transport 复用模型不同，单独考虑。
