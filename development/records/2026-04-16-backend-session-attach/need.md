# Need

## 背景

PoCo 的 session resume 逻辑是自动的：每个 project 的 active session 的 `backend_session_id` 会在首次任务时被 backend 写入，之后的任务自动 `thread/resume` 那个 id。用户不直接管理 session。

## 需求信号

用户明确反馈希望能"手动 attach 到一个外部已有的 backend session"。即：

- 他在别处（本地跑 codex CLI、历史终端记录、其他 PoCo 实例）已经有了一根有用的 backend thread
- 想从飞书卡片里把它"接管过来"作为当前 project 的 active session

## 来源

2026-04-16 对话里用户直接提出。

## 场景

- 本地终端跑过一段 codex 对话，想转到手机继续
- 多 PoCo 实例之间迁移 session
- project 原来的 active session 误操作丢失，想回去接某个历史 id

## 频率/影响

- 不会每天用，但没有这条路就完全无法从已有 thread 接入
- 和 PoCo purpose "在移动端接管远端 agent 工作" 直接相关

## 备注

- 只做 codex 和 claude_code 都能复用的 UX。每个 backend 的 "session id" 概念不同，但 `backend_session_id` 字段是统一的
- 不引入 per-task session override（每条任务指定不同 session）
- 不引入 session fork / 复制
