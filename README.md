# PoCo

PoCo is a Python-first MVP scaffold for controlling server-side AI agent workflows from mobile messaging entrypoints.

## Current Scope

- `FastAPI` webhook service
- Feishu-first event gateway
- Optional Feishu long-connection intake for local development
- Feishu callback verification token support
- Feishu tenant access token retrieval and text / interactive card send support
- Card-first interaction scaffolding with platform-neutral dispatcher
- Codex-first agent execution path
- Asynchronous background task dispatch
- Feishu task-state push on confirmation wait and terminal states
- Platform-independent task controller
- In-memory task state store
- Stub fallback runner for flow validation

## Local Run

### Lowest-Friction Start

If you only want to verify that PoCo itself can run on this machine, you can start with no Feishu credentials at all:

```bash
uvicorn poco.main:app --reload
curl http://127.0.0.1:8000/health
```

In that mode:

- PoCo runs in local/demo mode
- the agent backend can still be checked
- you can still use the local demo HTTP interface
- Feishu callback handling is not ready yet

The `/health` response will tell you exactly what is missing.

### Local Demo Interface

You can exercise the full command flow without Feishu:

```bash
curl -X POST http://127.0.0.1:8000/demo/command \
  -H 'Content-Type: application/json' \
  -d '{"text":"/run Reply with exactly: DEMO_OK"}'
```

Check task status:

```bash
curl http://127.0.0.1:8000/tasks/<task_id>
```

Approval flow example:

```bash
curl -X POST http://127.0.0.1:8000/demo/command \
  -H 'Content-Type: application/json' \
  -d '{"text":"/run confirm: Reply with exactly: APPROVED"}'

curl -X POST http://127.0.0.1:8000/demo/tasks/<task_id>/approve
```

PoCo currently plans to support:

- Codex
- Claude Code
- Cursor Agent

Current implementation priority is Codex, and the default backend is `codex`.

Agent backend configuration:

```bash
export POCO_AGENT_BACKEND="codex"
export POCO_CODEX_COMMAND="codex"
export POCO_CODEX_WORKDIR="/absolute/path/to/your/repo"
```

Optional Codex settings:

```bash
export POCO_CODEX_MODEL="gpt-5.4"
export POCO_CODEX_SANDBOX="workspace-write"
export POCO_CODEX_APPROVAL_POLICY="never"
export POCO_CODEX_TIMEOUT_SECONDS="900"
```

Use `POCO_AGENT_BACKEND=stub` if you want to exercise the flow without calling Codex.

`claude_code` and `cursor_agent` are recognized as planned backends, but they are not implemented yet. If selected, PoCo will start and report the backend as not ready.

Set the Feishu app credentials before using the real callback flow:

```bash
export POCO_FEISHU_APP_ID="cli_xxx"
export POCO_FEISHU_APP_SECRET="xxx"
```

Choose the inbound delivery mode:

```bash
export POCO_FEISHU_DELIVERY_MODE="webhook"
```

Use `longconn` when you want local development without a public callback URL:

```bash
export POCO_FEISHU_DELIVERY_MODE="longconn"
```

Optional:

```bash
export POCO_FEISHU_API_BASE_URL="https://open.feishu.cn"
export POCO_FEISHU_VERIFICATION_TOKEN="xxx"
export POCO_FEISHU_ENCRYPT_KEY="xxx"
export POCO_STATE_BACKEND="sqlite"
export POCO_STATE_DB_PATH="/absolute/path/to/poco.db"
```

Notes:

- `POCO_FEISHU_VERIFICATION_TOKEN` is optional in the current MVP. Leaving it unset reduces setup friction, but also lowers webhook security.
- If `POCO_FEISHU_ENCRYPT_KEY` is configured, the service expects Feishu signature headers and validates them.
- Encrypted callback payload bodies are not supported yet, so keep event encryption disabled for the current MVP.
- `POCO_FEISHU_DELIVERY_MODE=longconn` removes the need for public inbound webhook access during local development.
- The current long-connection implementation now handles both `im.message.receive_v1` and card callback traffic for local/mobile-first operation.
- Callback token/signature settings apply to webhook delivery. Feishu long-connection inbound events are authenticated by the long-connection session itself.
- `POCO_STATE_BACKEND=sqlite` is now the default runtime path. PoCo persists projects, workspace state and tasks so restart does not lose existing group/workspace tracking.
- `POCO_STATE_DB_PATH` defaults to `.work/poco.db`.

