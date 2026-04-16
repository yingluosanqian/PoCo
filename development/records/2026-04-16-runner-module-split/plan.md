# Plan

## 目标

把 `poco/agent/runner.py` 按方案 A 完整拆分成多个模块，`runner.py` 降级为 re-export facade，保持全部外部导入不破、全部测试继续绿、全部 runner 行为零变化。

## 范围

- 新增文件：`common.py` / `stub.py` / `codex_app_server.py` / `codex_cli.py` / `claude_code.py` / `cursor_agent.py` / `coco.py` / `factory.py`
- `runner.py` 从 2933 行缩成纯 re-export
- 不新增测试
- 不改任何现有测试
- 不改任何对外 import（`poco.main` / `poco.task.controller` / `poco.agent.catalog` / 所有 `tests/*`）

## 不在范围内的内容

- 不抽共用骨架（`SubprocessAgentBase` 等）
- 不合并 / 重命名任何 helper
- 不改任何 logging / error 文本
- 不改 `AgentRunUpdate` / `AgentRunner` 签名
- 不碰 `poco/agent/catalog.py` 以外的其他模块

## 风险点

- 循环依赖（靠 DAG 约定规避：common → completion_gate / std；backend → common + completion_gate；factory → all backends；runner facade → all）
- Helper 归属误判（backend-specific helper 不能掉进 common）
- facade 遗漏 re-export 导致 `catalog.py` 或 test 找不到符号
- 误改逻辑（硬规矩：只做文件搬运 + import 重写）

## 验收标准

- `uv run --extra dev pytest -q tests/test_agent_runner.py`：全部原样 passed
- `uv run --extra dev pytest -q tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_health.py tests/test_debug_api.py`：全部 passed
- `grep -n 'class\|^def' poco/agent/runner.py`：应只剩 re-export 相关，不再出现 Runner 类或 helper 函数的定义
- `grep -rn 'from poco\.agent\.runner'` 覆盖的外部站点全部仍然成功导入

## 实施顺序

1. 建 `common.py`：搬 `AgentRunUpdate`、`UpdateKind`、`AgentRunner` Protocol、所有共享 helper、`_cleanup_subprocess`
2. 建 `stub.py`：搬 `StubAgentRunner` / `UnavailableAgentRunner` / `MultiAgentRunner`
3. 建 `codex_app_server.py`：搬 `CodexAppServerRunner` + transport + session + codex helper
4. 建 `codex_cli.py`：搬 `CodexCliRunner`
5. 建 `claude_code.py`：搬 `ClaudeCodeRunner` + session + control
6. 建 `cursor_agent.py`：搬 `CursorAgentRunner` + cursor helper
7. 建 `coco.py`：搬 `CocoRunner` + Trae ACP 类 + coco helper
8. 建 `factory.py`：搬 `create_agent_runner`
9. 重写 `runner.py`：纯 re-export
10. 跑测试
11. 更新 validation
