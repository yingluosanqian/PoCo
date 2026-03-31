# Cursor Provider Plan

这份文档描述 PoCo 如何接入 `Cursor Agent`，目标是先做一个**最小可用版**，不一次做太重。

这不是最终实现文档，而是基于当前官方资料整理出来的一版接入设计。凡是 Cursor 官方文档没有明确保证的地方，本文都会标成“待确认”。

## 1. 为什么现在做

相较于继续深挖 Claude session 可见化，`Cursor Agent` 更适合先接入：

- 已经有官方 CLI
- 支持非交互模式
- 支持 `stream-json`
- 支持 `--resume`
- 支持列出历史会话

这意味着它和 PoCo 现有的 provider 抽象比较契合。

## 2. 官方能力确认

根据 Cursor 官方 CLI 文档，目前可以确认：

- `cursor-agent -p --print`
  - 可用于非交互脚本模式
- `--output-format`
  - 支持 `text` / `json` / `stream-json`
  - 默认是 `stream-json`
- `--resume [chatId]`
  - 支持恢复历史会话
- `cursor-agent resume`
  - 支持恢复最近一次会话
- `cursor-agent ls`
  - 支持列出历史会话
- 认证支持：
  - `cursor-agent login`
  - `CURSOR_API_KEY`
  - `--api-key`
- 非交互模式下有完整工具权限
  - 官方文档明确写了 write / bash 都可用

当前还**不能从官方文档完全确认**的点：

- `cursor-agent ls` 的输出字段是否稳定包含：
  - `cwd`
  - `title`
  - `updated_at`
- `--resume <chatId>` 在 `stream-json` 模式下的完整事件行为
- Cursor 本地历史文件是否有稳定、可依赖的磁盘格式

参考：

- CLI 参数：
  - https://docs.cursor.com/en/cli/reference/parameters
- 输出格式：
  - https://docs.cursor.com/en/cli/reference/output-format
- CLI 使用：
  - https://docs.cursor.com/en/cli/using
- 认证：
  - https://docs.cursor.com/en/cli/reference/authentication

## 3. 当前 PoCo 的接入约束

PoCo 当前 provider 抽象在：

- [base.py](/root/project/poco/dev/poco/providers/base.py)

核心接口是：

- `ProviderClient`
  - `start()`
  - `notifications()`
  - `close()`
  - `ensure_thread()`
  - `start_turn()`
  - `interrupt_turn()`
  - `steer_turn()`
- `SessionLocator`
  - `get()`
  - `list_recent()`
  - `delete()`

因此 Cursor 接入不需要先改大架构，优先做一个新的 provider 文件即可。

当前 PoCo provider 抽象还有一个现实约束：

- `ProviderConfig` 目前固定是：
  - `bin`
  - `app_server_args`
  - `model`
  - `approval_policy`
  - `sandbox`
  - `reasoning_effort`

这组字段更贴近 Codex，而不是 Cursor。第一版接入时会尽量复用，后面再视情况 clean。

## 4. 建议的最小实现

### 4.1 新增 `CursorSessionLocator`

路径建议：

- `poco/providers/cursor.py`

职责：

- 列出最近 session
- 按 `session_id` 查询 session
- 第一版**不负责删除 session**

优先策略：

1. 先优先使用官方 CLI：
   - `cursor-agent ls`
2. 如果 CLI 无法提供足够细节：
   - 第一版允许只返回 `session_id`
   - 不强求马上补本地文件解析
3. 只有在官方 CLI 明显不够用时，才再研究本地文件结构

第一版理想上希望拿到：

- `session_id`
- `cwd`
- `thread_name`
- `updated_at`

但实际优先级是：

1. `session_id`
2. `thread_name`
3. `updated_at`
4. `cwd`

也就是说，哪怕第一版只能稳定拿到 `session_id`，也允许先接入。

### 4.2 新增 `CursorProviderClient`

仍放在：

- `poco/providers/cursor.py`

目标行为：

- `start()`
  - 第一版做空实现
  - 不假设 Cursor 存在像 Codex 一样的常驻 app-server
- `ensure_thread(thread_id)`
  - 有 thread_id 就直接返回
  - 没有就生成一个新的 UUID
- `start_turn(thread_id, text, local_image_paths)`
  - 启动：
    - `cursor-agent -p --print --output-format stream-json`
  - 如果已有 thread：
    - `--resume <thread_id>`
  - 否则：
    - 不主动传 session id
    - 让 Cursor 自己生成新的 `session_id`
- `interrupt_turn(...)`
  - 第一版先做最小版：
    - 直接 terminate 本地 `cursor-agent` 子进程
