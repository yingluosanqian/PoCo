# 快速开始

## 安装

可以通过 `pip` 安装最新版：

```
pip install pocket-coding
```

或者从源码安装：

```
git clone git@github.com:yingluosanqian/PoCo.git
cd PoCo
pip install .
```

## 配置

前置：用户需要自行配置 Codex CLI 或者 Claude Code CLI。该工具会直接调用，但不会复用设置，所以还需要再工具内再次配置。

按照[这里](feishu-bot-setup.md)创建并配置飞书机器人。

## 运行

完成配置后，在终端运行 `poco` 后，向飞书机器人发送任意消息，按提示交互即可。

私聊机器人是控制台；可以通过私聊机器人创建项目（会自动拉群，一个群对应一个任务）。

- `new` 创建新项目；
- `manage` 管理已有项目。
