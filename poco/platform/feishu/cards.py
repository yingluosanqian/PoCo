from __future__ import annotations

from pathlib import Path
from typing import Any
from poco.interaction.card_models import PlatformRenderInstruction


class FeishuCardRenderer:
    def __init__(self, *, app_base_url: str | None = None) -> None:
        self._app_base_url = app_base_url.rstrip("/") if app_base_url else None

    def render(self, instruction: PlatformRenderInstruction) -> dict[str, Any]:
        if instruction.template_key == "project_home":
            return _render_project_home(
                instruction.template_data,
            )
        if instruction.template_key == "project_create":
            return _render_project_create(
                instruction.template_data,
            )
        if instruction.template_key == "project_manage":
            return _render_project_manage(instruction.template_data)
        if instruction.template_key == "project_list":
            return _render_project_manage(instruction.template_data)
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
                app_base_url=self._app_base_url,
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
        if instruction.template_key == "workspace_choose_model":
            return _render_workspace_choose_model(
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
                app_base_url=self._app_base_url,
            )
        return _render_fallback(instruction.template_key, instruction.template_data)


def _render_project_home(
    data: dict[str, Any],
) -> dict[str, Any]:
    project_count = data.get("project_count", 0)
    return _card_shell(
        title="PoCo Projects",
        template="blue",
        elements=[
            _markdown(f"DM 控制台。当前共有 **{project_count}** 个 project。"),
            _button(
                label="New",
                intent_value={
                    "intent_key": "project.new",
                    "surface": "dm",
                },
                style="primary",
                name="new_project_button",
            ),
            _button(
                label="Manage",
                intent_value={
                    "intent_key": "project.manage",
                    "surface": "dm",
                },
                name="manage_projects_button",
            ),
        ],
    )


def _render_project_create(
    data: dict[str, Any],
) -> dict[str, Any]:
    default_backend = data.get("default_backend") or "codex"
    return _card_shell(
        title="New Project",
        template="blue",
        elements=[
            {
                "tag": "form",
                "name": "project_create_form",
                "elements": [
                    _markdown("**Project Name**"),
                    {
                        "tag": "input",
                        "name": "name",
                        "required": True,
                        "placeholder": {
                            "tag": "plain_text",
                            "content": "Project name",
                        },
                        "margin": "0px 0px 12px 0px",
                    },
                    _markdown(f"**Agent**\n`{default_backend}`"),
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "Create Project + Group",
                        },
                        "type": "primary",
                        "width": "default",
                        "size": "medium",
                        "name": "submit_project_create_button",
                        "form_action_type": "submit",
                        "behaviors": [
                            {
                                "type": "callback",
                                "value": {
                                    "intent_key": "project.create",
                                    "surface": "dm",
                                    "backend": default_backend,
                                },
                            }
                        ],
                        "margin": "0px 0px 12px 0px",
                    },
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "Cancel",
                        },
                        "type": "default",
                        "width": "default",
                        "size": "medium",
                        "name": "cancel_project_create_button",
                        "behaviors": [
                            {
                                "type": "callback",
                                "value": {
                                    "intent_key": "project.home",
                                    "surface": "dm",
                                },
                            }
                        ],
                        "margin": "0px 0px 12px 0px",
                    },
                ],
            }
        ],
    )


