# PoCo

PoCo is a Python-first scaffold for driving server-side coding agents from chat surfaces (Feishu today, Slack since this release). Projects, workspaces, sessions, and tasks all live in PoCo; the chat bot is a thin interactive front-end for them.

## Supported Platforms

- **Feishu** — DM control plane + per-project group chat, over webhook **or** long connection (`longconn`, default).
- **Slack** — DM control plane + per-project channel, over Socket Mode (default) **or** HTTP webhooks. Slash command `/poco` opens the same project-list card the DM surface renders.

Both platforms run simultaneously when configured. Every `Task` / `Project` remembers which platform it was created from, and replies are routed back to the originating surface by `PlatformRoutingTaskNotifier`.

## Supported Agent Backends

- `codex` (default) — runs through `codex app-server` over stdio; streams real `agentMessage/delta` events into task cards.
- `claude_code`
- `cursor_agent`
- `coco` (Trae CLI)
- `stub` — local flow validation only.

Backend per project is picked from the DM project-creation card. Environment variables are server-side defaults only.

## Quick Start

```bash
python3 -m pip install -e .
poco config    # interactive prompt for Feishu credentials
poco start
poco status
```

`poco config` writes `~/.poco/poco.config.json`. Environment variables override file values at runtime. To run with no chat platform at all (just the HTTP demo surface and agent runner), skip `poco config` and start directly:

```bash
poco start
curl http://127.0.0.1:8000/health
```

`/health` explicitly lists what is missing for each platform.

## Configuration

PoCo reads config from three layers, in decreasing precedence:

1. `POCO_*` environment variables
2. Flat keys in `~/.poco/poco.config.json` (same name as the env var)
3. Sectioned keys in the same file, e.g. `{"feishu": {"app_id": "..."}, "slack": {"bot_token": "..."}}`

### Feishu

| Key | Purpose |
| --- | --- |
| `POCO_FEISHU_APP_ID` / `POCO_FEISHU_APP_SECRET` | Required to enable the Feishu integration. |
| `POCO_FEISHU_DELIVERY_MODE` | `longconn` (default) or `webhook`. |
| `POCO_FEISHU_VERIFICATION_TOKEN` | Optional webhook token. Lowers friction when unset, lowers security too. |
| `POCO_FEISHU_ENCRYPT_KEY` | Enables signature validation on webhook callbacks. Encrypted payload bodies are not supported yet. |
| `POCO_FEISHU_API_BASE_URL` | Defaults to `https://open.feishu.cn`. |

Long-connection mode authenticates inbound events via the long-connection session itself and routes both message events and card callbacks over the same listener. Callback token/signature settings only apply to webhook delivery.

### Slack

| Key | Purpose |
| --- | --- |
| `POCO_SLACK_BOT_TOKEN` | `xoxb-…` bot token. Required. |
| `POCO_SLACK_SIGNING_SECRET` | Required for HTTP webhook signature verification. |
| `POCO_SLACK_APP_TOKEN` | `xapp-…` app-level token. Required when `POCO_SLACK_DELIVERY_MODE=socket`. |
| `POCO_SLACK_DELIVERY_MODE` | `socket` (default) or `webhook`. |

Slack is considered enabled when bot token + signing secret (+ app token, for socket mode) are all set. `/poco` slash command posts the project-list card as an ephemeral reply.

### Agent backend (server-side)

Minimum:

```bash
export POCO_AGENT_BACKEND="codex"
export POCO_CODEX_COMMAND="codex"
export POCO_CODEX_WORKDIR="/absolute/path/to/your/repo"
```

Optional per-backend tuning:

```bash
# Codex
export POCO_CODEX_MODEL="gpt-5"
export POCO_CODEX_SANDBOX="workspace-write"
export POCO_CODEX_APPROVAL_POLICY="never"
export POCO_CODEX_TIMEOUT_SECONDS="900"
export POCO_CODEX_TRANSPORT_IDLE_SECONDS="1800"

# Claude Code
export POCO_CLAUDE_COMMAND="claude"
export POCO_CLAUDE_WORKDIR="/absolute/path/to/your/repo"
export POCO_CLAUDE_MODEL="sonnet"
export POCO_CLAUDE_PERMISSION_MODE="default"
export POCO_CLAUDE_TIMEOUT_SECONDS="900"

# Cursor Agent
export POCO_CURSOR_COMMAND="cursor-agent"
export POCO_CURSOR_WORKDIR="/absolute/path/to/your/repo"
export POCO_CURSOR_MODEL="auto"
export POCO_CURSOR_MODE="default"
export POCO_CURSOR_SANDBOX="default"
export POCO_CURSOR_TIMEOUT_SECONDS="900"

# Trae CLI (coco)
export POCO_COCO_COMMAND="traecli"
export POCO_COCO_WORKDIR="/absolute/path/to/your/repo"
export POCO_COCO_MODEL="GPT-5"
export POCO_COCO_APPROVAL_MODE="default"
export POCO_COCO_TIMEOUT_SECONDS="900"
```

