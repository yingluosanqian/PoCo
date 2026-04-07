from __future__ import annotations

from typing import Any

from poco.interaction.card_models import PlatformRenderInstruction


class FeishuCardRenderer:
    def render(self, instruction: PlatformRenderInstruction) -> dict[str, Any]:
        if instruction.template_key == "project_list":
            return _render_project_list(instruction.template_data)
        if instruction.template_key == "project_detail":
            return _render_project_detail(instruction.template_data)
        if instruction.template_key == "workspace_overview":
            return _render_workspace_overview(instruction.template_data)
        return _render_fallback(instruction.template_key, instruction.template_data)


def _render_project_list(data: dict[str, Any]) -> dict[str, Any]:
    projects = data.get("projects", [])
    elements: list[dict[str, Any]] = []
    if not projects:
        elements.append({"type": "markdown", "content": "No projects yet."})
    for project in projects:
        elements.append(
            {
                "type": "project_item",
                "project_id": project["id"],
                "name": project["name"],
                "backend": project["backend"],
                "bound_group": project.get("group_chat_id"),
            }
        )
    return {
        "schema": "2.0",
        "view": "project_list",
        "title": "Projects",
        "elements": elements,
        "actions": [
            {"intent_key": "project.create", "label": "Create Project"},
        ],
    }


def _render_project_detail(data: dict[str, Any]) -> dict[str, Any]:
    project = data["project"]
    return {
        "schema": "2.0",
        "view": "project_detail",
        "title": project["name"],
        "project": project,
        "summary": {
            "backend": project["backend"],
            "repo": project.get("repo"),
            "workdir": project.get("workdir"),
            "group_chat_id": project.get("group_chat_id"),
            "archived": project.get("archived", False),
        },
        "actions": [
            {"intent_key": "project.bind_group", "label": "Bind Group"},
            {"intent_key": "workspace.open", "label": "Open Workspace"},
        ],
    }


def _render_workspace_overview(data: dict[str, Any]) -> dict[str, Any]:
    project = data["project"]
    return {
        "schema": "2.0",
        "view": "workspace_overview",
        "title": f"Workspace: {project['name']}",
        "project": project,
        "stats": {
            "active_session_summary": data.get("active_session_summary"),
            "latest_task_status": data.get("latest_task_status"),
            "pending_approvals": data.get("pending_approvals"),
            "latest_result_summary": data.get("latest_result_summary"),
        },
        "actions": [
            {"intent_key": "workspace.refresh", "label": "Refresh"},
        ],
    }


def _render_fallback(template_key: str | None, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "view": template_key or "unknown",
        "title": template_key or "Unknown View",
        "data": data,
    }

