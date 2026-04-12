# Backends

## 1. 总则

- backend 只允许在创建 project 时选择
- 之后群里的 `Agent` 卡只修改当前 backend 的配置
- 不允许在已有 project 上切 backend，因为上下文不互通

## 2. Codex

实现：

- runner: [`CodexAppServerRunner`](/Users/yihanc/project/PoCo/poco/agent/runner.py)
- 配置目录: [`poco/agent/catalog.py`](/Users/yihanc/project/PoCo/poco/agent/catalog.py)

当前能力：

- 真流式输出
- resume 上下文
- stop
- 运行时动态发现 model

配置项：

- `model`
- `sandbox`
  - `read-only`
  - `workspace-write`
  - `danger-full-access`

说明：

- model 通过 `codex app-server` 的 `model/list` 动态获取
- 这是当前三者里最成熟的一条执行链

## 3. Claude Code

实现：

- runner: [`ClaudeCodeRunner`](/Users/yihanc/project/PoCo/poco/agent/runner.py)

当前能力：

- 流式输出
- resume 上下文
- stop

配置项：

- `model`
  - 当前只保留 `sonnet` / `opus` alias
- `permission_mode`
  - `default`
  - `acceptEdits`
  - `plan`
  - `bypassPermissions`

特殊处理：

- 当 `permission_mode=bypassPermissions` 时，会注入 `IS_SANDBOX=1`

说明：

- Claude CLI 当前没有像 Cursor / Codex 那样稳定的模型枚举接口
- 因此这里故意保持 alias 方案，不做“伪动态发现”

## 4. Cursor Agent

实现：

- runner: [`CursorAgentRunner`](/Users/yihanc/project/PoCo/poco/agent/runner.py)

当前能力：

- 流式输出
- resume 上下文
- stop
- 运行时动态发现 model

配置项：

- `model`
- `mode`
  - `default`
  - `plan`
  - `ask`
- `sandbox`
  - `default`
  - `enabled`
  - `disabled`

说明：

- model 通过 `cursor-agent --list-models` 动态获取
- 当前还没有把 `--force / --yolo` 暴露到 UI

## 5. Trae CLI / CoCo

实现：

- runner: [`CocoRunner`](/Users/yihanc/project/PoCo/poco/agent/runner.py)

当前能力：

- ACP 协议输出
- resume 上下文
- stop
- 从本地 `~/.trae/traecli.yaml` 读取当前 model 作为卡片候选

配置项：

- `model`
- `approval_mode`
  - `default`
  - `yolo`

说明：

- 当前通过 `traecli acp serve` 执行，不再走 `-p --json`
- `approval_mode=yolo` 当前映射到 ACP mode `bypass_permissions`
- backend key 仍保持 `coco`，UI label 展示为 `Trae CLI`
- 当前执行链仍在重设计中，已暴露：
  - task 完成语义不够稳定
  - `session/load` 后 update 归属边界不够清晰
  - 需要严格收紧子进程生命周期管理

## 6. 当前能力矩阵

| Backend | Streaming | Resume | Stop | Dynamic model discovery |
| --- | --- | --- | --- | --- |
| `codex` | yes | yes | yes | yes |
| `claude_code` | yes | yes | yes | no |
| `cursor_agent` | yes | yes | yes | yes |
| `coco` | partial | yes | yes | limited |
