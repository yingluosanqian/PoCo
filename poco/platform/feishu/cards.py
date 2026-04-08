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
    elements: list[dict[str, Any]] = [
        _markdown(
            "这是你的 DM 控制台。现在可以直接在卡片里创建 project，并顺手自动拉起对应工作群。"
        ),
        _button(
            label="Create Project + Group",
            intent_value={
                "intent_key": "project.create",
                "surface": "dm",
            },
            style="primary",
            name="create_project_button",
        ),
    ]

    if not projects:
        elements.append(_markdown("**还没有 project**"))
    else:
        for project in projects:
            group_hint = project.get("group_chat_id") or "未绑定群"
            elements.extend(
                [
                    _markdown(
                        "\n".join(
                            [
                                f"**{project['name']}**",
                                f"- backend: `{project['backend']}`",
                                f"- group: `{group_hint}`",
                                f"- status: `{'archived' if project.get('archived') else 'active'}`",
                            ]
                        )
                    ),
                    _button(
                        label=f"Open {project['name']}",
                        intent_value={
                            "intent_key": "project.open",
                            "surface": "dm",
                            "project_id": project["id"],
                        },
                        name=f"open_project_{project['id']}",
                    ),
                ]
            )

    return _card_shell(
        title="PoCo Projects",
        template="blue",
        elements=elements,
    )


def _render_project_detail(data: dict[str, Any]) -> dict[str, Any]:
    project = data["project"]
    group_chat_id = project.get("group_chat_id")
    group_hint = f"已创建 (`{group_chat_id}`)" if group_chat_id else "未绑定群"
    repo_hint = project.get("repo") or "未设置"
    workdir_hint = project.get("workdir") or "未设置"
    return _card_shell(
        title=project["name"],
        template="green",
        elements=[
            _markdown(
                "\n".join(
                    [
                        f"**backend**: `{project['backend']}`",
                        f"**group**: `{group_hint}`",
                        f"**repo**: `{repo_hint}`",
                        f"**workdir**: `{workdir_hint}`",
                    ]
                )
            ),
            _button(
                label="Open Workspace",
                intent_value={
                    "intent_key": "workspace.open",
                    "surface": "dm",
                    "project_id": project["id"],
                },
                style="primary",
                name=f"open_workspace_{project['id']}",
            ),
            _button(
                label="Back To Projects",
                intent_value={
                    "intent_key": "project.list",
                    "surface": "dm",
                },
                name="back_to_projects_button",
            ),
        ],
    )


def _render_workspace_overview(data: dict[str, Any]) -> dict[str, Any]:
    project = data["project"]
    latest_status = data.get("latest_task_status") or "none"
    latest_result = data.get("latest_result_summary") or "No result yet."
    active_session = data.get("active_session_summary") or "No active session yet."
    pending_approvals = data.get("pending_approvals") or 0
    return _card_shell(
        title=f"Workspace: {project['name']}",
        template="orange",
        elements=[
            _markdown(f"**active session**\n{active_session}"),
            _markdown(f"**latest task status**: `{latest_status}`"),
            _markdown(f"**pending approvals**: `{pending_approvals}`"),
            _markdown(f"**latest result**\n{latest_result}"),
            _button(
                label="Refresh",
                intent_value={
                    "intent_key": "workspace.refresh",
                    "surface": "dm",
                    "project_id": project["id"],
                },
                name=f"refresh_workspace_{project['id']}",
            ),
            _button(
                label="Back To Project",
                intent_value={
                    "intent_key": "project.open",
                    "surface": "dm",
                    "project_id": project["id"],
                },
                name=f"back_to_project_{project['id']}",
            ),
        ],
    )


def _render_fallback(template_key: str | None, data: dict[str, Any]) -> dict[str, Any]:
    return _card_shell(
        title=template_key or "Unknown View",
        template="grey",
        elements=[
            _markdown(f"未识别的模板：`{template_key or 'unknown'}`"),
            _markdown(f"```json\n{data}\n```"),
        ],
    )


def _card_shell(
    *,
    title: str,
    template: str,
    elements: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "width_mode": "fill",
            "enable_forward_interaction": False,
        },
        "header": {
            "title": {
                "tag": "plain_text",
                "content": title,
            },
            "template": template,
            "padding": "12px 12px 12px 12px",
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 12px 12px",
            "elements": elements,
        },
    }


def _markdown(content: str) -> dict[str, Any]:
    return {
        "tag": "markdown",
        "content": content,
        "text_align": "left",
        "text_size": "normal_v2",
        "margin": "0px 0px 12px 0px",
    }


def _button(
    *,
    label: str,
    intent_value: dict[str, str],
    name: str,
    style: str = "default",
) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {
            "tag": "plain_text",
            "content": label,
        },
        "type": style,
        "width": "default",
        "size": "medium",
        "name": name,
        "behaviors": [
            {
                "type": "callback",
                "value": intent_value,
            }
        ],
        "margin": "0px 0px 12px 0px",
    }