- `steer_turn(...)`
  - 第一版先不实现
  - 直接抛 `ProviderNotImplementedError`

### 4.3 流式事件映射

PoCo 现在的 relay/runtime 依赖的是类似下面这些内部通知：

- `item/agentMessage/delta`
- `item/completed`
- `turn/completed`

Cursor `stream-json` 的官方文档已确认有：

- `system init`
- `user`
- `tool_call`
- `assistant`
- 最终 `result`

第一版建议映射成：

- 收到 `assistant` 事件里的文本内容
  - 映射为 `item/agentMessage/delta`
- 收到最终 `result`
  - 映射为：
    - `item/completed`
    - `turn/completed`

也就是说：
- 先适配 PoCo 现有 runtime
- 不急着为 Cursor 单独改一套 turn 协议

待确认：

- `assistant` 事件是否天然就是“增量”
- 还是需要从多个事件中拼接文本

在真正开始实现前，需要先手动跑一遍：

```bash
cursor-agent -p --print --output-format stream-json "hello"
```

观察真实 NDJSON 事件序列，再决定增量拼接逻辑。

## 5. 配置设计

第一版保持与现有 provider 一致，不引入 profile。

建议新增：

- `cursor.bin`
  - 默认：`cursor-agent`
- `cursor.app_server_args`
  - 虽然名字不准，但第一版为了复用现有配置结构，先沿用
  - 语义上把它当作：
    - `cursor extra cli args`
- `cursor.model`
- `cursor.approval_policy`
- `cursor.sandbox`

如果后面发现 Cursor 的实际 CLI 参数和 `approval_policy / sandbox` 不完全匹配，再做第二轮产品化。

第一版还要接受一个现实：

- Cursor CLI 当前明确可确认的权限相关参数，最明显的是：
  - `-f / --force`
- 它和 PoCo 现有的 `approval_policy` / `sandbox` 模型并不严格一一对应

因此第一版可以先做：

- `approval_policy == "force"` 时追加 `--force`
- 其它值先忽略或保守透传

不要在第一版里强行假设 Cursor 和 Codex 的权限模型一致。

## 6. 认证策略

Cursor 官方支持：

- `cursor-agent login`
- `CURSOR_API_KEY`
- `--api-key`

PoCo 第一版建议：

1. 优先依赖用户本机已经完成：
   - `cursor-agent login`
   - 或设置好 `CURSOR_API_KEY`
2. 不在 PoCo 里额外做登录 UI
3. 如果命令运行时遇到认证失败：
   - 明确提示用户先登录或设置 API Key

也就是说：
- 先把认证视作环境前置条件
- 不把登录流程塞进 PoCo

## 7. Session 管理策略

第一版先只做到：

- 新建 session
- resume 既有 session
- 在 DM 创建项目时 attach 既有 session

不急着先做：

- session 可见化大改版
- detach / migrate
- 更细的 session 生命周期 UI

## 8. TUI / DM 的最小改动

只做必要接入：

- Agent 选择里新增：
  - `cursor`
- New Project 卡片支持：
  - `cursor`
- `Attach to existing session`
  - 对 `cursor` 也开放

先不做 Cursor 专属高级配置页。

## 9. 第一阶段不做的事

这次明确不做：

- Cursor 专属 runtime profile
- Cursor 专属 TUI 复杂交互
- steer / checkpoint / advanced tooling 的产品化
- 深入研究 Cursor 本地历史文件结构
- 重新设计 provider 抽象层

## 10. 建议的实施顺序

1. 先人工验证 Cursor CLI 真实事件流
   - `stream-json`
   - `--resume`
   - `ls`
2. 新增 `poco/providers/cursor.py`
3. 补 `CursorSessionLocator`
4. 补 `CursorProviderClient`
5. 把 provider 注册进 runtime/config/model choices
6. 让 DM / TUI / New Project 能选 `cursor`
7. 跑通：
   - 新建项目
   - 发一条消息
   - 流式回复
   - resume 既有 session

## 11. 当前判断

`Cursor Agent` 非常适合先按“类似 Claude、但更标准化的 CLI provider”接入。

第一版的目标不是做完所有 Cursor 能力，而是：

- 能跑
- 能流式
- 能 resume
- 能 attach session

把这四件事做稳，就已经足够让它进入 PoCo 的 provider 列表。

## 12. 当前 reviewer 结论

这份方案当前是可以继续往下走的，但要注意三条硬约束：

1. 不要在第一版里假设 Cursor 有 Codex 式 app-server
2. 不要在第一版里假设 `ls` 能稳定给出完整 metadata
3. 在真正实现前，必须先手动验证一次 `stream-json` 的真实事件形状

只要守住这三条，第一版接入的范围就是清晰且可控的。