### State backend

```bash
export POCO_STATE_BACKEND="sqlite"        # default
export POCO_STATE_DB_PATH="~/.poco/poco.db"
```

SQLite is the default runtime path. It persists projects, workspace context, sessions, and tasks so a restart does not lose group/workspace bookkeeping.

## Interaction Model

- **DM**: control plane. `New` creates a project and its bound group; `Manage` lists projects and exposes delete. DM inbound messages always render the project-list card.
- **Group**: workspace card with `Stop` / `Working Dir` / `Agent` actions, plus plain-text task submission. `Working Dir` selection (folder browse, manual entry, recent directories, and project-level presets) stays inside cards. `Agent` opens a dedicated selection card.

Group behavior:

- Plain text in a bound group is a task prompt.
- Tasks in a project run in a single-project queue — a new message is queued while another task is still active.
- Codex groups persist the upstream thread id and resume it via `codex app-server`, so follow-up messages continue the same Codex conversation.
- Task cards show bracketed status in the title (e.g. `[Running] Task: … (codex, /srv/api)`), and live-stream throttled agent output.
- Waiting task cards expose `Approve` / `Reject`; later state transitions update the same card in place before falling back to a new message.
- Workspace cards are refreshed when the latest task changes and keep a bound `message_id` across updates.

## HTTP Surface

Core endpoints:

| Path | Purpose |
| --- | --- |
| `GET /health` | Runtime readiness + missing/warn summary for both platforms. |
| `GET /tasks`, `GET /tasks/{task_id}` | Raw task state. |
| `GET /debug/feishu`, `GET /debug/slack` | Recent inbound events, outbound attempts, errors, listener snapshot for the respective platform. |
| `GET /debug/env` | Presence/length of whitelisted env keys (no values are returned). |

Feishu endpoints:

- `POST /platform/feishu/events`
- `POST /platform/feishu/card-actions`

Slack endpoints:

- `POST /platform/slack/events` (JSON body, `X-Slack-Signature` verified)
- `POST /platform/slack/interactive` (form-encoded `payload=…`)
- `POST /platform/slack/commands` (form-encoded slash command)

Demo endpoints (platform-agnostic):

- `POST /demo/command` — `{"text":"/run …"}`
- `POST /demo/tasks/{task_id}/approve`
- `POST /demo/tasks/{task_id}/reject`
- `GET /demo/cards/dm/projects`
- `POST /demo/card-actions`

### Supported text commands

In a bound project group, any plain text is treated as a task prompt. The explicit commands are still accepted:

- `/run <prompt>` — start a task.
- `/status <task_id>`
- `/approve <task_id>` / `/reject <task_id>`
- `/help`

If the prompt starts with `confirm:`, the stub runner and the Codex backend pause at a confirmation checkpoint; `/approve <task_id>` resumes.

## Local Demo Example

Without any chat platform configured:

```bash
curl -X POST http://127.0.0.1:8000/demo/command \
  -H 'Content-Type: application/json' \
  -d '{"text":"/run Reply with exactly: DEMO_OK"}'

curl http://127.0.0.1:8000/tasks/<task_id>
```

Approval flow:

```bash
curl -X POST http://127.0.0.1:8000/demo/command \
  -H 'Content-Type: application/json' \
  -d '{"text":"/run confirm: Reply with exactly: APPROVED"}'

curl -X POST http://127.0.0.1:8000/demo/tasks/<task_id>/approve
```

## CLI

```bash
poco config           # interactive Feishu credential prompt
poco start            # starts uvicorn in the background, pid in ~/.poco/poco.pid
poco status           # pid + /health summary
poco restart
poco shutdown
```

Manual fallback:

```bash
uvicorn poco.main:app --reload
```

## Packaging

```bash
python3 -m pip install build
python3 -m build
# produces dist/*.whl and dist/*.tar.gz
```

When published, installation will be:

```bash
python3 -m pip install pocket-coding
```

## Debugging Reply Issues

When a chat message does not get a reply, compare `/debug/feishu` or `/debug/slack` against the expected flow:

- If there are no recent inbound entries: the platform never reached PoCo (check long-connection/socket-mode listener status under `listener`, or the public webhook route).
- If inbound entries exist but there are no outbound attempts: PoCo dropped the message (e.g. unbound group, ignored bot message).
- If outbound attempts exist but errors accumulate: the platform rejected the send (scope/permission issues usually).

`/health` also surfaces listener readiness for both platforms plus the current agent backend readiness.