def _render_project_manage(data: dict[str, Any]) -> dict[str, Any]:
    projects = data.get("projects", [])
    elements: list[dict[str, Any]] = []

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
                        label="Delete Project",
                        intent_value={
                            "intent_key": "project.delete",
                            "surface": "dm",
                            "project_id": project["id"],
                        },
                        style="danger",
                        name=f"delete_project_{project['id']}",
                    ),
                ]
            )
    elements.append(
        _button(
            label="Back",
            intent_value={
                "intent_key": "project.home",
                "surface": "dm",
            },
            name="back_to_project_home_button",
        )
    )

    return _card_shell(
        title="Manage Projects",
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
    app_base_url: str | None,
) -> dict[str, Any]:
    project = data["project"]
    latest_status = data.get("latest_task_status") or "none"
    latest_task_id = data.get("latest_task_id")
    current_workdir = data.get("current_workdir") or "no working dir"
    current_agent = data.get("current_agent") or project["backend"]
    current_model = data.get("current_model")
    stop_enabled = bool(data.get("stop_enabled"))
    config_locked = latest_status in {"created", "queued", "running", "waiting_for_confirmation"}
    elements: list[dict[str, Any]] = []
    if stop_enabled:
        elements.append(
            _button(
                label="Stop",
                intent_value={
                    "intent_key": "task.stop",
                    "surface": surface,
                    "project_id": project["id"],
                    "task_id": latest_task_id or "",
                },
                name=f"stop_workspace_task_{project['id']}",
            )
        )
    else:
        elements.append(_plain_text("Stop is available only while a task is running."))
    if not config_locked:
        elements.append(
            _two_up(
                _action_button(
                    label="Working Dir",
                    intent_value={
                        "intent_key": "workspace.enter_path",
                        "surface": surface,
                        "project_id": project["id"],
                    },
                    name=f"enter_workdir_path_{project['id']}",
                ),
                _action_button(
                    label="Model",
                    intent_value={
                        "intent_key": "workspace.choose_model",
                        "surface": surface,
                        "project_id": project["id"],
                    },
                    name=f"choose_workspace_model_{project['id']}",
                ),
            )
        )
    return _card_shell(
        title=_workspace_title(
            project_name=project["name"],
            status=latest_status,
            task_id=latest_task_id,
            agent=current_agent,
            workdir=current_workdir,
            model=current_model,
        ),
        template="orange",
        elements=elements,
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
                label="Back To Workspace",
                intent_value={
                    "intent_key": "workspace.open",
                    "surface": surface,
                    "project_id": project["id"],
                },
                name=f"back_to_workspace_{project['id']}",
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
    browse_path = data.get("browse_path") or current_workdir or "no working dir"
    parent_path = data.get("parent_path")
    child_dirs = data.get("child_dirs") or []
    browse_page = data.get("browse_page") or 1
    browse_total_pages = data.get("browse_total_pages") or 1
    error = data.get("error") or ""
    elements: list[dict[str, Any]] = [
        _markdown(
            "\n".join(
                [
                    f"**Current Working Dir**\n`{current_workdir or 'no working dir'}`",
                    f"**Browsing**\n`{browse_path}`",
                ]
            )
        )
    ]
    if error:
        elements.append(_markdown(error))
    nav_buttons: list[dict[str, Any]] = []
    if parent_path:
        nav_buttons.append(
            _button(
                label="Up",
                intent_value={
                    "intent_key": "workspace.enter_path",
                    "surface": surface,
                    "project_id": project["id"],
                    "browse_path": parent_path,
                },
                name=f"browse_parent_{project['id']}",
            )
        )
    nav_buttons.append(
        _button(
            label="Use This Folder",
            intent_value={
                "intent_key": "workspace.apply_entered_path",
                "surface": surface,
                "project_id": project["id"],
                "workdir": browse_path,
            },
            style="primary",
            name=f"use_browsed_path_{project['id']}",
        )
    )
    elements.extend(nav_buttons)
    if child_dirs:
        elements.append(_markdown("**Subfolders**"))
        elements.append(
            {
                "tag": "form",
                "name": f"workspace_browse_form_{project['id']}",
                "elements": [
                    _select_static(
                        name="browse_path",
                        placeholder="Select a subfolder",
                        options=[
                            {
                                "label": Path(child).name or child,
                                "value": child,
                            }
                            for child in child_dirs
                        ],
                        value=child_dirs[0],
                    ),
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "Open Selected",
                        },
                        "type": "default",
                        "width": "default",
                        "size": "medium",
                        "name": f"open_selected_folder_{project['id']}",
                        "form_action_type": "submit",
                        "behaviors": [
                            {
                                "type": "callback",
                                "value": {
                                    "intent_key": "workspace.enter_path",
                                    "surface": surface,
                                    "project_id": project["id"],
                                },
                            }
                        ],
                        "margin": "0px 0px 12px 0px",
                    },
                ],
            }
        )
    else:
        elements.append(_markdown("No subfolders here."))
    if browse_total_pages > 1:
        if browse_page > 1:
            elements.append(
                _button(
                    label="Previous Page",
                    intent_value={
                        "intent_key": "workspace.enter_path",
                        "surface": surface,
                        "project_id": project["id"],
                        "browse_path": browse_path,
                        "page": str(int(browse_page) - 1),
                    },
                    name=f"browse_prev_page_{project['id']}_{browse_page}",
                )
            )
        if browse_page < browse_total_pages:
            elements.append(
                _button(
                    label="Next Page",
                    intent_value={
                        "intent_key": "workspace.enter_path",
                        "surface": surface,
                        "project_id": project["id"],
                        "browse_path": browse_path,
                        "page": str(int(browse_page) + 1),
                    },
                    name=f"browse_next_page_{project['id']}_{browse_page}",
                )
            )
    elements.append(
        {
            "tag": "form",
            "name": f"workspace_enter_path_form_{project['id']}",
            "elements": [
                _markdown("**Manual Path Entry**\nEnter a workdir path directly if browsing is too slow."),
                _input(
                    name="workdir",
                    placeholder="Enter workdir path",
                    value=current_workdir or browse_path,
                ),
                _markdown(data["note"]),
                {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": "Apply Path",
                    },
                    "type": "primary",
                    "width": "default",
                    "size": "medium",
                    "name": f"apply_entered_path_{project['id']}",
                    "form_action_type": "submit",
                    "behaviors": [
                        {
                            "type": "callback",
                            "value": {
                                "intent_key": "workspace.apply_entered_path",
                                "surface": surface,
                                "project_id": project["id"],
                            },
                        }
                    ],
                    "margin": "0px 0px 12px 0px",
                },
            ],
        }
    )
    elements.append(
        _button(
            label="Cancel",
            intent_value={
                "intent_key": "workspace.open",
                "surface": surface,
                "project_id": project["id"],
            },
            name=f"cancel_workspace_enter_path_{project['id']}",
        )
    )
    return _card_shell(
        title=f"Working Dir: {project['name']}",
        template="blue",
        elements=elements,
    )


