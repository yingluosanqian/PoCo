# PoCo

[中文说明](README.zh-CN.md)

`PoCo` is the product name. The Python package name is `pocket-coding`.

PoCo is a local TUI for running `Codex app-server` behind a Feishu bot.

- DM the bot for management
- Use Feishu groups as project workspaces
- Run one Codex worker per project group
- Stream progress back by creating and editing Feishu messages

## Quick Start

Install:

```bash
pip install pocket-coding
```

Or from source:

```bash
pip install .
```

Start:

```bash
poco
```

Non-interactive config is also supported:

```bash
poco config app_id "cli_xxx"
poco config app_secret "your-secret"
poco config --show
```

In the TUI:

1. Fill in `Feishu App ID` and `App Secret`
2. Click `Save & Restart`
3. Add the bot to a project group
4. In that group, run:

```text
/poco name my-project
/poco cwd /path/to/project
/poco mode mention
/poco enable
```

After that:

- DM the bot with `/poco workers` or `/poco status my-project`
- In the group, use `/poco ...` for PoCo commands
- In the group, all non-`/poco` text is forwarded to Codex

To attach the current group worker to an existing Codex CLI session:

```text
/poco attach <session_id>
```

PoCo will try to import the session working directory from local Codex state and bind the current worker to that session.

## How It Works

- DM with the bot: management console
- Group chat with the bot: project workspace
- Each project group gets its own Codex worker process
- Each group must configure its own working directory before enable
- PoCo connects to Feishu in long-connection mode, so no public callback URL is required

## Commands

DM commands:

- `/poco help`
- `/poco workers`
- `/poco list`
- `/poco sessions [limit]`
- `/poco status <worker_alias|group_chat_id>`
- `/poco stop <worker_alias|group_chat_id>`
- `/poco reset <worker_alias|group_chat_id>`
- `/poco remove <worker_alias|group_chat_id>`

Group commands:

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

When a worker is already running:

- normal text is rejected
- use `/poco steer <message>` to guide the current turn
- use `/poco queue <message>` to queue one follow-up message for the next turn
- use `/poco stop` to interrupt the current turn

## Feishu Requirements

Use a self-built enterprise app, not a custom webhook bot.

Required capabilities:

- Bot enabled
- Event subscription: `im.message.receive_v1`
- Permission to send messages
- Permission to update messages

Recommended:

- Long connection mode

## TUI

Views:

The TUI is a two-panel terminal UI:

- left panel: logo and runtime summary
- right panel: current interaction view
- bottom: one slash-command line for control

Shortcuts:

- `Ctrl+R`: Save and restart
- `q`: Quit
- `Up` / `Down`: move in the command dropdown or config menu
- `Tab`: complete the selected slash command

Inside the TUI, use commands such as:

```text
/help
/config
/log
/restart
/quit
```

Typing `/` in the command input shows available commands. Prefixes also work for discovery, for example `/co` suggests `/config`.

`/config` enters config mode. In that mode:

- the right panel turns into a selection menu
- `Up` / `Down` moves between sections
- `language` lets you switch between English and Chinese
- `feishu` walks you through `App ID` and `App Secret`
- only `/quit` leaves config mode from the command line

Typing `/config` shows slash suggestions including `/config show`.

`/config show` opens the current config in the right panel. If the content is longer than the panel, use `Up` / `Down` to scroll.

`/quit` returns from subviews such as log or help back to the dashboard. When you are already on the dashboard, `/quit` exits the TUI.

## Files

- Config: `~/.config/poco/config.json`
- State: `~/.local/state/poco/`

## Development

Build packages:

```bash
uv build
```

Quick syntax check:

```bash
uv run python -m py_compile poco/__init__.py poco/app.py poco/runtime.py poco/bridge.py poco/config/store.py poco/tui/app.py
```
