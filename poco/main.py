from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from poco.agent.runner import create_agent_runner
from poco.config import Settings
from poco.demo import DemoCommandRequest
from poco.interaction.service import InteractionService
from poco.platform.feishu.client import FeishuAccessTokenProvider, FeishuApiError, FeishuMessageClient
from poco.platform.feishu.gateway import FeishuGateway
from poco.platform.feishu.verification import FeishuRequestVerifier, FeishuVerificationError
from poco.storage.memory import InMemoryTaskStore
from poco.task.controller import TaskController, TaskNotFoundError
from poco.task.dispatcher import AsyncTaskDispatcher
from poco.task.notifier import FeishuTaskNotifier, NullTaskNotifier


class DemoDecisionRequest(BaseModel):
    approved: bool


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
        missing = []
        warnings = []

        if not settings.feishu_enabled:
            missing.extend(["POCO_FEISHU_APP_ID", "POCO_FEISHU_APP_SECRET"])
            warnings.append(
                "Feishu integration is disabled. PoCo is currently in local/demo mode."
            )
        if not settings.feishu_verification_enabled:
            warnings.append(
                "Feishu callback verification token is disabled. This lowers security but keeps MVP setup friction low."
            )
        if settings.feishu_signature_enabled:
            warnings.append(
                "Feishu signature validation is enabled. Encrypted event bodies are still unsupported in the current MVP."
            )
        else:
            warnings.append(
                "Feishu signature validation is disabled."
            )

        if not agent_ready:
            missing.append("agent backend readiness")

        return {
            "status": "ok",
            "mode": settings.runtime_mode,
            "feishu_enabled": settings.feishu_enabled,
            "feishu_verification_enabled": settings.feishu_verification_enabled,
            "feishu_signature_enabled": settings.feishu_signature_enabled,
            "agent_backend": runner.name,
            "agent_ready": agent_ready,
            "agent_detail": agent_detail,
            "missing": missing,
            "warnings": warnings,
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

    @app.post("/demo/command")
    def handle_demo_command(payload: DemoCommandRequest) -> dict[str, Any]:
        response = interaction.handle_text(
            user_id=payload.user_id,
            text=payload.text,
            source="demo",
        )
        task = controller.get_task(response.task_id) if response.task_id else None
        if response.task_id:
            if response.dispatch_action == "start":
                dispatcher.dispatch_start(response.task_id)
            elif response.dispatch_action == "resume":
                dispatcher.dispatch_resume(response.task_id)

        return {
            "ok": True,
            "mode": "demo",
            "response_text": response.text,
            "task_id": response.task_id,
            "dispatch_action": response.dispatch_action,
            "task": task.to_dict() if task is not None else None,
        }

    @app.post("/demo/tasks/{task_id}/approve")
    def approve_demo_task(task_id: str) -> dict[str, Any]:
        response = interaction.handle_text(
            user_id="local_demo_user",
            text=f"/approve {task_id}",
            source="demo",
        )
        if response.dispatch_action == "resume" and response.task_id:
            dispatcher.dispatch_resume(response.task_id)
        task = controller.get_task(task_id)
        return {
            "ok": True,
            "mode": "demo",
            "response_text": response.text,
            "task": task.to_dict(),
        }

    @app.post("/demo/tasks/{task_id}/reject")
    def reject_demo_task(task_id: str) -> dict[str, Any]:
        response = interaction.handle_text(
            user_id="local_demo_user",
            text=f"/reject {task_id}",
            source="demo",
        )
        task = controller.get_task(task_id)
        return {
            "ok": True,
            "mode": "demo",
            "response_text": response.text,
            "task": task.to_dict(),
        }

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
