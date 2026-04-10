from __future__ import annotations

from typing import Any

from poco.interaction.card_models import PlatformRenderInstruction


class FeishuCardRenderer:
    def render(self, instruction: PlatformRenderInstruction) -> dict[str, Any]:
        if instruction.template_key == "project_list":
            return _render_project_list(instruction.template_data)
        if instruction.template_key == "project_config":
            return _render_project_config(
                instruction.template_data,
                surface=instruction.surface.value,
            )
        if instruction.template_key == "project_agent_config":
            return _render_project_agent_config(
                instruction.template_data,
                surface=instruction.surface.value,
            )
        if instruction.template_key == "project_repo_config":
            return _render_project_repo_config(
                instruction.template_data,
                surface=instruction.surface.value,
            )
        if instruction.template_key == "project_default_dir_config":
            return _render_project_default_dir_config(
                instruction.template_data,
                surface=instruction.surface.value,
            )
        if instruction.template_key == "project_dir_presets":
            return _render_project_dir_presets(
                instruction.template_data,
                surface=instruction.surface.value,
            )
        if instruction.template_key == "workspace_overview":
            return _render_workspace_overview(
                instruction.template_data,
                surface=instruction.surface.value,
            )
        if instruction.template_key == "workspace_workdir_switcher":
            return _render_workspace_workdir_switcher(
                instruction.template_data,
                surface=instruction.surface.value,
            )
        if instruction.template_key == "workspace_use_default_dir":
            return _render_workspace_use_default_dir(
                instruction.template_data,
                surface=instruction.surface.value,
            )
        if instruction.template_key == "workspace_choose_preset":
            return _render_workspace_choose_preset(
                instruction.template_data,
                surface=instruction.surface.value,
            )
        if instruction.template_key == "workspace_recent_dirs":
            return _render_workspace_recent_dirs(
                instruction.template_data,
                surface=instruction.surface.value,
            )
        if instruction.template_key == "workspace_enter_path":
            return _render_workspace_enter_path(
                instruction.template_data,
                surface=instruction.surface.value,
            )
        if instruction.template_key == "task_composer":
            return _render_task_composer(
                instruction.template_data,
                surface=instruction.surface.value,
            )
        if instruction.template_key == "task_status":
            return _render_task_status(
                instruction.template_data,
                surface=instruction.surface.value,
            )
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


