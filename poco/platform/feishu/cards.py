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
            "这是你的 DM 控制台。当前先打通首页卡片下发，后续再把创建项目、建群和工作区动作接成完整交互。"
        )
    ]

    if not projects:
        elements.append(
            _markdown(
                "**还没有 project**\n\n现在直接给这个 bot 发任意消息，就会刷新这张首页卡片。"
            )
        )
    else:
        for project in projects:
            group_hint = project.get("group_chat_id") or "未绑定群"
            elements.append(
                _markdown(
                    "\n".join(
                        [
                            f"**{project['name']}**",
                            f"- backend: `{project['backend']}`",
                            f"- group: `{group_hint}`",
                            f"- status: `{'archived' if project.get('archived') else 'active'}`",
                        ]
                    )
                )
            )

    return _card_shell(
        title="PoCo Projects",
        template="blue",
        elements=elements,
    )


def _render_project_detail(data: dict[str, Any]) -> dict[str, Any]:
    project = data["project"]
    group_hint = project.get("group_chat_id") or "未绑定群"
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
            _markdown("项目管理动作已经进入 card-first 结构，但真实按钮回调链还会继续补全。"),
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
