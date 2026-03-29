# PoCo

[English](README.md)

`PoCo` 是产品名，Python 包名是 `pocket-coding`。

PoCo 是一个本地 TUI，用来把 `Codex app-server` 接到飞书机器人后面。

- 和机器人单聊时，把它当作管理控制台
- 把飞书群当作项目工作区
- 每个项目群对应一个独立的 Codex worker
- 通过飞书消息创建和编辑，把进度持续回推到群里

## 快速开始

安装：

```bash
pip install pocket-coding
```

如果你是从源码运行：

```bash
pip install .
```

启动：

```bash
poco
```

也支持非交互配置：

```bash
poco config app_id "cli_xxx"
poco config app_secret "your-secret"
poco config --show
```

进入 TUI 后：

1. 填写 `Feishu App ID` 和 `App Secret`
2. 点击 `Save & Restart`
3. 把 bot 拉进项目群
4. 在项目群里执行：

```text
/poco name my-project
/poco cwd /path/to/project
/poco mode mention
/poco enable
```

之后：

- 在单聊里用 `/poco workers` 或 `/poco status my-project`
- 在群里，`/poco ...` 是 PoCo 自己的命令
- 在群里，其他非 `/poco` 文本会直接转发给 Codex

如果你想把当前项目群的 worker 绑定到一个已有的 Codex CLI session：

```text
/poco attach <session_id>
```

PoCo 会尝试从本地 Codex 状态里导入这个 session 的工作目录，并把当前 worker 绑定到这个 session。

## 工作方式

- 单聊机器人：管理控制台
- 群聊机器人：项目工作区
- 每个项目群会启动一个独立的 Codex worker 进程
- 每个群都必须先配置自己的工作目录，才能启用
- PoCo 使用飞书长连接模式，不需要公网回调地址

## 命令

单聊命令：

- `/poco help`
- `/poco workers`
- `/poco list`
- `/poco sessions [limit]`
- `/poco status <worker_alias|group_chat_id>`
- `/poco stop <worker_alias|group_chat_id>`
- `/poco reset <worker_alias|group_chat_id>`
- `/poco remove <worker_alias|group_chat_id>`

项目群命令：

- `/poco help`
- `/poco mode <mention|auto>`
- `/poco attach <session_id>`
- `/poco cwd <path>`
- `/poco enable`
- `/poco disable`
- `/poco reset`
- `/poco new`
- `/poco name <alias>`
- `/poco unname`
- `/poco status`
- `/poco stop`
- `/poco steer <message>`
- `/poco queue <message>`
- `/poco remove`

如果当前 worker 正在运行：

- 普通文本会被拒绝，不会直接发给 Codex
- 用 `/poco steer <message>` 给当前这一轮补充引导
- 用 `/poco queue <message>` 把一条后续消息排到下一轮
- 用 `/poco stop` 中断当前这一轮

## 飞书要求

请使用“企业自建应用”，不要使用自定义群机器人。

至少需要：

- 开启机器人能力
- 事件订阅：`im.message.receive_v1`
- 发送消息权限
- 更新消息权限

推荐：

- 使用长连接模式

## TUI

页面：

当前 TUI 是一个双栏终端界面：

- 左侧：logo 和运行状态摘要
- 右侧：当前交互面板
- 底部：一条 slash 命令输入行

快捷键：

- `Ctrl+R`：保存并重启
- `q`：退出
- `↑ / ↓`：在命令下拉框或 config 菜单中移动
- `Tab`：补全当前选中的 slash 命令

TUI 内可直接输入：

```text
/help
/config
/log
/restart
/quit
```

在输入框里键入 `/` 会显示可用命令；例如输入 `/co` 时，会提示 `/config`。

输入 `/config` 后会进入 config mode：

- 右侧面板会变成选择菜单
- `↑ / ↓` 可以切换 section
- `language` 可以切换英文和中文
- `feishu` 会引导输入 `App ID` 和 `App Secret`
- 命令行里只接受 `/quit` 用来退出 config mode

输入 `/config` 后，slash 提示里会出现 `/config show`。

输入 `/config show` 会在右侧面板显示当前配置；如果内容过长，可以用 `↑ / ↓` 滚动。

`/quit` 在 log、help 这类子视图中会先回到 dashboard；如果当前已经在 dashboard，再次 `/quit` 才会退出 TUI。

## 文件位置

- 配置文件：`~/.config/poco/config.json`
- 状态目录：`~/.local/state/poco/`

## 开发

构建安装包：

```bash
uv build
```

快速语法检查：

```bash
uv run python -m py_compile poco/__init__.py poco/app.py poco/runtime.py poco/bridge.py poco/config/store.py poco/tui/app.py
```
