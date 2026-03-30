# PoCo

[中文说明](README.zh-CN.md)

`PoCo` is the product name. The Python package name is `pocket-coding`.

PoCo is a local TUI for running coding-agent providers behind a Feishu bot. Codex is fully wired through `app-server`; Claude Code is wired through a CLI-backed provider with streamed output, session discovery, and session attach.

- DM the bot for management
- Use Feishu groups as project workspaces
- Run one provider-backed worker per project group
- Stream progress back by creating and editing Feishu messages

## Quick Start

Install PoCo:

```bash
pip install pocket-coding
```

Or from source:

```bash
pip install .
```

Then follow this flow:

1. Create one Feishu self-built bot app, then bootstrap it with PoCo.

Create the app manually in the Feishu developer console first. After you get
the `App ID` and `App Secret`, run:

Before running bootstrap, open this auth page and grant either
`application:application` or `admin:app.category:update`:

<https://open.feishu.cn/app/cli_a92032ebc97cdbcc/auth?q=application:application,admin:app.category:update&op_from=openapi&token_type=tenant>

Then run:

```bash
poco feishu-bootstrap
```

PoCo will rewrite the app into the state it needs, including scopes, event
subscriptions, and callback subscriptions.

After bootstrap finishes, create and publish a new app version manually in the
Feishu Open Platform. PoCo will print the suggested next semantic version in
the bootstrap log.

2. Make sure the machine running PoCo already has `codex` or `claude` / Claude
Code installed and working.

PoCo does not install these tools for you. If they are missing or broken, fix
that first on your machine, then continue.

3. Start PoCo, then open a DM with the bot.

```bash
poco
```

In the DM, send any message. For example:

```text
poco
```

This opens the DM control card. Use `New Project` to create a project group.
PoCo will create a group named `Pocket-Project: <project_id>`, add you, add the
bot, and start the default runtime:

- Agent: `codex`
- Provider: `openai`
- Model: `gpt-5.4`
- Reply Mode: `all`

To send images to the current agent, send one Feishu post message that includes
both the image and the text prompt. PoCo will forward them together.

PoCo also ships with predefined model catalogs. For the Claude provider, the built-in list currently includes:

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

Built-in Claude backends currently include:

- `anthropic`
- `deepseek`
- `kimi`
- `minimax`

After that, the default workflow is simple:

- DM the bot with `poco`
- use the DM console card for project create / status / remove
- in the project group, just talk to the agent

## How It Works

- DM with the bot: management console
- Group chat with the bot: project workspace
- Each project group gets its own worker process
- Each project is configured from the DM console card
- PoCo connects to Feishu in long-connection mode, so no public callback URL is required

## Usage

DM console:

- send `poco`
- use the card UI to create a project, inspect a worker, or remove a worker

Project group:

- just talk to the agent
- send one Feishu post message that contains both the image and the text prompt
- no setup or lifecycle commands are needed in the group

## Providers

- `codex`: fully implemented through `codex app-server`
- `claude`: implemented through the Claude Code CLI with streamed JSON output

Current provider notes:

- Codex is the default runtime path
- Claude currently supports session attach, image input, and streamed replies

## TUI

Views:

The TUI is a two-panel terminal UI:

- left panel: logo and runtime summary
- right panel: the current menu or interaction view
- bottom: an input line that is only enabled when a config field needs text input

Shortcuts:

- `Ctrl+R`: Save and restart
- `q`: go back one level
- `Up` / `Down`: move in the main menu or config menu
- `Enter`: open the selected item
- `Esc`: go back one level

The default home screen is menu-driven:

- the right panel shows a menu with `Config`, `Restart`, and `Quit`
- use `Up` / `Down` to select an item
- press `Enter` to open it

`Config` enters config mode. In that mode:

- the right panel turns into a selection menu
- `Up` / `Down` moves between sections or fields
- `Enter` opens the current selection
- `Esc` returns to the previous level
  - `Language` lets you switch between English and Chinese
  - `Bot` contains `feishu` settings such as `App ID` and `App Secret`
  - `Agent & Model` contains `codex` and `claude`
  - `claude` opens a backend menu first
  - choose a backend such as `anthropic`, `minimax`, or a user-added custom backend
  - the backend marked with `(default)` is the current global Claude default
  - then edit that backend's `base_url`, `auth_token`, `model`, and `extra_env`
  - `model` opens another menu; pick a model first, then run `set_as_default`
  - `extra_env` also opens a submenu; manage env entries one by one instead of editing raw JSON
  - `set_as_default` on the backend page marks that backend as the global Claude default
- `show` opens the current config in a scrollable view
- the bottom input line is only active while editing a text field

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
uv run python -m py_compile poco/__init__.py poco/app.py poco/runtime.py poco/relay/app.py poco/config/store.py poco/tui/app.py
```
