from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
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


class ProjectCreateRequest(BaseModel):
    actor_id: str
    name: str
    backend: str = "codex"


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
    card_renderer = FeishuCardRenderer(app_base_url=settings.app_origin)
    runner = create_agent_runner(
        backend=settings.agent_backend,
        codex_command=settings.codex_command,
        codex_workdir=settings.codex_workdir,
        codex_model=settings.codex_model,
        codex_sandbox=settings.codex_sandbox,
        codex_approval_policy=settings.codex_approval_policy,
        codex_timeout_seconds=settings.codex_timeout_seconds,
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
            "workspace.apply_entered_path": workspace_intent_handler,
            "workspace.choose_model": workspace_intent_handler,
            "workspace.apply_model": workspace_intent_handler,
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
        if not settings.app_origin:
            warnings.append(
                "POCO_APP_BASE_URL is not configured. Browser-based workdir selection will fall back to card callbacks."
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

    @app.get("/ui/workdir", response_class=HTMLResponse)
    def workdir_browser(project_id: str, path: str | None = None, saved: int = 0) -> HTMLResponse:
        try:
            project = project_controller.get_project(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        context = workspace_controller.get_context(project)
        initial_path = (
            path
            or context.active_workdir
            or project.workdir
            or settings.codex_workdir
        )
        browser = _build_workdir_browser_state(initial_path)
        status_note = "Working dir updated." if saved else ""
        body = _render_workdir_browser_html(
            project_name=project.name,
            project_id=project.id,
            current_workdir=context.active_workdir,
            selected_path=browser["selected_path"],
            browse_path=browser["browse_path"],
            parent_path=browser["parent_path"],
            child_dirs=browser["child_dirs"],
            error=browser["error"],
            status_note=status_note,
        )
        return HTMLResponse(body)

    @app.get("/ui/projects/new", response_class=HTMLResponse)
    def project_create_page(actor_id: str | None = None, saved: int = 0, project_name: str | None = None) -> HTMLResponse:
        body = _render_project_create_html(
            actor_id=actor_id or "",
            project_name=project_name or "",
            saved=bool(saved),
        )
        return HTMLResponse(body)

    @app.post("/api/projects")
    def create_project_from_browser(request: ProjectCreateRequest) -> dict[str, Any]:
        actor_id = request.actor_id.strip()
        if not actor_id:
            raise HTTPException(status_code=400, detail="actor_id is required.")
        name = request.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Project name cannot be empty.")
        backend = request.backend.strip() or "codex"

        project = project_controller.create_project(
            name=name,
            created_by=actor_id,
            backend=backend,
        )
        try:
            bootstrap = app.state.project_bootstrapper.bootstrap_project(
                project=project,
                actor_id=actor_id,
            )
        except ProjectBootstrapError as exc:
            project_controller.delete_project(project.id)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if bootstrap.group_chat_id is not None:
            project = project_controller.bind_group(project.id, bootstrap.group_chat_id)
            try:
                app.state.project_bootstrapper.notify_project_workspace(
                    project=project,
                    actor_id=actor_id,
                )
            except Exception:
                pass
        return {
            "ok": True,
            "project_id": project.id,
            "project_name": project.name,
            "group_chat_id": project.group_chat_id,
            "redirect_url": f"/ui/projects/new?{urlencode({'actor_id': actor_id, 'saved': 1, 'project_name': project.name})}",
        }

    @app.post("/api/projects/{project_id}/workdir")
    async def apply_project_workdir(project_id: str, request: Request) -> dict[str, Any]:
        try:
            project = project_controller.get_project(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Payload must be a JSON object.")
        workdir = str(payload.get("workdir") or "").strip()
        if not workdir:
            raise HTTPException(status_code=400, detail="Workdir path cannot be empty.")
        try:
            normalized = str(Path(workdir).expanduser().resolve())
        except OSError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not Path(normalized).is_dir():
            raise HTTPException(status_code=400, detail="Workdir path must be an existing directory.")

        context = workspace_controller.use_manual_workdir(project, normalized)
        _refresh_workspace_card(
            project=project,
            context=context,
        )
        return {
            "ok": True,
            "project_id": project.id,
            "workdir": normalized,
            "source": context.workdir_source,
            "redirect_url": f"/ui/workdir?{urlencode({'project_id': project.id, 'path': normalized, 'saved': 1})}",
        }

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


def _build_workdir_browser_state(path: str) -> dict[str, Any]:
    selected = str(Path(path).expanduser())
    resolved = Path(selected)
    error = ""
    browse_target = resolved
    if resolved.exists() and resolved.is_file():
        error = "Selected path is a file. Choose a directory."
        browse_target = resolved.parent
    elif not resolved.exists():
        error = "Selected path does not exist yet. You can still edit it manually."
        parent = resolved.parent
        browse_target = parent if parent.exists() and parent.is_dir() else Path.home()
    else:
        try:
            browse_target = resolved.resolve()
        except OSError:
            browse_target = resolved

    child_dirs: list[str] = []
    try:
        child_dirs = sorted(
            str(item.resolve())
            for item in browse_target.iterdir()
            if item.is_dir()
        )
    except OSError as exc:
        error = str(exc)

    parent_path = None
    if browse_target.parent != browse_target:
        parent_path = str(browse_target.parent)
    return {
        "selected_path": selected,
        "browse_path": str(browse_target),
        "parent_path": parent_path,
        "child_dirs": child_dirs,
        "error": error,
    }


def _render_workdir_browser_html(
    *,
    project_name: str,
    project_id: str,
    current_workdir: str | None,
    selected_path: str,
    browse_path: str,
    parent_path: str | None,
    child_dirs: list[str],
    error: str,
    status_note: str,
) -> str:
    current_label = escape(current_workdir or "no working dir")
    selected_label = escape(selected_path)
    browse_label = escape(browse_path)
    error_block = f'<p class="note error">{escape(error)}</p>' if error else ""
    status_block = f'<p class="note success">{escape(status_note)}</p>' if status_note else ""
    parent_link = ""
    if parent_path:
        parent_query = urlencode({"project_id": project_id, "path": parent_path})
        parent_link = (
            f'<a class="dir-link" href="/ui/workdir?{parent_query}">'
            f"<strong>..</strong><span>{escape(parent_path)}</span></a>"
        )
    child_links = "".join(
        f'<a class="dir-link" href="/ui/workdir?{urlencode({"project_id": project_id, "path": item})}">'
        f"<strong>{escape(Path(item).name or item)}</strong><span>{escape(item)}</span></a>"
        for item in child_dirs
    ) or '<p class="note">No child directories here.</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Workdir Browser</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background: #f6f4ef; color: #171717; }}
    .wrap {{ max-width: 760px; margin: 0 auto; padding: 24px 16px 40px; }}
    h1 {{ font-size: 24px; margin: 0 0 8px; }}
    .meta {{ color: #555; margin: 0 0 20px; }}
    .card {{ background: #fffdfa; border: 1px solid #dfd7c8; border-radius: 16px; padding: 16px; margin-bottom: 16px; }}
    .label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #7a6d58; margin-bottom: 8px; }}
    .path {{ font-family: ui-monospace, SFMono-Regular, monospace; word-break: break-all; }}
    input {{ width: 100%; box-sizing: border-box; padding: 12px 14px; border-radius: 12px; border: 1px solid #cfc3ad; font-size: 15px; }}
    .actions {{ display: flex; gap: 12px; margin-top: 12px; flex-wrap: wrap; }}
    button {{ border: 0; border-radius: 12px; padding: 12px 16px; background: #1f6feb; color: white; font-size: 15px; }}
    .secondary {{ background: #ece5d8; color: #222; }}
    .dirs {{ display: grid; gap: 8px; }}
    .dir-link {{ display: block; padding: 12px 14px; border-radius: 12px; background: #f3eee3; color: #1f1f1f; text-decoration: none; border: 1px solid #e0d8ca; }}
    .dir-link strong {{ display: block; font-size: 15px; }}
    .dir-link span {{ display: block; margin-top: 4px; color: #5c554b; font-size: 13px; word-break: break-all; }}
    .section-note {{ margin: 0 0 12px; color: #5d5446; }}
    .note {{ margin: 10px 0 0; color: #5d5446; }}
    .error {{ color: #a12727; }}
    .success {{ color: #176d3a; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Change Working Dir</h1>
    <p class="meta">{escape(project_name)}</p>
    <div class="card">
      <div class="label">Current</div>
      <div class="path">{current_label}</div>
    </div>
    <div class="card">
      <div class="label">Browse Folders</div>
      <p class="section-note">Option 1. Browse like open-folder, then apply the folder you want.</p>
      <div class="path">{browse_label}</div>
      <div class="actions">
        <button id="apply-browsed-button" type="button">Use This Folder</button>
        <a class="dir-link secondary" href="/ui/workdir?{urlencode({'project_id': project_id})}">Reset Browser</a>
      </div>
      <div class="dirs">
        {parent_link}
        {child_links}
      </div>
    </div>
    <div class="card">
      <div class="label">Enter Path Manually</div>
      <p class="section-note">Option 2. Type the full path yourself and apply it directly.</p>
      <input id="workdir-input" value="{selected_label}" spellcheck="false" />
      <div class="actions">
        <button id="apply-button" type="button">Apply Typed Path</button>
      </div>
      {status_block}
      {error_block}
    </div>
  </div>
  <script>
    async function applyWorkdir(workdir) {{
      const response = await fetch("/api/projects/{escape(project_id)}/workdir", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ workdir }})
      }});
      const payload = await response.json();
      if (!response.ok) {{
        alert(payload.detail || "Failed to update workdir.");
        return;
      }}
      window.location.href = payload.redirect_url;
    }}
    document.getElementById("apply-button").addEventListener("click", async () => {{
      await applyWorkdir(document.getElementById("workdir-input").value);
    }});
    document.getElementById("apply-browsed-button").addEventListener("click", async () => {{
      await applyWorkdir("{selected_label}");
    }});
  </script>
</body>
</html>"""


def _render_project_create_html(
    *,
    actor_id: str,
    project_name: str,
    saved: bool,
) -> str:
    saved_block = ""
    if saved and project_name:
        saved_block = f'<p class="note success">Project created: {escape(project_name)}</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>New Project</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background: #f6f4ef; color: #171717; }}
    .wrap {{ max-width: 680px; margin: 0 auto; padding: 24px 16px 40px; }}
    h1 {{ font-size: 24px; margin: 0 0 8px; }}
    .meta {{ color: #555; margin: 0 0 20px; }}
    .card {{ background: #fffdfa; border: 1px solid #dfd7c8; border-radius: 16px; padding: 16px; margin-bottom: 16px; }}
    .label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #7a6d58; margin-bottom: 8px; }}
    input, select {{ width: 100%; box-sizing: border-box; padding: 12px 14px; border-radius: 12px; border: 1px solid #cfc3ad; font-size: 15px; background: white; }}
    .actions {{ display: flex; gap: 12px; margin-top: 12px; flex-wrap: wrap; }}
    button {{ border: 0; border-radius: 12px; padding: 12px 16px; background: #1f6feb; color: white; font-size: 15px; }}
    .note {{ margin: 10px 0 0; color: #5d5446; }}
    .success {{ color: #176d3a; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>New Project</h1>
    <p class="meta">Create project and group in one step.</p>
    <div class="card">
      <div class="label">Project Name</div>
      <input id="project-name" value="{escape(project_name)}" placeholder="Project name" spellcheck="false" />
    </div>
    <div class="card">
      <div class="label">Agent</div>
      <select id="agent-backend">
        <option value="codex" selected>Codex</option>
      </select>
      {saved_block}
    </div>
    <div class="actions">
      <button id="create-project-button" type="button">Create Project + Group</button>
    </div>
  </div>
  <script>
    async function createProject() {{
      const response = await fetch("/api/projects", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{
          actor_id: "{escape(actor_id)}",
          name: document.getElementById("project-name").value,
          backend: document.getElementById("agent-backend").value
        }})
      }});
      const payload = await response.json();
      if (!response.ok) {{
        alert(payload.detail || "Failed to create project.");
        return;
      }}
      window.location.href = payload.redirect_url;
    }}
    document.getElementById("create-project-button").addEventListener("click", createProject);
  </script>
</body>
</html>"""


def _refresh_workspace_card(*, project, context) -> None:
    message_client = app.state.message_client
    if message_client is None or not project.workspace_message_id:
        return
    tasks = app.state.task_controller.list_tasks_for_project(project.id)
    latest_task = max(tasks, key=lambda task: task.updated_at) if tasks else None
    instruction = build_render_instruction(
        build_workspace_overview_result(
            project,
            context=context,
            active_session=app.state.session_controller.get_active_session(project.id),
            latest_task=latest_task,
            message=f"Workspace refreshed for {project.name}",
        ),
        surface=Surface.GROUP,
    )
    card = app.state.card_renderer.render(instruction)
    message_client.update_interactive(
        message_id=project.workspace_message_id,
        card=card,
    )
