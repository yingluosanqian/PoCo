# Need

## 背景

claude_code backend 当前允许用户在 Feishu 的 `workspace.choose_agent` 卡片里填两个字段：

- `anthropic_base_url` → 运行时注入 `ANTHROPIC_BASE_URL`
- `anthropic_api_key` → 运行时注入 `ANTHROPIC_API_KEY`

注入路径在 `poco/agent/claude_code.py::_execute_prompt`，卡片表单定义在 `poco/agent/catalog.py::_BACKEND_DESCRIPTORS["claude_code"].config_fields`。

## 需求信号

用户明确表达不再需要这两个字段由 PoCo 的卡片表单采集 / 由 backend config 携带，希望清理相关代码。

## 来源

2026-04-16 用户直接反馈。

## 场景

运维收敛：把这类敏感连接信息移出 per-task backend config 的采集面。claude CLI 本身仍然会读 `ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY` 环境变量；PoCo 不再主动注入，改由运维在 PoCo 进程启动的环境里自己管理。

## 频率/影响

一次性清理。

## 备注

- 不删除 env 变量本身的作用（claude CLI 仍然会读）
- 不删 `/debug/env` 里这两个 key 的 present 检查（用于诊断"PoCo 进程是否继承到这两个 env"依然有用）
- sqlite 里已存的 `backend_config` 残留字段保留不动（inert，不会再被 runner 读）
