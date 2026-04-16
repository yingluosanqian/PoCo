# Need

## 背景

`poco/agent/runner.py` 当前 2933 行，容纳了四个 backend（codex_app_server / claude_code / cursor_agent / coco）加 codex_cli 共五个 runner 实现、它们各自的 transport / session / state dataclass、以及二十多个 helper 函数。

## 需求信号

- 2026-04-16-completion-gate-abstraction decision 明确指出下一步要把 completion 语义审计扩展到 claude_code / cursor_agent / coco，本身每个 backend 会新增状态管理、日志点和测试
- 在单文件里继续叠三轮 backend 改动会让 runner.py 逼近 4000 行，review / 导航 / 冲突解决都会付出不成比例的成本
- 今天用户两次排障（claude 慢 / codex MCP 失败）都需要定位到某个 backend 的特定区段，单文件让"跳到相关代码"这一步成本高

## 来源

- 和用户确认过的先后顺序：Refactor 3 (CompletionGate) → **Refactor 1 (拆 runner.py)** → Feature 1 (其他 backend 完成语义审计)

## 场景

纯内部重构。不改对外接口、不改 backend 行为、不改 `poco.agent.runner` 对外的导入面。

## 频率/影响

影响每一轮后续 agent 相关改动的心智成本和修改半径。是 Feature 1 的直接前置。

## 备注

本轮只做文件拆分 + 导入修正，不改任何逻辑、不抽新抽象、不改测试。
