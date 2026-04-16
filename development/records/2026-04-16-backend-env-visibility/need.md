# Need

## 背景

PoCo 的所有 agent backend（codex / claude_code / cursor_agent / coco）都通过 `subprocess.Popen` 直接 exec CLI 二进制，没有走 shell，因此不会读 `.bashrc` / `.zshrc` / `.profile`。子进程拿到的环境只来自 PoCo 自身进程的 `os.environ`。

## 需求信号

最近多次出现同一类运维问题：

- claude CLI 起来后长时间没有回应，实际是 `ANTHROPIC_BASE_URL` 没传进去，默认走 api.anthropic.com，境内机器基本不通
- codex app-server 报 `codex_apps status: failed`，是 MCP server 启动失败，但 PoCo 这边不知道是不是因为某个环境变量没继承到
- 用户习惯在 `.bashrc` 写导出语句，启动 PoCo 时 shell 已经读过，但 daemon 方式启动 PoCo 并不会读

## 来源

- 2026-04-16 用户使用 claude backend 卡住的诊断对话
- 2026-04-16 用户遇到 codex MCP 启动失败的诊断对话

## 场景

排障场景。用户在飞书里看到 task 卡 Running 或 progress 停在某一步时，没有快捷方式判断是不是 PoCo 这边环境继承的问题。只能：

- 手动跑一遍 CLI 比对
- 或者进服务器查 PoCo 进程的 `/proc/<pid>/environ`

## 频率/影响

每次首次把 PoCo 部署到新机器、或者运维环境变动（新增代理、更换网关、迁移账号）时都会遇到。诊断成本高到每个新用户都要重新踩一次。

## 备注

本轮只处理"能不能看到 PoCo 进程的关键环境变量"，不处理"怎么把 shell rc 变量持久化进来"。后者是更大的配置路径问题，需要另立 record。
