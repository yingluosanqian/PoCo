from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from poco.agent.runner import create_agent_runner
from poco.config import Settings
from poco.demo import DemoCommandRequest
from poco.interaction.card_dispatcher import CardActionDispatcher, build_render_instruction
from poco.interaction.card_models import Surface
from poco.interaction.card_handlers import (
    ProjectIntentHandler,
    TaskIntentHandler,
    WorkspaceIntentHandler,
    build_workspace_overview_result,
)
from poco.interaction.service import InteractionService
from poco.platform.feishu.client import FeishuAccessTokenProvider, FeishuApiError, FeishuMessageClient
from poco.platform.feishu.card_gateway import FeishuCardActionGateway
from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.platform.feishu.cards import FeishuCardRenderer
from poco.platform.feishu.gateway import FeishuGateway
from poco.platform.feishu.longconn import FeishuLongconnListener
from poco.platform.feishu.project_bootstrap import FeishuProjectBootstrapper
from poco.platform.feishu.verification import FeishuRequestVerifier, FeishuVerificationError
from poco.project.bootstrap import NullProjectBootstrapper, ProjectBootstrapError
from poco.project.controller import ProjectController
from poco.session.controller import SessionController
from poco.storage.memory import InMemoryProjectStore, InMemorySessionStore, InMemoryTaskStore, InMemoryWorkspaceContextStore
from poco.storage.sqlite import SqliteProjectStore, SqliteSessionStore, SqliteTaskStore, SqliteWorkspaceContextStore
from poco.task.controller import TaskController, TaskNotFoundError
from poco.task.dispatcher import AsyncTaskDispatcher
from poco.task.notifier import FeishuTaskNotifier, NullTaskNotifier
from poco.workspace.controller import WorkspaceContextController


class DemoDecisionRequest(BaseModel):
    approved: bool


