# Decision

## 待选问题/方案

方案 A：完整拆分 —— 每个 backend 一个模块 + 一个 `common`（通用 helper / 基础接口）+ 一个 `stub`（fallback runner）+ 一个 `factory`。`runner.py` 降级为纯 re-export facade。

方案 B：最小拆分 —— 只把 codex_app_server 摘出来，其他继续留在 `runner.py`。

方案 C：按类型横切 —— `transports.py`、`sessions.py`、`helpers.py`、`runners.py`。

方案 D：保持单文件，通过折叠 / region 注释改善可读性。

## 当前决策

采纳 **方案 A**：完整拆分。

目标结构：

```
poco/agent/
  __init__.py
  completion_gate.py  (已存在)
  runner.py           (降级为 re-export facade)
  common.py           (AgentRunUpdate / AgentRunner / UpdateKind / 通用 helper)
  stub.py             (StubAgentRunner / UnavailableAgentRunner / MultiAgentRunner)
  codex_app_server.py (CodexAppServerRunner + transport + session + codex-only helper)
  codex_cli.py        (CodexCliRunner)
  claude_code.py      (ClaudeCodeRunner + session/control dataclass + claude helper)
  cursor_agent.py     (CursorAgentRunner + cursor helper)
  coco.py             (CocoRunner + Trae ACP client/stream/transport/helper)
  factory.py          (create_agent_runner)
```

`poco.agent.runner` 仅保留 `from .common import *` / `from .codex_app_server import CodexAppServerRunner` 等形式的 re-export，所有外部导入面零破坏。

## 为什么这样选

- **Feature 1 的直接前置**：接下来三个 backend 各自做 completion 审计，拆后每次只动一个文件
- **方案 B 只拖延问题**：留着 claude / cursor / coco 混在一起，下一轮还要再拆一次
- **方案 C 破坏语义相关性**：把 codex 的 session 和 claude 的 session 放一起不帮助阅读
- **方案 D 无实质帮助**：折叠是编辑器特性，不改善 grep / diff / 模块边界
- **re-export facade 的代价最小**：所有 `from poco.agent.runner import ...` 继续工作，不用改 6 个以上的 import 站点

## 为什么不选其他方案

- 方案 B：stop-gap，下轮还要再开一次 record
- 方案 C：跨 backend 横切会鼓励后续"把 cursor session 挪到 sessions.py"这种错误重构
- 方案 D：不解决问题

## 风险

- **循环导入**：`common.py` 只能向外依赖标准库，不能依赖任何 backend 模块。各 backend 模块只依赖 `common` / `completion_gate`。`factory` 依赖所有 backend。`runner.py` re-export 所有。拓扑是无环的 DAG。
- **意外修改逻辑**：纯文件移动过程中容易顺手改小东西。硬规矩：本轮不改任何 runner 的执行逻辑，不加 helper、不改 helper 签名
- **内部符号 re-export 遗漏**：`catalog.py` 懒加载依赖 `_CodexAppServerSession`、`_TraeAcpClient`、`_cleanup_subprocess`。facade 必须确保这些仍可通过 `poco.agent.runner` 访问
- **测试信号**：既有 83 条核心测试 + 11 条 CompletionGate 测试必须全部继续绿

## 后续影响

- 接下来 Feature 1 的三轮 backend 完成语义审计每轮只动一个文件 + 一份单测
- 未来新 backend 直接加 `poco/agent/<name>.py`，不再动 runner.py
- 若后续要抽"SubprocessAgentBase" 骨架，各 backend 文件自带边界，便于一次处理一个
