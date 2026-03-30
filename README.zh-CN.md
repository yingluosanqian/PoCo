# PoCo

[English](README.md)

**PoCo** (Pocket-Coding) 是一个把不同 Coding-Agent 接入办公软件机器人程序。

当前已经支持了 Codex, Claude Code 等 Coding-Agent；已经支持了飞书机器人。

## 快速开始

点击这里[快速开始](docs/quickstart.zh-CN.md)。

## 工作方式

- 单聊机器人：管理控制台
- 群聊机器人：项目工作区
- 每个项目群会启动一个独立的 worker 进程
- 每个项目都通过 DM 控制台卡片配置
- PoCo 使用飞书长连接模式，不需要公网回调地址

## 使用方式

单聊控制台：

- 发 `poco`
- 用卡片完成新建项目和管理项目

项目群：

- 直接聊天即可
- 如果要发图片，请发送一条同时包含图片和文字说明的飞书图文消息

## Provider

- `codex`：已通过 `codex app-server` 完整接通
- `claude`：已通过 Claude Code CLI 接通，支持流式 JSON 输出

当前 provider 能力说明：

- Codex 是默认运行路径
- Claude 当前支持 session attach、图片输入和流式回复

## TUI

页面：

当前 TUI 是一个双栏终端界面：

- 左侧：logo 和运行状态摘要
- 右侧：当前交互面板
- 底部：一个输入栏，但只有在需要输入配置值时才会启用

快捷键：

- `Ctrl+R`：保存并重启
- `q`：返回上一级
- `↑ / ↓`：在主菜单或 config 菜单中移动
- `Enter`：进入当前选项
- `Esc`：返回上一级

默认首页是菜单驱动的：

- 右侧会显示：
  - `Agent & Model`
  - `Bot (feishu)`
  - `PoCo`
  - `Language`
  - `Quit`
- 用 `↑ / ↓` 选择项目
- 按 `Enter` 进入

顶层菜单会直接进入对应配置分类：

- 右侧面板会变成选择菜单
- `↑ / ↓` 可以切换 section 或字段
- `Enter` 进入当前项
- `Esc` 返回上一级
- `Language` 可以切换英文和中文
- `Bot (feishu)` 里包含 `feishu` 相关设置，比如 `App ID`、`App Secret`
- `Agent & Model` 里包含 `codex` 和 `claude`
- `claude` 会先进入 provider 菜单
- 先选一个 provider，例如 `anthropic`、`minimax`、`deepseek`、`kimi`
- 再编辑这个 provider 的 `base_url`、`auth_token`、`model`、`extra_env`
- `model` 会再进入一个模型菜单；先选模型，再执行 `set_as_default`
- `extra_env` 也会进入子菜单；按项管理环境变量，不再直接编辑原始 JSON
- `show` 会打开当前配置文件的滚动视图
- 只有在编辑文本字段时，底部输入栏才会启用

## 文件位置

- 工作区绑定：`~/.config/poco/workspaces.json`
- 每个 bot 的配置文件：`~/.config/poco/bindings/<app_id>/config.json`
- 每个 bot 的状态目录：`~/.local/state/poco/<app_id>/`
- 兼容旧版时，默认配置 / 状态仍在：
  - `~/.config/poco/config.json`
  - `~/.local/state/poco/`

## 开发

构建安装包：

```bash
uv build
```

快速语法检查：

```bash
uv run python -m py_compile poco/__init__.py poco/app.py poco/runtime.py poco/relay/app.py poco/config/store.py poco/tui/app.py
```