def create_app(*, settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    if settings.state_backend == "sqlite":
        store = SqliteTaskStore(settings.state_db_path)
        project_store = SqliteProjectStore(settings.state_db_path)
        workspace_store = SqliteWorkspaceContextStore(settings.state_db_path)
        session_store = SqliteSessionStore(settings.state_db_path)
    else:
        store = InMemoryTaskStore()
        project_store = InMemoryProjectStore()
        workspace_store = InMemoryWorkspaceContextStore()
        session_store = InMemorySessionStore()
    card_renderer = FeishuCardRenderer()
    runner = create_agent_runner(
        backend=settings.agent_backend,
        codex_command=settings.codex_command,
        codex_workdir=settings.codex_workdir,
        codex_model=settings.codex_model,
        codex_sandbox=settings.codex_sandbox,
        codex_approval_policy=settings.codex_approval_policy,
        codex_timeout_seconds=settings.codex_timeout_seconds,
        claude_command=settings.claude_command,
        claude_workdir=settings.claude_workdir,
        claude_model=settings.claude_model,
        claude_permission_mode=settings.claude_permission_mode,
        claude_timeout_seconds=settings.claude_timeout_seconds,
        cursor_command=settings.cursor_command,
        cursor_workdir=settings.cursor_workdir,
        cursor_model=settings.cursor_model,
        cursor_mode=settings.cursor_mode,
        cursor_sandbox=settings.cursor_sandbox,
        cursor_timeout_seconds=settings.cursor_timeout_seconds,
    )
    session_controller = SessionController(session_store)
    controller = TaskController(store=store, runner=runner, session_controller=session_controller)
    controller.recover_interrupted_tasks()
    project_controller = ProjectController(
        project_store,
        task_store=store,
        session_store=session_store,
        workspace_store=workspace_store,
    )
    workspace_controller = WorkspaceContextController(workspace_store)
    interaction = InteractionService(controller, session_controller=session_controller)
    feishu_debug = FeishuDebugRecorder()
    request_verifier = FeishuRequestVerifier(
        verification_token=settings.feishu_verification_token,
        encrypt_key=settings.feishu_encrypt_key,
    )
    message_client = None
    project_bootstrapper = NullProjectBootstrapper()
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
        project_bootstrapper = FeishuProjectBootstrapper(
            message_client,
            renderer=card_renderer,
            project_controller=project_controller,
            debug_recorder=feishu_debug,
        )
    notifier = (
        FeishuTaskNotifier(
            message_client,
            renderer=card_renderer,
            project_controller=project_controller,
            session_controller=session_controller,
            task_controller=controller,
            workspace_controller=workspace_controller,
            debug_recorder=feishu_debug,
        )
        if message_client is not None
        else NullTaskNotifier()
    )
    dispatcher = AsyncTaskDispatcher(controller, notifier=notifier)
    project_intent_handler = ProjectIntentHandler(
        project_controller,
        bootstrapper=project_bootstrapper,
    )
    workspace_intent_handler = WorkspaceIntentHandler(
        project_controller,
        workspace_controller,
        controller,
        session_controller=session_controller,
        default_workdir=settings.codex_workdir,
    )
    task_intent_handler = TaskIntentHandler(
        project_controller,
        workspace_controller,
        controller,
        session_controller=session_controller,
        dispatcher=dispatcher,
    )
    card_dispatcher = CardActionDispatcher(
        {
            "project.home": project_intent_handler,
            "project.new": project_intent_handler,
            "project.manage": project_intent_handler,
            "project.list": project_intent_handler,
            "project.create": project_intent_handler,
            "project.delete": project_intent_handler,
            "project.open": project_intent_handler,
            "project.configure_agent": project_intent_handler,
            "project.configure_repo": project_intent_handler,
            "project.configure_default_dir": project_intent_handler,
            "project.manage_dir_presets": project_intent_handler,
            "project.add_dir_preset": project_intent_handler,
            "project.bind_group": project_intent_handler,
            "project.archive": project_intent_handler,
            "workspace.open": workspace_intent_handler,
            "workspace.use_default_dir": workspace_intent_handler,
            "workspace.choose_preset": workspace_intent_handler,
            "workspace.apply_preset_dir": workspace_intent_handler,
            "workspace.use_recent_dir": workspace_intent_handler,
            "workspace.enter_path": workspace_intent_handler,
            "workspace.enter_path_manual": workspace_intent_handler,
            "workspace.apply_entered_path": workspace_intent_handler,
            "workspace.choose_model": workspace_intent_handler,
            "workspace.choose_agent": workspace_intent_handler,
            "workspace.apply_model": workspace_intent_handler,
            "workspace.apply_agent": workspace_intent_handler,
            "task.open_composer": task_intent_handler,
            "task.open": task_intent_handler,
            "task.submit": task_intent_handler,
            "task.stop": task_intent_handler,
            "task.approve": task_intent_handler,
            "task.reject": task_intent_handler,
        }
    )
    card_gateway = FeishuCardActionGateway(
        dispatcher=card_dispatcher,
        renderer=card_renderer,
        project_controller=project_controller,
        request_verifier=request_verifier,
        debug_recorder=feishu_debug,
    )
    gateway = FeishuGateway(
        interaction,
        request_verifier=request_verifier,
        message_client=message_client,
        dispatcher=dispatcher,
        card_gateway=card_gateway,
        task_controller=controller,
        card_renderer=card_renderer,
        debug_recorder=feishu_debug,
        project_controller=project_controller,
        workspace_controller=workspace_controller,
    )
    longconn_listener = FeishuLongconnListener(
        app_id=settings.feishu_app_id,
        app_secret=settings.feishu_app_secret,
        gateway=gateway,
        card_gateway=card_gateway,
        delivery_mode=settings.feishu_delivery_mode,
        debug_recorder=feishu_debug,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        longconn_listener.start_background()
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.task_controller = controller
    app.state.project_controller = project_controller
    app.state.session_controller = session_controller
    app.state.workspace_controller = workspace_controller
    app.state.feishu_gateway = gateway
    app.state.feishu_card_gateway = card_gateway
    app.state.settings = settings
    app.state.agent_runner = runner
    app.state.task_dispatcher = dispatcher
    app.state.feishu_debug = feishu_debug
    app.state.feishu_longconn = longconn_listener
    app.state.message_client = message_client
    app.state.card_renderer = card_renderer
    app.state.project_bootstrapper = project_bootstrapper

    @app.get("/health")
    def health() -> dict[str, Any]:
        agent_ready, agent_detail = runner.is_ready()
        listener_ready, listener_detail = longconn_listener.readiness()
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
        if settings.feishu_longconn_enabled:
            warnings.append(
                "Feishu long connection mode is enabled. Public webhook ingress is not required for inbound message events."
            )
            warnings.append(
                "Current long connection intake handles both message events and card callbacks."
            )
            if settings.feishu_verification_enabled or settings.feishu_signature_enabled:
                warnings.append(
                    "Feishu callback token/signature validation settings only apply to webhook delivery, not long connection inbound events."
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
        if settings.feishu_longconn_enabled and not listener_ready:
            missing.append("feishu long connection listener")

        return {
            "status": "ok",
            "mode": settings.runtime_mode,
            "feishu_enabled": settings.feishu_enabled,
            "feishu_delivery_mode": settings.feishu_delivery_mode,
            "feishu_verification_enabled": settings.feishu_verification_enabled,
            "feishu_signature_enabled": settings.feishu_signature_enabled,
            "feishu_listener_ready": listener_ready,
            "feishu_listener_detail": listener_detail,
            "state_backend": settings.state_backend,
            "state_db_path": settings.state_db_path if settings.state_backend == "sqlite" else None,
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

    @app.post("/platform/feishu/card-actions")
    async def handle_feishu_card_action(request: Request) -> dict[str, Any]:
        raw_body = await request.body()
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Feishu payload must be a JSON object.")

        try:
            return card_gateway.handle_action(
                payload,
                headers=dict(request.headers),
                raw_body=raw_body,
            )
        except FeishuVerificationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
            elif response.dispatch_action == "advance_queue":
                task = controller.get_task(response.task_id)
                if task.project_id:
                    dispatcher.dispatch_next_queued(task.project_id)

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
        elif response.dispatch_action == "advance_queue" and response.task_id:
            task = controller.get_task(response.task_id)
            if task.project_id:
                dispatcher.dispatch_next_queued(task.project_id)
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
        if response.dispatch_action == "advance_queue" and response.task_id:
            task = controller.get_task(response.task_id)
            if task.project_id:
                dispatcher.dispatch_next_queued(task.project_id)
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

    @app.get("/debug/feishu")
    def feishu_debug_snapshot() -> dict[str, Any]:
        snapshot = app.state.feishu_debug.snapshot()
        snapshot["listener"] = app.state.feishu_longconn.snapshot()
        return snapshot

    @app.get("/demo/cards/dm/projects")
    def demo_dm_project_list_card() -> dict[str, Any]:
        response = card_gateway.render_dm_project_list()
        response["mode"] = "demo"
        return response

    @app.post("/demo/card-actions")
    def demo_card_action(payload: dict[str, Any]) -> dict[str, Any]:
        response = card_gateway.handle_action(payload)
        response["mode"] = "demo"
        return response

    return app


app = create_app()
