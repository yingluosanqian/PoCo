# Quick Start

## Install

Install the latest release with `pip`:

```bash
pip install pocket-coding
```

Or install from source:

```bash
git clone git@github.com:yingluosanqian/PoCo.git
cd PoCo
pip install .
```

## Configure

Prerequisite: you need to configure either Codex CLI or Claude Code CLI yourself.
PoCo calls those tools directly, but does not reuse their setup automatically,
so you still need to complete their own CLI setup first.

Create and configure the Feishu bot by following [this guide](feishu-bot-setup.md).

## Run

After the setup is done, run `poco` in your terminal, then send any message to
the Feishu bot and follow the prompts.

DM with the bot is the control console. You can create projects there, and PoCo
will automatically create a group for each project. One group maps to one task.

- `new` creates a new project
- `manage` manages an existing project
