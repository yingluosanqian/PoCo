# Problem

## 背景

见 `need.md`。

## 相关需求

- 允许后续 backend 改动的影响半径收敛到单个文件
- 保持 `from poco.agent.runner import ...` 这个既有导入面不破

## 当前状态

`poco/agent/runner.py` 内容层次：

- 基础接口：`AgentRunUpdate`、`UpdateKind`、`AgentRunner` Protocol
- 通用 helper：`_cleanup_subprocess`、`_parse_json_event`、`_optional_string` 等 10+ 函数
- 通用 stub：`StubAgentRunner`、`UnavailableAgentRunner`、`MultiAgentRunner`
- Codex app-server：runner + `_CodexAppServerTransport` + `_CodexActiveTurn` + `_CodexAppServerSession` + codex-only helpers
- Codex CLI（legacy）：`CodexCliRunner`
- Claude Code：runner + `_ClaudePendingControl` + `_ClaudeActiveSession` + claude helpers
- Cursor Agent：runner + cursor helpers
- Coco（Trae CLI）：runner + `_TraePromptEvent` + `_TraePromptTurnState` + `_TraeAcpTransport` + `_TraeAcpClient` + `_TraeAcpPromptStream` + coco helpers
- 工厂：`create_agent_runner`

外部导入情况：

- `poco/main.py`: `create_agent_runner`
- `poco/task/controller.py`: `AgentRunner`
- `poco/agent/catalog.py`: `_CodexAppServerSession`、`_TraeAcpClient`、`_cleanup_subprocess`（懒加载）
- `tests/test_agent_runner.py`: 所有 Runner 类 + `_cleanup_subprocess`
- `tests/test_task_*`: `StubAgentRunner`、`AgentRunUpdate`、`CodexCliRunner`

## 问题定义

**单文件承载 5 个 backend + 它们各自的 transport / session / helper，使得任何一个 backend 级别的改动都要面对全文件的上下文。** 无法通过目录结构表达 "这片代码只和 X backend 有关"。

## 为什么这是个真实问题

- 下一步 Feature 1 会连续在 3 个 backend 上加 completion 审计，每次都得在同文件重新定位
- 未来新增 backend 会继续膨胀单文件
- 阅读 / 编辑 / diff / 冲突解决成本随文件长度非线性增长
- 2026-04-16 completion-gate-abstraction record 的 decision 已经预告"更大抽象需另立 record 重审"—— 本轮就是那个重审

## 不是什么问题

- 不是"现有逻辑有 bug"。本轮禁止修改任何 runner 的行为逻辑
- 不是"要抽跨 backend 状态机"。本轮禁止引入新抽象
- 不是"要改对外接口"。`poco.agent.runner` 继续是所有外部导入的入口

## 证据

- `wc -l poco/agent/runner.py` = 2933
- 文件内 `grep ^class` 找到 13 个类；`grep ^def` 找到 30+ 个顶层函数
- 外部 import 通过 `poco.agent.runner` 命名空间引用 6 种以上符号
