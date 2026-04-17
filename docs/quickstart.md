# PoCo Quickstart

> [中文版](quickstart-zh.md)

This guide gets PoCo running on your machine in under 5 minutes. By the end you'll have a Feishu bot that can send tasks to a server-side coding agent and show live results on your phone.

## Prerequisites

- Python 3.12+
- A coding agent CLI installed on the server: `codex`, `claude`, `cursor-agent`, or `traecli`
- A Feishu custom bot with App ID and App Secret

## 1. Create and configure a Feishu bot

1. **Create a bot**: open [Feishu Open Platform](https://open.larkoffice.com/app?lang=zh-CN) and create a new custom app.
2. **Add capabilities**: go to *App Capabilities*, find *Bot*, and click *Add*.
3. **Configure permissions**: go to *Permission Management* and batch-import the following scopes:

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

4. **Events and callbacks**:
   - 4.1 Add an event subscription: choose **Long Connection** as the delivery method, and subscribe to `im.message.receive_v1`.
   - 4.2 Add a callback subscription: choose **Long Connection** as the delivery method, and subscribe to `card.action.trigger`.

5. **Publish**: go to *Version Management & Release*, create a version and publish it.

After publishing, you can find the **App ID** and **App Secret** under *Credentials & Basic Info*.

## 2. Install PoCo

```bash
git clone <your-repo-url> PoCo
cd PoCo
python3 -m pip install -e .
# or uv run poco
```

Verify the CLI is available:

```bash
poco --help
```

## 3. Configure Feishu credentials

```bash
poco config
```

This prompts for your Feishu App ID and App Secret, and writes them to `~/.poco/poco.config.json`.

If you prefer environment variables (e.g. in a systemd unit or `.env` file):

```bash
export POCO_FEISHU_APP_ID="cli_xxxxx"
export POCO_FEISHU_APP_SECRET="xxxxxxxxxxxxxxxx"
```

When both env vars are set, `poco config` will detect them and skip the interactive prompt.

PoCo defaults to **long-connection mode** (`longconn`), which means no public URL or webhook setup is needed for local development. Feishu events arrive over the long-connection session directly.

## 4. Start PoCo

```bash
poco start
```

This starts PoCo as a background process. Check status:

```bash
poco status
```

Check the health endpoint for a detailed readiness report:

```bash
curl http://127.0.0.1:8000/health
```

The response tells you exactly what's ready, what's missing, and what to fix.

## 5. Send your first task

1. Open a DM conversation with your Feishu bot.
2. Send any message (e.g. "hi"). The bot replies with a **PoCo Projects** card.
3. Tap **New** to create a project. PoCo creates a dedicated group chat for it.
4. In the project group, type your task directly: `Review the test coverage in this repo`.
5. The bot replies with a **task status card** that streams the agent's output in real time.

## 6. What you'll see

While the task runs, the card title updates with a live activity hint:

```
[Running · Thinking] Task: a1b2c3d4 (gpt-5.4, /srv/myrepo)
[Running · Running: pytest -q] Task: a1b2c3d4 (gpt-5.4, /srv/myrepo)
[Running · Writing] Task: a1b2c3d4 (gpt-5.4, /srv/myrepo)
```

When the agent finishes:

```
[Complete] Task: a1b2c3d4 (gpt-5.4, /srv/myrepo)
```

The card body shows the full response text, and the title includes token usage when available.

## Next steps

- **Change the working directory**: tap `Working Dir` on the workspace card to browse, enter a path manually, or pick from presets.
- **Switch agent backend**: tap `Agent` on the workspace card to change model, sandbox, or backend entirely.
- **Attach to an existing session**: tap `Session` on the workspace card to resume a previous agent conversation, or paste an external session ID.
- **Check environment issues**: visit `http://127.0.0.1:8000/debug/env` to see which env vars PoCo inherited (no values are shown, just presence + length).
- **Debug message routing**: visit `/debug/feishu` to see recent inbound/outbound events if the bot isn't replying.

## Common issues

| Symptom | Likely cause | Fix |
|---|---|---|
| `/health` says `agent backend readiness` is missing | Agent CLI not on `$PATH` or workdir doesn't exist | `which codex` / check `POCO_CODEX_WORKDIR` |
| Bot never replies to DM | Feishu credentials wrong or long-connection not established | Check `/health` for `feishu_listener_ready` |
| Task card stuck at `[Running]` forever | Agent CLI hanging or env vars not inherited | Check `/debug/env` for missing `ANTHROPIC_BASE_URL` etc. |
| `codex_apps status: failed` in card | MCP server startup failed inside codex | Run `codex app-server` manually to see the error |
| `poco config` skipped prompts | `POCO_FEISHU_APP_ID` / `POCO_FEISHU_APP_SECRET` already in env | Intentional — env vars take precedence |

## Useful CLI commands

```bash
poco start            # start PoCo in the background
poco status           # show pid + health summary
poco restart          # stop + start
poco shutdown         # graceful stop
poco config           # interactive Feishu credential setup
```

Manual start (foreground, with hot reload):

```bash
uvicorn poco.main:app --reload
```
