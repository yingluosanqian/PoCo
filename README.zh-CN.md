# PoCo

[English](README.md)

`PoCo` 是产品名，Python 包名是 `pocket-coding`。

PoCo 是一个本地 TUI，用来把不同的 coding-agent provider 接到飞书机器人后面。当前 Codex 已通过 `app-server` 完整接通；Claude Code 也已经通过 CLI 适配接入，支持流式输出、session 发现和 attach。

- 和机器人单聊时，把它当作管理控制台
- 把飞书群当作项目工作区
- 每个项目群对应一个独立的 provider worker
- 通过飞书消息创建和编辑，把进度持续回推到群里

## 快速开始

先安装 PoCo：

```bash
pip install pocket-coding
```

如果你是从源码运行：

```bash
pip install .
```

然后按下面三步来：

1. 先创建一个飞书企业自建机器人应用，然后用 PoCo 一键补齐配置。

飞书应用本身必须先在开发者后台手动创建。拿到 `App ID` 和
`App Secret` 之后，运行：

在运行 bootstrap 之前，请先打开下面这个授权页，手动开通以下任意一个权限：

- `application:application`
- `admin:app.category:update`

授权页：

<https://open.feishu.cn/app/cli_a92032ebc97cdbcc/auth?q=application:application,admin:app.category:update&op_from=openapi&token_type=tenant>

然后再运行：

```bash
poco feishu-bootstrap
```

PoCo 会把这个应用改写成它需要的状态，包括权限、事件订阅、回调订阅，
不包括版本自动发布。

bootstrap 完成后，请你回到飞书开放平台，手动创建并发布一个新版本。
PoCo 会在 bootstrap 日志里打印建议使用的下一个语义版本号。

2. 确认运行 PoCo 的机器上已经装好并能正常使用 `codex` 或 `claude`
/ Claude Code。

PoCo 不负责帮你安装这些工具。如果它们不存在或者本机不能正常运行，
请先自己处理好，再继续。

3. 启动 PoCo，然后去飞书里和机器人单聊。

```bash
poco
```

在 DM 里发任意一条消息即可，例如：

```text
poco
```

这会打开 DM 控制台卡片。点击 `New Project` 创建一个项目群。
PoCo 会自动创建名为 `Pocket-Project: <project_id>` 的群，把你和机器人拉进去，
并启动默认 runtime：

- Agent：`codex`
- Provider：`openai`
- Model：`gpt-5.4`
- Reply Mode：`all`

如果要给当前 agent 发图片，请用一条飞书图文消息同时发送图片和文字说明。

PoCo 还自带一份预定义模型目录。当前 Claude provider 内置了这些模型：

- `sonnet`
- `opus`
- `haiku`
- `deepseek-chat`
- `deepseek-reasoner`
- `kimi-k2.5`
- `kimi-k2-0905-preview`
- `kimi-k2-0711-preview`
- `kimi-k2-turbo-preview`
- `kimi-k2-thinking`
- `kimi-k2-thinking-turbo`
- `moonshot-v1-8k`
- `moonshot-v1-32k`
- `moonshot-v1-128k`
- `moonshot-v1-8k-vision-preview`
- `moonshot-v1-32k-vision-preview`
- `moonshot-v1-128k-vision-preview`
- `MiniMax-M2.1`
- `MiniMax-M2.5`
- `MiniMax-M2.7`

当前内置的 Claude backend 包括：

- `anthropic`
- `deepseek`
- `kimi`
- `minimax`

之后默认就按这条路径用：

- 在单聊里发 `poco`
- 用 DM 控制台卡片做项目创建 / 状态查看 / 删除
- 在项目群里直接和 agent 聊天

## 工作方式

- 单聊机器人：管理控制台
- 群聊机器人：项目工作区
- 每个项目群会启动一个独立的 worker 进程
- 每个项目都通过 DM 控制台卡片配置
- PoCo 使用飞书长连接模式，不需要公网回调地址

## 使用方式

单聊控制台：

- 发 `poco`
- 用卡片完成新建项目、查看状态、删除项目

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

- 右侧会显示 `Config`、`Restart`、`Quit`
- 用 `↑ / ↓` 选择项目
- 按 `Enter` 进入

进入 `Config` 后：

- 右侧面板会变成选择菜单
- `↑ / ↓` 可以切换 section 或字段
- `Enter` 进入当前项
- `Esc` 返回上一级
  - `Language` 可以切换英文和中文
  - `Bot` 里包含 `feishu` 相关设置，比如 `App ID`、`App Secret`
  - `Agent & Model` 里包含 `codex` 和 `claude`
  - `claude` 会先进入 backend 菜单
  - 先选一个 backend，例如 `anthropic`、`minimax`，或用户新增的 custom backend
  - 带 `(default)` 标记的就是当前全局默认 Claude backend
  - 再编辑这个 backend 的 `base_url`、`auth_token`、`model`、`extra_env`
  - `model` 会再进入一个模型菜单；先选模型，再执行 `set_as_default`
  - `extra_env` 也会进入子菜单；按项管理环境变量，不再直接编辑原始 JSON
  - backend 页面里的 `set_as_default` 会把当前 backend 设为全局默认 Claude backend
- `show` 会打开当前配置文件的滚动视图
- 只有在编辑文本字段时，底部输入栏才会启用

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
uv run python -m py_compile poco/__init__.py poco/app.py poco/runtime.py poco/relay/app.py poco/config/store.py poco/tui/app.py
```
