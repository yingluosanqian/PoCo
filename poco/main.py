from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from poco.agent.runner import StubAgentRunner
from poco.config import Settings
from poco.interaction.service import InteractionService
from poco.platform.feishu.gateway import FeishuGateway
from poco.storage.memory import InMemoryTaskStore
from poco.task.controller import TaskController, TaskNotFoundError


def create_app() -> FastAPI:
    settings = Settings()
    store = InMemoryTaskStore()
    runner = StubAgentRunner()
    controller = TaskController(store=store, runner=runner)
    interaction = InteractionService(controller)
    gateway = FeishuGateway(interaction)

    app = FastAPI(title=settings.app_name)
    app.state.task_controller = controller
    app.state.feishu_gateway = gateway

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/platform/feishu/events")
    def handle_feishu_event(payload: dict[str, Any]) -> dict[str, Any]:
        return gateway.handle_event(payload)

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