def _render_project_config(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    group_chat_id = project.get("group_chat_id")
    group_hint = f"已创建 (`{group_chat_id}`)" if group_chat_id else "未绑定群"
    repo_hint = project.get("repo") or "未设置"
    workdir_hint = project.get("workdir") or "未设置"
    return _card_shell(
        title=f"Project: {project['name']}",
        template="green",
        elements=[
            _markdown(
                "\n".join(
                    [
                        f"**Agent**\n`{project['backend']}`",
                        f"**Repo Root**\n`{repo_hint}`",
                        f"**Default Workdir**\n`{workdir_hint}`",
                        f"**Workspace Group**\n{group_hint}",
                    ]
                )
            ),
            _button(
                label="Open Workspace",
                intent_value={
                    "intent_key": "workspace.open",
                    "surface": surface,
                    "project_id": project["id"],
                },
                style="primary",
                name=f"open_workspace_{project['id']}",
            ),
            _button(
                label="Configure Agent",
                intent_value={
                    "intent_key": "project.configure_agent",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"configure_agent_{project['id']}",
            ),
            _button(
                label="Configure Repo",
                intent_value={
                    "intent_key": "project.configure_repo",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"configure_repo_{project['id']}",
            ),
            _button(
                label="Configure Default Dir",
                intent_value={
                    "intent_key": "project.configure_default_dir",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"configure_default_dir_{project['id']}",
            ),
            _button(
                label="Manage Dir Presets",
                intent_value={
                    "intent_key": "project.manage_dir_presets",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"manage_dir_presets_{project['id']}",
            ),
            _button(
                label="Back To Projects",
                intent_value={
                    "intent_key": "project.list",
                    "surface": surface,
                },
                name="back_to_projects_button",
            ),
        ],
    )


def _render_project_agent_config(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    return _config_subcard(
        title=f"Agent: {project['name']}",
        summary=f"**Current Agent**\n`{data['current_agent']}`",
        note=data["note"],
        surface=surface,
        project_id=project["id"],
    )


def _render_project_repo_config(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    repo_root = data.get("repo_root") or "未设置"
    return _config_subcard(
        title=f"Repo: {project['name']}",
        summary=f"**Repo Root**\n`{repo_root}`",
        note=data["note"],
        surface=surface,
        project_id=project["id"],
    )


def _render_project_default_dir_config(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    default_workdir = data.get("default_workdir") or "未设置"
    return _config_subcard(
        title=f"Default Dir: {project['name']}",
        summary=f"**Default Workdir**\n`{default_workdir}`",
        note=data["note"],
        surface=surface,
        project_id=project["id"],
    )


def _render_project_dir_presets(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    presets = data.get("presets") or []
    elements: list[dict[str, Any]] = [
        _markdown("**Current Presets**"),
    ]
    if presets:
        elements.extend(_markdown(f"- `{preset}`") for preset in presets)
    else:
        elements.append(_markdown("还没有 preset"))
    elements.extend(
        [
            _input(
                name="workdir",
                placeholder="Add preset path",
            ),
            _markdown(data["note"]),
            _button(
                label="Add Preset",
                intent_value={
                    "intent_key": "project.add_dir_preset",
                    "surface": surface,
                    "project_id": project["id"],
                },
                style="primary",
                name=f"add_dir_preset_{project['id']}",
            ),
            _button(
                label="Back To Project",
                intent_value={
                    "intent_key": "project.open",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"back_to_project_{project['id']}",
            ),
        ]
    )
    return _card_shell(
        title=f"Dir Presets: {project['name']}",
        template="wathet",
        elements=elements,
    )


def _render_workspace_overview(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    latest_status = data.get("latest_task_status") or "none"
    latest_task_id = data.get("latest_task_id")
    active_session = data.get("active_session_summary") or "No active session yet."
    pending_approvals = data.get("pending_approvals") or 0
    current_workdir = data.get("current_workdir") or "未设置"
    workdir_source = data.get("workdir_source") or "unset"
    latest_task_line = f"**latest task status**: `{latest_status}`"
    if latest_task_id:
        latest_task_line = f"**latest task**: `{latest_status}` (`{latest_task_id}`)"
    elements: list[dict[str, Any]] = [
        _markdown(f"**active session**\n{active_session}"),
        _markdown(f"**current workdir**\n`{current_workdir}`"),
        _markdown(f"**workdir source**: `{workdir_source}`"),
        _markdown(latest_task_line),
        _markdown(f"**pending approvals**: `{pending_approvals}`"),
    ]
    if latest_task_id:
        elements.append(
            _button(
                label="Open Latest Task",
                intent_value={
                    "intent_key": "task.open",
                    "surface": surface,
                    "project_id": project["id"],
                    "task_id": latest_task_id,
                },
                name=f"open_latest_task_{project['id']}",
            )
        )
    elements.extend(
        [
            _button(
                label="Run Task",
                intent_value={
                    "intent_key": "task.open_composer",
                    "surface": surface,
                    "project_id": project["id"],
                },
                style="primary",
                name=f"open_task_composer_{project['id']}",
            ),
            _button(
                label="Change Workdir",
                intent_value={
                    "intent_key": "workspace.open_workdir_switcher",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"open_workdir_switcher_{project['id']}",
            ),
            _button(
                label="Refresh",
                intent_value={
                    "intent_key": "workspace.refresh",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"refresh_workspace_{project['id']}",
            ),
            _button(
                label="Back To Project",
                intent_value={
                    "intent_key": "project.open",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"back_to_project_{project['id']}",
            ),
        ]
    )
    return _card_shell(
        title=f"Workspace: {project['name']}",
        template="orange",
        elements=elements,
    )


def _render_workspace_workdir_switcher(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    current_agent = data.get("current_agent") or project["backend"]
    current_workdir = data.get("current_workdir") or "未设置"
    source = data.get("source") or "unset"
    return _card_shell(
        title=f"Workdir: {project['name']}",
        template="indigo",
        elements=[
            _markdown(f"**Current Agent**\n`{current_agent}`"),
            _markdown(f"**Current Workdir**\n`{current_workdir}`"),
            _markdown(f"**Source**: `{source}`"),
            _button(
                label="Use Default",
                intent_value={
                    "intent_key": "workspace.use_default_dir",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"use_default_dir_{project['id']}",
            ),
            _button(
                label="Choose Preset",
                intent_value={
                    "intent_key": "workspace.choose_preset",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"choose_preset_{project['id']}",
            ),
            _button(
                label="Use Recent",
                intent_value={
                    "intent_key": "workspace.use_recent_dir",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"use_recent_dir_{project['id']}",
            ),
            _button(
                label="Enter Path",
                intent_value={
                    "intent_key": "workspace.enter_path",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"enter_path_{project['id']}",
            ),
            _button(
                label="Back To Workspace",
                intent_value={
                    "intent_key": "workspace.open",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"back_to_workspace_{project['id']}",
            ),
        ],
    )


def _render_workspace_use_default_dir(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    default_workdir = data.get("default_workdir") or "未设置"
    return _workspace_subcard(
        title=f"Use Default: {project['name']}",
        summary=f"**Default Workdir**\n`{default_workdir}`",
        note=data["note"],
        surface=surface,
        project_id=project["id"],
    )


def _render_workspace_choose_preset(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    presets = data.get("presets") or []
    elements: list[dict[str, Any]] = [
        _markdown("**Available Presets**"),
    ]
    if presets:
        for index, preset in enumerate(presets):
            elements.append(_markdown(f"- `{preset}`"))
            elements.append(
                _button(
                    label=f"Use Preset {index + 1}",
                    intent_value={
                        "intent_key": "workspace.apply_preset_dir",
                        "surface": surface,
                        "project_id": project["id"],
                        "workdir": preset,
                    },
                    style="primary",
                    name=f"use_preset_{project['id']}_{index}",
                )
            )
    else:
        elements.append(_markdown("还没有 preset"))
    elements.extend(
        [
            _markdown(data["note"]),
            _button(
                label="Back To Workdir",
                intent_value={
                    "intent_key": "workspace.open_workdir_switcher",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"back_to_workdir_{project['id']}",
            ),
        ]
    )
    return _card_shell(
        title=f"Presets: {project['name']}",
        template="blue",
        elements=elements,
    )


def _render_workspace_recent_dirs(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    recent_dirs = data.get("recent_dirs") or []
    recent_text = "\n".join(f"- `{item}`" for item in recent_dirs) if recent_dirs else "还没有 recent dirs"
    return _workspace_subcard(
        title=f"Recent Dirs: {project['name']}",
        summary=f"**Recent Dirs**\n{recent_text}",
        note=data["note"],
        surface=surface,
        project_id=project["id"],
    )


def _render_workspace_enter_path(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    current_workdir = data.get("current_workdir") or ""
    return _card_shell(
        title=f"Enter Path: {project['name']}",
        template="blue",
        elements=[
            _markdown("**Manual Path Entry**\nEnter a workdir path for the current workspace context."),
            _input(
                name="workdir",
                placeholder="Enter workdir path",
                value=current_workdir,
            ),
            _markdown(data["note"]),
            _button(
                label="Apply Path",
                intent_value={
                    "intent_key": "workspace.apply_entered_path",
                    "surface": surface,
                    "project_id": project["id"],
                },
                style="primary",
                name=f"apply_entered_path_{project['id']}",
            ),
            _button(
                label="Back To Workdir",
                intent_value={
                    "intent_key": "workspace.open_workdir_switcher",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"back_to_workdir_{project['id']}",
            ),
        ],
    )


def _render_task_composer(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    current_agent = data.get("current_agent") or project["backend"]
    current_workdir = data.get("current_workdir") or "未设置"
    return _card_shell(
        title=f"Run Task: {project['name']}",
        template="carmine",
        elements=[
            _markdown(f"**Current Agent**\n`{current_agent}`"),
            _markdown(f"**Current Workdir**\n`{current_workdir}`"),
            _input(
                name="prompt",
                placeholder="Describe the task for the agent",
            ),
            _markdown(data["note"]),
            _button(
                label="Submit Task",
                intent_value={
                    "intent_key": "task.submit",
                    "surface": surface,
                    "project_id": project["id"],
                },
                style="primary",
                name=f"submit_task_{project['id']}",
            ),
            _button(
                label="Back To Workspace",
                intent_value={
                    "intent_key": "workspace.open",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"back_to_workspace_{project['id']}",
            ),
        ],
    )


def _render_task_status(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    task = data["task"]
    status = task.get("status") or "unknown"
    prompt = task.get("prompt") or ""
    workdir = task.get("effective_workdir") or "未设置"
    raw_result = task.get("raw_result") or task.get("result_summary") or "No result yet."
    requested_page = _normalize_page(data.get("result_page"))
    result_chunk, page, total_pages = _paginate_text(raw_result, page=requested_page)
    elements: list[dict[str, Any]] = [
        _markdown(f"**Task ID**\n`{task['id']}`"),
        _markdown(f"**Status**\n`{status}`"),
        _markdown(f"**Agent**\n`{task.get('agent_backend') or 'unknown'}`"),
        _markdown(f"**Workdir**\n`{workdir}`"),
        _markdown(f"**Prompt**\n{prompt}"),
    ]

    awaiting = task.get("awaiting_confirmation_reason")
    if awaiting:
        elements.append(_markdown(f"**Awaiting Confirmation**\n{awaiting}"))
        elements.append(
            _button(
                label="Approve",
                intent_value={
                    "intent_key": "task.approve",
                    "surface": surface,
                    "project_id": task.get("project_id") or "",
                    "task_id": task["id"],
                },
                style="primary",
                name=f"approve_task_{task['id']}",
            )
        )
        elements.append(
            _button(
                label="Reject",
                intent_value={
                    "intent_key": "task.reject",
                    "surface": surface,
                    "project_id": task.get("project_id") or "",
                    "task_id": task["id"],
                },
                name=f"reject_task_{task['id']}",
            )
        )
    else:
        elements.append(_markdown("**Result**"))
        if total_pages > 1:
            elements.append(_markdown(f"Page `{page}` / `{total_pages}`"))
        elements.append(_plain_text(result_chunk))
        if total_pages > 1:
            if page > 1:
                elements.append(
                    _button(
                        label="Previous Page",
                        intent_value={
                            "intent_key": "task.open",
                            "surface": surface,
                            "project_id": task.get("project_id") or "",
                            "task_id": task["id"],
                            "page": str(page - 1),
                        },
                        name=f"task_prev_page_{task['id']}_{page}",
                    )
                )
            if page < total_pages:
                elements.append(
                    _button(
                        label="Next Page",
                        intent_value={
                            "intent_key": "task.open",
                            "surface": surface,
                            "project_id": task.get("project_id") or "",
                            "task_id": task["id"],
                            "page": str(page + 1),
                        },
                        name=f"task_next_page_{task['id']}_{page}",
                    )
                )

    if task.get("project_id"):
        elements.append(
            _button(
                label="Back To Workspace",
                intent_value={
                    "intent_key": "workspace.open",
                    "surface": surface,
                    "project_id": task["project_id"],
                },
                name=f"task_back_to_workspace_{task['id']}",
            )
        )

    return _card_shell(
        title=f"Task: {task['id']}",
        template=_task_template_for_status(status),
        elements=elements,
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


def _config_subcard(
    *,
    title: str,
    summary: str,
    note: str,
    surface: str,
    project_id: str,
) -> dict[str, Any]:
    return _card_shell(
        title=title,
        template="wathet",
        elements=[
            _markdown(summary),
            _markdown(note),
            _button(
                label="Back To Project",
                intent_value={
                    "intent_key": "project.open",
                    "surface": surface,
                    "project_id": project_id,
                },
                name=f"back_to_project_{project_id}",
            ),
        ],
    )


def _workspace_subcard(
    *,
    title: str,
    summary: str,
    note: str,
    surface: str,
    project_id: str,
) -> dict[str, Any]:
    return _card_shell(
        title=title,
        template="blue",
        elements=[
            _markdown(summary),
            _markdown(note),
            _button(
                label="Back To Workdir",
                intent_value={
                    "intent_key": "workspace.open_workdir_switcher",
                    "surface": surface,
                    "project_id": project_id,
                },
                name=f"back_to_workdir_{project_id}",
            ),
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


def _plain_text(content: str) -> dict[str, Any]:
    return {
        "tag": "div",
        "text": {
            "tag": "plain_text",
            "content": content,
        },
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


def _input(
    *,
    name: str,
    placeholder: str,
    value: str = "",
) -> dict[str, Any]:
    return {
        "tag": "input",
        "name": name,
        "placeholder": {
            "tag": "plain_text",
            "content": placeholder,
        },
        "value": value,
        "margin": "0px 0px 12px 0px",
    }


def _task_template_for_status(status: str) -> str:
    if status == "waiting_for_confirmation":
        return "orange"
    if status == "completed":
        return "green"
    if status in {"failed", "cancelled"}:
        return "red"
    return "blue"


def _normalize_page(value: Any) -> int:
    try:
        page = int(value)
    except (TypeError, ValueError):
        return 1
    return page if page > 0 else 1


def _paginate_text(
    content: str,
    *,
    page: int,
    page_chars: int = 2400,
) -> tuple[str, int, int]:
    if len(content) <= page_chars:
        return content, 1, 1
    total_pages = (len(content) + page_chars - 1) // page_chars
    normalized_page = min(max(page, 1), total_pages)
    start = (normalized_page - 1) * page_chars
    end = start + page_chars
    return content[start:end], normalized_page, total_pages