Install dependencies, then start the service:

```bash
uvicorn poco.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

The health response now includes:

- current runtime mode: `local` or `feishu`
- chosen Feishu delivery mode: `webhook` or `longconn`
- chosen agent backend and whether it looks ready
- whether the Feishu long-connection listener is actually ready
- which state backend is in use
- whether Feishu callback token verification is enabled
- whether Feishu signature validation is enabled
- what is still missing
- warnings about relaxed safety settings

### Card Demo Interface

You can now exercise the first DM card chain locally:

```bash
curl http://127.0.0.1:8000/demo/cards/dm/projects
```

Create a project through the demo card-action endpoint:

```bash
curl -X POST http://127.0.0.1:8000/demo/card-actions \
  -H 'Content-Type: application/json' \
  -d '{
    "event": {
      "operator": {"open_id": "ou_demo_user"},
      "context": {"open_message_id": "om_demo_card"},
      "action": {
        "value": {
          "intent_key": "project.create",
          "surface": "dm",
          "request_id": "req_demo_project_create_1"
        },
        "form_value": {
          "name": "PoCo",
          "backend": "codex"
        }
      }
    }
  }'
```

This currently proves the first card chain:

- DM card action payload -> `ActionIntent`
- dispatcher -> project handler
- `IntentDispatchResult` -> render instruction
- renderer -> card response payload

Real Feishu DM bootstrap is now also wired:

- when PoCo receives a DM message event from Feishu
- it replies with a real Feishu card JSON 2.0 project-list card
- the project-list card now contains real callback buttons such as `Create Project + Group`
- `Create Project + Group` now creates the project and, in real Feishu mode, bootstraps a dedicated group chat in the same action
- after the group is created, PoCo also posts the first workspace overview card into that group
- opening a project in DM now lands on a `Project Config` card instead of a bare detail card
- current group chats still keep the text-command fallback path

That means the current interaction split is:

- `DM`: control-plane card bootstrap and first project-management actions
- `Group`: first workspace overview card plus text-command task fallback

Notes about project bootstrap:

- in real Feishu mode, `project.create` now calls the Feishu group-create API and binds the returned `chat_id` to the new project
- after binding the group, PoCo best-effort posts the first workspace overview card into the new group
- if group bootstrap fails, PoCo rolls the project creation back instead of leaving a half-created project behind
- in local/demo mode without Feishu credentials, `project.create` still works, but no group is created

### Feishu Debug Snapshot

When Feishu messages do not get any reply, inspect:

```bash
curl http://127.0.0.1:8000/debug/feishu
```

It shows:

- recent inbound Feishu callbacks
- the reply target PoCo selected for each callback
- recent outbound send attempts, including DM card sends
- recent Feishu send errors
- current long-connection listener status

This is the fastest way to tell whether the problem is:

- Feishu never called PoCo
- PoCo picked the wrong reply target
- PoCo tried to send but Feishu rejected the request

Real Feishu callbacks should target:

```text
POST /platform/feishu/events
```

Card action callbacks should currently target:

```text
POST /platform/feishu/card-actions
```

Current interaction model:

- DM messages currently bootstrap a compact home card instead of returning text help
- DM home cards now expose only `New` and `Manage`
- DM `New` now uses a pure-card form to collect `project name`, then creates the project and group before returning to the DM home card
- DM `Manage` now focuses on destructive admin actions; projects can be deleted there without opening a project detail card first, and deletion now cascades through local project state in sqlite/in-memory stores
- newly created project groups now receive an initial workspace overview card
- group workspace and task cards now route `Change Workdir` to a browser-based folder picker; the page supports both manual path entry and folder browsing
- group workspace cards are now intentionally compact: workspace metadata is collapsed into the title, and the body keeps only `Stop`, `Change Workdir`, and `Choose Model`
- `Choose Model` now opens a dedicated model-selection card; applying a model returns to the main workspace card
- browser-based workdir selection requires `POCO_APP_BASE_URL` so card buttons can open a reachable web page
- `Use Default` now updates the in-memory workspace context and becomes the first real write path for group-side workdir state
- `Enter Path` now updates the same in-memory workspace context and becomes the second real write path, using manual source
- DM `Manage Dir Presets` can now add project-level presets, and group `Choose Preset` can apply them into the current in-memory workspace context
- Group text `/run` now resolves the bound project and current workspace workdir, then stamps that into task execution context
- Bound group workspaces now also treat ordinary plain-text messages as task prompts by default
- Bound group workspaces now run tasks in a single-project queue: if one task is still active, the next message is queued instead of starting a parallel Codex run
- codex-backed groups now persist the upstream Codex thread id and reuse it with `exec resume`, so follow-up messages continue the same Codex conversation instead of starting from a blank context
- Group text-created tasks now reply with a single initial `task_status` card, and later live/terminal updates stay on that same card
- Codex execution now prefers the task's `effective_workdir` over the global fallback directory
- group card `task.submit` now reuses the same task-execution path and inherits the current workspace workdir
- `task.submit` now replaces the current composer card with a `task_status` card and binds that message to the task flow
- The webhook request returns quickly after acknowledging the command
- Task execution happens in a background dispatcher
- When a task waits for confirmation, completes, fails, or is cancelled, PoCo now pushes a `task_status` card to the stored Feishu reply target
- Waiting task cards now include `Approve` / `Reject` actions that resume or cancel the task through card callbacks
- Once a task status card has been sent, later task-state notifications now try to update that same card in place before falling back to a new message
- workspace cards now keep a bound message id and will also be refreshed with latest-task changes when task state changes
- task status cards now prefer the agent's raw result over summary text, and long results are paginated instead of being replaced by a summary
- task status cards now collapse task id, status, agent and effective workdir into the title; the body is reserved for model output or confirmation text instead of duplicated metadata
- task status titles now lead with bracketed status, for example `[Running] Task: ... (codex, no working dir)`, to keep the scan path tighter on mobile
- task and workspace cards now prefer direct action buttons over navigation-only buttons; task cards expose `Stop`, `Change Working Dir`, and `Change Model` instead of `Back`/`Refresh` style controls
- workspace cards no longer try to show latest-result body; the title carries status / agent / workdir / current task, and the body stays action-only
- running task cards now show throttled live output updates from the agent, instead of staying at a coarse `running` state

If `POCO_FEISHU_DELIVERY_MODE=longconn` is enabled:

- inbound message events arrive over Feishu long connection instead of the webhook route
- DM events can now trigger proactive project-list card sends
- group events still reuse the same `InteractionService -> TaskController -> Dispatcher -> Notifier` chain
- outbound replies still use the Feishu HTTP API
- card callbacks are now also handled through the Feishu long-connection listener

To verify the DM card bootstrap on a real Feishu bot:

1. Set `POCO_FEISHU_DELIVERY_MODE=longconn`
2. Start `uvicorn poco.main:app --reload`
3. Confirm `/health` shows `feishu_listener_ready=true`
4. Send any DM message like `hi` to the bot
5. The bot should reply with a `PoCo Projects` card
6. Click `Create Project + Group` and the card should refresh into a project detail view

Example webhook payload:

```json
{
  "token": "verification_token_from_feishu",
  "event": {
    "sender": {
      "sender_id": {
        "open_id": "ou_demo_user"
      }
    },
    "message": {
      "chat_id": "oc_demo_chat",
      "content": "{\"text\":\"/run confirm: review the deployment plan\"}"
    }
  }
}
```

## Supported Commands

- In a bound project group, you can now send plain text directly and PoCo will treat it as the task prompt.
- Group text-created tasks now reply with a single initial `task_status` card, and later live/terminal updates stay on that same card.
- Running-state card update failures no longer fallback to new-card fanout.
- PoCo now keeps a minimal persisted `active session` per project, and workspace cards show that session instead of a placeholder.
- PoCo now treats each project group as one stable session, instead of exposing multi-session lifecycle controls in the group UI.
- In sqlite-backed runtime, task card message ids are now persisted immediately so follow-up updates do not fan out into fresh cards.
- `/run <prompt>`
- `/status <task_id>`
- `/approve <task_id>`
- `/reject <task_id>`
- `/help`

If the prompt starts with `confirm:`, the stub runner pauses the task at a confirmation checkpoint so the approval flow can be exercised without a real agent backend.

The same `confirm:` prefix also works for the Codex backend: PoCo will pause before invoking `codex`, then continue only after `/approve <task_id>`.
