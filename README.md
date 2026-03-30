# PoCo

[中文说明](README.zh-CN.md)

**PoCo** (Pocket-Coding) is a bot runtime that connects different coding agents to workplace chat software.

It currently supports Codex, Claude Code, and Feishu bots.

## Quick Start

See [Quick Start](docs/quickstart.md).

## How It Works

- DM with the bot: management console
- Group chat with the bot: project workspace
- Each project group gets its own worker process
- Each project is configured from the DM console card
- PoCo uses Feishu long-connection mode, so no public callback URL is required

## Usage

DM console:

- send `poco`
- use the card UI to create a project and manage projects

Project group:

- just talk to the agent
- if you want to send an image, send one Feishu post message that contains both the image and the text prompt

## Provider

- `codex`: fully implemented through `codex app-server`
- `claude`: implemented through the Claude Code CLI with streamed JSON output

Current provider notes:

- Codex is the default runtime path
- Claude currently supports session attach, image input, and streamed replies

## TUI

The TUI is a two-panel terminal UI:

- left panel: logo and runtime summary
- right panel: the current interaction panel
- bottom: an input line that is only enabled when a config field needs text input

Shortcuts:

- `Ctrl+R`: Save and restart
- `q`: go back one level
- `↑ / ↓`: move in the main menu or config menu
- `Enter`: open the selected item
- `Esc`: go back one level

The default home screen is menu-driven:

- the right panel shows:
  - `Agent & Model`
  - `Bot (feishu)`
  - `PoCo`
  - `Language`
  - `Quit`
- use `↑ / ↓` to select an item
- press `Enter` to open it

Top-level items open their config sections directly:

- the right panel turns into a selection menu
- `↑ / ↓` moves between sections or fields
- `Enter` opens the current selection
- `Esc` returns to the previous level
- `Language` lets you switch between English and Chinese
- `Bot (feishu)` contains Feishu settings such as `App ID` and `App Secret`
- `Agent & Model` contains `codex` and `claude`
- `claude` opens a provider menu first
- choose a provider such as `anthropic`, `minimax`, `deepseek`, or `kimi`
- then edit that provider's `base_url`, `auth_token`, `model`, and `extra_env`
- `model` opens another menu; pick a model first, then run `set_as_default`
- `extra_env` also opens a submenu; manage env entries one by one instead of editing raw JSON
- `show` opens the current config in a scrollable view
- the bottom input line is only active while editing a text field

## Files

- Workspace bindings: `~/.config/poco/workspaces.json`
- Per-bot config file: `~/.config/poco/bindings/<app_id>/config.json`
- Per-bot state directory: `~/.local/state/poco/<app_id>/`
- Legacy default config/state are still under:
  - `~/.config/poco/config.json`
  - `~/.local/state/poco/`

## Development

Build packages:

```bash
uv build
```

Quick syntax check:

```bash
uv run python -m py_compile poco/__init__.py poco/app.py poco/runtime.py poco/relay/app.py poco/config/store.py poco/tui/app.py
```