def _render_workspace_choose_model(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    current_model = data.get("current_model")
    options = data.get("options") or []
    elements: list[dict[str, Any]] = []
    if current_model:
        elements.append(_markdown(f"**Current Model**\n`{current_model}`"))
    elements.append(_markdown(data["note"]))
    for option in options:
        elements.append(
            _button(
                label=option["label"],
                intent_value={
                    "intent_key": "workspace.apply_model",
                    "surface": surface,
                    "project_id": project["id"],
                    "model": option["value"],
                },
                name=f"apply_model_{project['id']}_{option['label'].lower().replace(' ', '_')}",
                style="primary" if option["value"] else "default",
            )
        )
    elements.append(
        _button(
            label="Cancel",
            intent_value={
                "intent_key": "workspace.open",
                "surface": surface,
                "project_id": project["id"],
            },
            name=f"cancel_workspace_choose_model_{project['id']}",
        )
    )
    return _card_shell(
        title=f"Choose Model: {project['name']}",
        template="blue",
        elements=elements,
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
    app_base_url: str | None,
) -> dict[str, Any]:
    task = data["task"]
    status = task.get("status") or "unknown"
    workdir = task.get("effective_workdir") or "no working dir"
    live_output = task.get("live_output") or ""
    raw_result = task.get("raw_result") or task.get("result_summary") or "No result yet."
    requested_page = _normalize_page(data.get("result_page"))
    page = 1
    total_pages = 1
    elements: list[dict[str, Any]] = []

    awaiting = task.get("awaiting_confirmation_reason")
    if awaiting:
        elements.append(_markdown(awaiting))
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
                label="Stop",
                intent_value={
                    "intent_key": "task.stop",
                    "surface": surface,
                    "project_id": task.get("project_id") or "",
                    "task_id": task["id"],
                },
                name=f"stop_task_{task['id']}",
            )
        )
    elif status == "running":
        if live_output:
            live_chunk, page, total_pages = _paginate_text(live_output, page=requested_page)
            elements.append(_markdown(live_chunk))
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
        else:
            elements.append(_markdown("Waiting for agent output..."))
    elif status == "queued":
        elements.append(_markdown("Queued. This task will start after the current task finishes."))
    else:
        result_chunk, page, total_pages = _paginate_text(raw_result, page=requested_page)
        elements.append(_markdown(result_chunk))
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
        config_locked = status in {"created", "queued", "running", "waiting_for_confirmation"}
        if status in {"created", "running"}:
            elements.append(
                _button(
                    label="Stop",
                    intent_value={
                        "intent_key": "task.stop",
                        "surface": surface,
                        "project_id": task["project_id"],
                        "task_id": task["id"],
                    },
                    name=f"stop_task_{task['id']}",
                )
            )
        if not config_locked:
            elements.append(
                _two_up(
                    _action_button(
                        label="Working Dir",
                        intent_value={
                            "intent_key": "workspace.enter_path",
                            "surface": surface,
                            "project_id": task["project_id"],
                        },
                        name=f"task_change_workdir_{task['id']}",
                    ),
                    _action_button(
                        label="Model",
                        intent_value={
                            "intent_key": "workspace.choose_model",
                            "surface": surface,
                            "project_id": task["project_id"],
                        },
                        name=f"task_choose_model_{task['id']}",
                    ),
                )
            )

    return _card_shell(
        title=_task_title(
            task_id=task["id"],
            status=status,
            agent=task.get("effective_model") or task.get("agent_backend") or "unknown",
            workdir=workdir,
            page=page,
            total_pages=total_pages,
        ),
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
                label="Back To Workspace",
                intent_value={
                    "intent_key": "workspace.open",
                    "surface": surface,
                    "project_id": project_id,
                },
                name=f"back_to_workspace_{project_id}",
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


def _as_code_block(content: str) -> str:
    safe = content.replace("```", "'''")
    return f"```text\n{safe}\n```"


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


def _action_button(
    *,
    label: str,
    name: str,
    style: str = "default",
    intent_value: dict[str, str] | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    if url is not None:
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
            "url": url,
            "margin": "0px 0px 12px 0px",
        }
    if intent_value is None:
        raise ValueError("intent_value is required when url is not provided.")
    return _button(
        label=label,
        intent_value=intent_value,
        name=name,
        style=style,
    )


def _locked_or_action_button(
    *,
    locked: bool,
    label: str,
    name: str,
    locked_reason: str,
    style: str = "default",
    intent_value: dict[str, str] | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    if locked:
        return _plain_text(f"{label} · locked")
    return _action_button(
        label=label,
        name=name,
        style=style,
        intent_value=intent_value,
        url=url,
    )


def _two_up(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag": "column_set",
        "horizontal_spacing": "12px",
        "margin": "0px 0px 12px 0px",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "elements": [left],
            },
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "elements": [right],
            },
        ],
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


