from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from poco.agent.runner import create_agent_runner
from poco.config import Settings
from poco.interaction.service import InteractionService
from poco.platform.feishu.client import FeishuAccessTokenProvider, FeishuApiError, FeishuMessageClient
from poco.platform.feishu.gateway import FeishuGateway
from poco.platform.feishu.verification import FeishuRequestVerifier, FeishuVerificationError
from poco.storage.memory import InMemoryTaskStore
from poco.task.controller import TaskController, TaskNotFoundError
from poco.task.dispatcher import AsyncTaskDispatcher
from poco.task.notifier import FeishuTaskNotifier, NullTaskNotifier


def create_app() -> FastAPI:
    settings = Settings()
    store = InMemoryTaskStore()
    runner = create_agent_runner(
        backend=settings.agent_backend,
        codex_command=settings.codex_command,
        codex_workdir=settings.codex_workdir,
        codex_model=settings.codex_model,
        codex_sandbox=settings.codex_sandbox,
        codex_approval_policy=settings.codex_approval_policy,
        codex_timeout_seconds=settings.codex_timeout_seconds,
    )
    controller = TaskController(store=store, runner=runner)
    interaction = InteractionService(controller)
    request_verifier = FeishuRequestVerifier(
        verification_token=settings.feishu_verification_token,
        encrypt_key=settings.feishu_encrypt_key,
    )
    message_client = None
    if settings.feishu_enabled:
        token_provider = FeishuAccessTokenProvider(
            base_url=settings.feishu_api_origin,
            app_id=settings.feishu_app_id or "",
            app_secret=settings.feishu_app_secret or "",
        )
        message_client = FeishuMessageClient(
            base_url=settings.feishu_api_origin,
            token_provider=token_provider,
        )
    notifier = FeishuTaskNotifier(message_client) if message_client is not None else NullTaskNotifier()
    dispatcher = AsyncTaskDispatcher(controller, notifier=notifier)
    gateway = FeishuGateway(
        interaction,
        request_verifier=request_verifier,
        message_client=message_client,
        dispatcher=dispatcher,
    )

    app = FastAPI(title=settings.app_name)
    app.state.task_controller = controller
    app.state.feishu_gateway = gateway
    app.state.settings = settings
    app.state.agent_runner = runner
    app.state.task_dispatcher = dispatcher

    @app.get("/health")
    def health() -> dict[str, Any]:
        agent_ready, agent_detail = runner.is_ready()
        return {
            "status": "ok",
            "feishu_enabled": settings.feishu_enabled,
            "agent_backend": runner.name,
            "agent_ready": agent_ready,
            "agent_detail": agent_detail,
        }

    @app.post("/platform/feishu/events")
    async def handle_feishu_event(request: Request) -> dict[str, Any]:
        raw_body = await request.body()
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Feishu payload must be a JSON object.")

        try:
            return gateway.handle_event(
                payload,
                headers=request.headers,
                raw_body=raw_body,
            )
        except FeishuVerificationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except FeishuApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/tasks")
    def list_tasks() -> dict[str, list[dict[str, object]]]:
        tasks = [task.to_dict() for task in controller.list_tasks()]
        return {"tasks": tasks}

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, object]:
        try:
            task = controller.get_task(task_id)
        except TaskNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return task.to_dict()

    return app


app = create_app()
