# PoCo

PoCo is a Python-first MVP scaffold for controlling server-side AI agent workflows from mobile messaging entrypoints.

## Current Scope

- `FastAPI` webhook service
- Feishu-first event gateway
- Feishu callback verification token support
- Feishu tenant access token retrieval and text message send support
- Codex-first agent execution path
- Asynchronous background task dispatch
- Feishu task-state push on confirmation wait and terminal states
- Platform-independent task controller
- In-memory task state store
- Stub fallback runner for flow validation

## Local Run

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
export POCO_FEISHU_VERIFICATION_TOKEN="xxx"
```

Optional:

```bash
export POCO_FEISHU_API_BASE_URL="https://open.feishu.cn"
export POCO_FEISHU_ENCRYPT_KEY="xxx"
```

If `POCO_FEISHU_ENCRYPT_KEY` is configured, the service expects Feishu signature headers and validates them. Encrypted callback payload bodies are not supported yet, so keep event encryption disabled for the current MVP.

Install dependencies, then start the service:

```bash
uvicorn poco.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

The health response now includes the chosen agent backend and whether the backend looks ready on this machine.

Real Feishu callbacks should target:

```text
POST /platform/feishu/events
```

Current interaction model:

- The webhook request returns quickly after acknowledging the command
- Task execution happens in a background dispatcher
- When a task waits for confirmation, completes, fails, or is cancelled, PoCo pushes a follow-up message to the stored Feishu reply target

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

- `/run <prompt>`
- `/status <task_id>`
- `/approve <task_id>`
- `/reject <task_id>`
- `/help`

If the prompt starts with `confirm:`, the stub runner pauses the task at a confirmation checkpoint so the approval flow can be exercised without a real agent backend.

The same `confirm:` prefix also works for the Codex backend: PoCo will pause before invoking `codex`, then continue only after `/approve <task_id>`.