def _select_static(
    *,
    name: str,
    placeholder: str,
    options: list[dict[str, str]],
    value: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "tag": "select_static",
        "name": name,
        "placeholder": {
            "tag": "plain_text",
            "content": placeholder,
        },
        "options": [
            {
                "text": {
                    "tag": "plain_text",
                    "content": option["label"],
                },
                "value": option["value"],
            }
            for option in options
        ],
        "margin": "0px 0px 12px 0px",
    }
    if value:
        data["value"] = value
    return data


def _task_template_for_status(status: str) -> str:
    if status == "waiting_for_confirmation":
        return "orange"
    if status == "completed":
        return "green"
    if status == "failed":
        return "red"
    if status == "cancelled":
        return "grey"
    return "blue"


def _task_title(
    *,
    task_id: str,
    status: str,
    agent: str,
    workdir: str,
    page: int,
    total_pages: int,
) -> str:
    title = f"[{_task_status_label(status)}] Task: {task_id} ({agent}, {workdir})"
    if total_pages > 1:
        return f"{title} [{page}/{total_pages}]"
    return title


def _workspace_title(
    *,
    project_name: str,
    status: str,
    task_id: str | None,
    agent: str,
    workdir: str,
    model: str | None,
) -> str:
    status_label = _workspace_status_label(status)
    details: list[str] = [agent, workdir]
    if model:
        details.append(model)
    if task_id:
        details.append(task_id)
    return f"[{status_label}] Workspace: {project_name} ({', '.join(details)})"


def _workspace_status_label(status: str) -> str:
    if status == "completed":
        return "Complete"
    if status == "failed":
        return "Failed"
    if status == "running":
        return "Running"
    if status == "cancelled":
        return "Stopped"
    if status == "waiting_for_confirmation":
        return "Waiting"
    return "Idle"


def _task_status_label(status: str) -> str:
    if status == "queued":
        return "Queued"
    if status == "waiting_for_confirmation":
        return "Waiting"
    if status == "completed":
        return "Complete"
    if status == "failed":
        return "Error"
    if status == "cancelled":
        return "Stopped"
    if status == "running":
        return "Running"
    if status == "created":
        return "Created"
    return "Unknown"


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
