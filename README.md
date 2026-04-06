# PoCo

PoCo is a Python-first MVP scaffold for controlling server-side AI agent workflows from mobile messaging entrypoints.

## Current Scope

- `FastAPI` webhook service
- Feishu-first event gateway
- Platform-independent task controller
- In-memory task state store
- Stub agent runner for flow validation

## Local Run

Install dependencies, then start the service:

```bash
uvicorn poco.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Example webhook payload:

```json
{
  "event": {
    "sender": {
      "sender_id": {
        "open_id": "ou_demo_user"
      }
    },
    "message": {
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
