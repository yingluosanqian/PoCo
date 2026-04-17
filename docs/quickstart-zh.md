# PoCo 快速开始

> [English version](quickstart.md)

本指南帮你在 5 分钟内跑起 PoCo。完成后你会有一个飞书机器人，可以从手机上给服务端的编程 agent 发任务，并实时查看结果。

## 前置条件

- Python 3.12+
- 服务器上已安装一个编程 agent CLI：`codex`、`claude`、`cursor-agent` 或 `traecli`
- 一个飞书自建应用，拿到 App ID 和 App Secret

## 1. 创建并配置飞书机器人

1. **创建应用**：打开 [飞书开放平台](https://open.larkoffice.com/app?lang=zh-CN)，创建一个自建应用。
2. **添加应用能力**：进入 *应用能力*，找到 *机器人*，点击 *添加*。
3. **配置权限**：进入 *权限管理*，一键导入以下权限：

```json
{
  "scopes": {
    "tenant": [
      "aily:file:write",
      "application:application.app_message_stats.overview:readonly",
      "application:application:self_manage",
      "application:bot.menu:write",
      "cardkit:card:read",
      "cardkit:card:write",
      "contact:user.employee_id:readonly",
      "docs:document.content:read",
      "event:ip_list",
      "im:app_feed_card:write",
      "im:chat.access_event.bot_p2p_chat:read",
      "im:chat.collab_plugins:write_only",
      "im:chat.members:bot_access",
      "im:chat:create",
      "im:chat:delete",
      "im:chat:operate_as_owner",
      "im:chat:read",
      "im:chat:update",
      "im:message",
      "im:message.group_at_msg:readonly",
      "im:message.p2p_msg:readonly",
      "im:message:readonly",
      "im:message:send_as_bot",
      "im:message:update",
      "im:resource",
      "wiki:wiki:readonly"
    ],
    "user": [
      "aily:file:write",
      "im:chat.access_event.bot_p2p_chat:read"
    ]
  }
}
```

4. **事件与回调**：
   - 4.1 添加事件订阅：订阅方式选择 **长连接**，添加事件 `im.message.receive_v1`。
   - 4.2 添加回调订阅：订阅方式选择 **长连接**，添加事件 `card.action.trigger`。

5. **发布**：进入 *版本管理与发布*，创建版本并发布。

发布后，在 *凭证与基础信息* 页面可以看到 **App ID** 和 **App Secret**。

## 2. 安装 PoCo

```bash
git clone <your-repo-url> PoCo
cd PoCo
python3 -m pip install -e .
# 或 uv run poco
```

验证 CLI 可用：

```bash
poco --help
```

## 3. 配置飞书凭证

```bash
poco config
```

会交互式提示输入飞书 App ID 和 App Secret，写入 `~/.poco/poco.config.json`。

如果你倾向使用环境变量（例如 systemd unit 或 `.env` 文件）：

```bash
export POCO_FEISHU_APP_ID="cli_xxxxx"
export POCO_FEISHU_APP_SECRET="xxxxxxxxxxxxxxxx"
```

当两个环境变量都已设置时，`poco config` 会自动检测并跳过交互提示。

PoCo 默认使用**长连接模式**（`longconn`），本地开发时不需要公网 URL 或 webhook 配置。飞书事件直接通过长连接会话到达。

## 4. 启动 PoCo

```bash
poco start
```

PoCo 以后台进程运行。查看状态：

```bash
poco status
```

也可以通过健康检查端点获取详细的就绪报告：

```bash
curl http://127.0.0.1:8000/health
```

返回内容会明确告诉你哪些模块就绪、哪些缺失、如何修复。

## 5. 发送第一个任务

1. 在飞书里给你的机器人发一条私聊消息（比如"hi"）。机器人会回复一张 **PoCo Projects** 卡片。
2. 点击 **New** 创建项目。PoCo 会自动创建一个专属群聊。
3. 在项目群里直接输入你的任务：`检查一下这个仓库的测试覆盖率`。
4. 机器人回复一张 **任务状态卡片**，实时展示 agent 的输出内容。

## 6. 你会看到什么

任务运行时，卡片标题会实时更新当前活动：

```
[Running · Thinking] Task: a1b2c3d4 (gpt-5.4, /srv/myrepo)
[Running · Running: pytest -q] Task: a1b2c3d4 (gpt-5.4, /srv/myrepo)
[Running · Writing] Task: a1b2c3d4 (gpt-5.4, /srv/myrepo)
```

agent 完成后：

```
[Complete] Task: a1b2c3d4 (gpt-5.4, /srv/myrepo)
```

卡片正文展示完整回复文本，标题中包含 token 用量信息。

## 下一步

- **切换工作目录**：在 workspace 卡片上点击 `Working Dir`，可以浏览目录、手动输入路径或从预设中选择。
- **切换 agent**：点击 `Agent` 可以更改模型、沙箱或 backend。
- **接入已有会话**：点击 `Session` 可以恢复之前的 agent 对话，或粘贴一个外部 session ID。
- **排查环境问题**：访问 `http://127.0.0.1:8000/debug/env` 查看 PoCo 进程继承了哪些环境变量（只显示是否存在和长度，不暴露值）。
- **排查消息链路**：访问 `/debug/feishu` 查看近期的入站/出站事件，定位机器人不回复的原因。

## 常见问题

| 症状 | 可能原因 | 解决方式 |
|---|---|---|
| `/health` 提示 `agent backend readiness` 缺失 | agent CLI 不在 `$PATH` 里，或 workdir 不存在 | `which codex` / 检查 `POCO_CODEX_WORKDIR` |
| 私聊机器人没有任何回复 | 飞书凭证错误或长连接未建立 | 检查 `/health` 的 `feishu_listener_ready` |
| 任务卡片一直停在 `[Running]` | agent CLI 卡住或环境变量未继承 | 检查 `/debug/env` 看 `ANTHROPIC_BASE_URL` 等是否缺失 |
| 卡片显示 `codex_apps status: failed` | codex 内部 MCP server 启动失败 | 手动运行 `codex app-server` 查看具体错误 |
| `poco config` 跳过了输入提示 | `POCO_FEISHU_APP_ID` / `POCO_FEISHU_APP_SECRET` 已在环境变量中 | 正常行为——环境变量优先 |

## 常用 CLI 命令

```bash
poco start            # 后台启动 PoCo
poco status           # 查看 pid + 健康状态
poco restart          # 重启
poco shutdown         # 优雅停止
poco config           # 交互式配置飞书凭证
```

前台启动（带热重载）：

```bash
uvicorn poco.main:app --reload
```
