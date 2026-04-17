from __future__ import annotations

import json
from typing import Any

from poco.interaction.card_models import PlatformRenderInstruction


class SlackCardRenderer:
    """Render :class:`PlatformRenderInstruction` values into Slack Block Kit.

    Covers the seven tier-B templates PoCo delivers on Slack (phase 2):
    ``task_status``, ``workspace_overview``, ``project_home``,
    ``task_composer``, ``project_create``, ``project_list``, and
    ``project_manage``. Unknown templates fall back to a descriptive block
    so rendering never crashes during rollout.
    """

    def render(self, instruction: PlatformRenderInstruction) -> dict[str, Any]:
        key = instruction.template_key
        data = instruction.template_data
        surface = instruction.surface.value
        if key == "task_status":
            return _render_task_status(data, surface=surface)
        if key == "workspace_overview":
            return _render_workspace_overview(data, surface=surface)
        if key == "project_home":
            return _render_project_home(data)
        if key == "task_composer":
            return _render_task_composer(data, surface=surface)
        if key == "project_create":
            return _render_project_create(data)
        if key in {"project_list", "project_manage"}:
            return _render_project_manage(data)
        return _render_fallback(key, data)


# Block Kit primitives ---------------------------------------------------


def _header(text: str) -> dict[str, Any]:
    return {"type": "header", "text": {"type": "plain_text", "text": _truncate(text, 150)}}


def _section(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": _truncate(text, 3000)}}


def _divider() -> dict[str, Any]:
    return {"type": "divider"}


def _context(text: str) -> dict[str, Any]:
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": _truncate(text, 2000)}],
    }


def _button(
    *,
    label: str,
    action_id: str,
    intent_value: dict[str, Any],
    style: str | None = None,
) -> dict[str, Any]:
    element: dict[str, Any] = {
        "type": "button",
        "text": {"type": "plain_text", "text": _truncate(label, 75)},
        "action_id": _truncate(action_id, 255),
        "value": _truncate(json.dumps(intent_value, ensure_ascii=False), 2000),
    }
    if style in {"primary", "danger"}:
        element["style"] = style
    return element


def _actions(*elements: dict[str, Any]) -> dict[str, Any]:
    # Slack allows up to 25 elements per actions block; cap defensively.
    return {"type": "actions", "elements": list(elements)[:25]}


def _plain_text_input_block(
    *,
    block_id: str,
    label: str,
    action_id: str,
    placeholder: str | None = None,
    initial_value: str | None = None,
    multiline: bool = False,
) -> dict[str, Any]:
    element: dict[str, Any] = {
        "type": "plain_text_input",
        "action_id": action_id,
        "multiline": multiline,
    }
    if placeholder:
        element["placeholder"] = {"type": "plain_text", "text": _truncate(placeholder, 150)}
    if initial_value:
        element["initial_value"] = initial_value
    return {
        "type": "input",
        "block_id": block_id,
        "label": {"type": "plain_text", "text": _truncate(label, 2000)},
        "element": element,
    }


def _static_select_block(
    *,
    block_id: str,
    label: str,
    action_id: str,
    placeholder: str,
    options: list[dict[str, Any]],
    initial_value: str | None = None,
) -> dict[str, Any]:
    slack_options = [
        {
            "text": {"type": "plain_text", "text": _truncate(str(opt.get("label") or opt.get("value") or ""), 75)},
            "value": _truncate(str(opt.get("value") or ""), 75),
        }
        for opt in options
    ]
    element: dict[str, Any] = {
        "type": "static_select",
        "action_id": action_id,
        "placeholder": {"type": "plain_text", "text": _truncate(placeholder, 150)},
        "options": slack_options or [
            {
                "text": {"type": "plain_text", "text": "(no options)"},
                "value": "none",
            }
        ],
    }
    if initial_value:
        for option in slack_options:
            if option["value"] == initial_value:
                element["initial_option"] = option
                break
    return {
        "type": "input",
        "block_id": block_id,
        "label": {"type": "plain_text", "text": _truncate(label, 2000)},
        "element": element,
    }


def _message(*, text: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "text": _truncate(text, 3000),
        "blocks": blocks,
    }


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "\u2026"


# Templates --------------------------------------------------------------


def _render_project_home(data: dict[str, Any]) -> dict[str, Any]:
    project_count = data.get("project_count", 0)
    blocks = [
        _header("PoCo Projects"),
        _section(f"DM console — currently tracking *{project_count}* project(s)."),
        _actions(
            _button(
                label="New",
                action_id="new_project_button",
                intent_value={"intent_key": "project.new", "surface": "dm"},
                style="primary",
            ),
            _button(
                label="Manage",
                action_id="manage_projects_button",
                intent_value={"intent_key": "project.manage", "surface": "dm"},
            ),
        ),
    ]
    return _message(text="PoCo Projects", blocks=blocks)


def _render_project_create(data: dict[str, Any]) -> dict[str, Any]:
    default_backend = data.get("default_backend") or "codex"
    backend_options = data.get("backend_options") or [{"label": "Codex", "value": "codex"}]
    blocks = [
        _header("New Project"),
        _plain_text_input_block(
            block_id="project_create__name",
            label="Project Name",
            action_id="name",
            placeholder="Project name",
        ),
        _static_select_block(
            block_id="project_create__backend",
            label="Agent",
            action_id="backend",
            placeholder="Select an agent",
            options=backend_options,
            initial_value=default_backend,
        ),
        _actions(
            _button(
                label="Create Project + Channel",
                action_id="submit_project_create_button",
                intent_value={"intent_key": "project.create", "surface": "dm"},
                style="primary",
            ),
            _button(
                label="Cancel",
                action_id="cancel_project_create_button",
                intent_value={"intent_key": "project.home", "surface": "dm"},
            ),
        ),
    ]
    return _message(text="New Project", blocks=blocks)


def _render_project_manage(data: dict[str, Any]) -> dict[str, Any]:
    projects = data.get("projects", [])
    blocks: list[dict[str, Any]] = [_header("Manage Projects")]
    if not projects:
        blocks.append(_section("*No projects yet.*"))
    else:
        for project in projects:
            group_hint = project.get("group_chat_id") or "unbound channel"
            summary = "\n".join(
                [
                    f"*{project['name']}*",
                    f"• backend: `{project['backend']}`",
                    f"• channel: `{group_hint}`",
                    f"• status: `{'archived' if project.get('archived') else 'active'}`",
                ]
            )
            blocks.append(_section(summary))
            blocks.append(
                _actions(
                    _button(
                        label="Delete Project",
                        action_id=f"delete_project_{project['id']}",
                        intent_value={
                            "intent_key": "project.delete",
                            "surface": "dm",
                            "project_id": project["id"],
                        },
                        style="danger",
                    )
                )
            )
            blocks.append(_divider())
    blocks.append(
        _actions(
            _button(
                label="Back",
                action_id="back_to_project_home_button",
                intent_value={"intent_key": "project.home", "surface": "dm"},
            )
        )
    )
    return _message(text="Manage Projects", blocks=blocks)


def _render_task_composer(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    current_agent = data.get("current_agent") or project["backend"]
    current_workdir = data.get("current_workdir") or "not set"
    blocks = [
        _header(f"Run Task: {project['name']}"),
        _section(f"*Agent*: `{current_agent}`\n*Workdir*: `{current_workdir}`"),
        _plain_text_input_block(
            block_id=f"task_composer__prompt__{project['id']}",
            label="Prompt",
            action_id="prompt",
            placeholder="Describe the task for the agent",
            multiline=True,
        ),
        _section(data.get("note", "")),
        _actions(
            _button(
                label="Submit Task",
                action_id=f"submit_task_{project['id']}",
                intent_value={
                    "intent_key": "task.submit",
                    "surface": surface,
                    "project_id": project["id"],
                },
                style="primary",
            ),
            _button(
                label="Back To Workspace",
                action_id=f"back_to_workspace_{project['id']}",
                intent_value={
                    "intent_key": "workspace.open",
                    "surface": surface,
                    "project_id": project["id"],
                },
            ),
        ),
    ]
    return _message(text=f"Run Task: {project['name']}", blocks=blocks)


def _render_workspace_overview(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    project = data["project"]
    latest_status = data.get("latest_task_status") or "none"
    latest_task_id = data.get("latest_task_id")
    current_workdir = data.get("current_workdir") or "no working dir"
    current_agent = data.get("current_agent") or project["backend"]
    current_model = data.get("current_model")
    queue_count = int(data.get("queue_count") or 0)
    stop_enabled = bool(data.get("stop_enabled"))
    config_locked = latest_status in {"created", "queued", "running", "waiting_for_confirmation"}

    detail_bits = [f"`{current_agent}`", f"`{current_workdir}`"]
    if current_model:
        detail_bits.append(f"model `{current_model}`")
    if latest_task_id:
        detail_bits.append(f"task `{latest_task_id}`")
    if queue_count > 0:
        detail_bits.append(f"queue {queue_count}")
    summary = (
        f"*Workspace — {project['name']}*\n"
        f"Status: `{latest_status}`\n"
        f"{' · '.join(detail_bits)}"
    )

    blocks: list[dict[str, Any]] = [_section(summary)]
    action_elements: list[dict[str, Any]] = []
    if stop_enabled:
        action_elements.append(
            _button(
                label="Stop",
                action_id=f"stop_workspace_task_{project['id']}",
                intent_value={
                    "intent_key": "task.stop",
                    "surface": surface,
                    "project_id": project["id"],
                    "task_id": latest_task_id or "",
                },
            )
        )
    else:
        blocks.append(_context("Stop is available only while a task is running."))
    if not config_locked:
        action_elements.extend(
            [
                _button(
                    label="Working Dir",
                    action_id=f"enter_workdir_path_{project['id']}",
                    intent_value={
                        "intent_key": "workspace.enter_path",
                        "surface": surface,
                        "project_id": project["id"],
                    },
                ),
                _button(
                    label="Agent",
                    action_id=f"choose_workspace_agent_{project['id']}",
                    intent_value={
                        "intent_key": "workspace.choose_agent",
                        "surface": surface,
                        "project_id": project["id"],
                    },
                ),
                _button(
                    label="Session",
                    action_id=f"choose_workspace_session_{project['id']}",
                    intent_value={
                        "intent_key": "workspace.choose_session",
                        "surface": surface,
                        "project_id": project["id"],
                    },
                ),
            ]
        )
    if action_elements:
        blocks.append(_actions(*action_elements))
    return _message(text=f"Workspace: {project['name']}", blocks=blocks)


def _render_task_status(
    data: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    task = data["task"]
    status = task.get("status") or "unknown"
    agent_backend = task.get("agent_backend") or "unknown"
    workdir = task.get("effective_workdir") or "no working dir"
    model = task.get("effective_model") or agent_backend
    project_id = task.get("project_id") or ""
    task_id = task["id"]
    awaiting = task.get("awaiting_confirmation_reason")
    live_output = task.get("live_output") or ""
    raw_result = _task_display_result(task)
    queue_position = data.get("queue_position")
    blocking_task_id = data.get("blocking_task_id")
    blocking_task_status = data.get("blocking_task_status")

    activity_hint = task.get("activity_hint")
    status_display = status
    if activity_hint and status == "running":
        status_display = f"{status} · {activity_hint}"
    blocks: list[dict[str, Any]] = [
        _section(
            f"*Task `{task_id}`* — status `{status_display}`\n"
            f"Agent: `{model}` · Workdir: `{workdir}`"
        ),
    ]

    action_elements: list[dict[str, Any]] = []

    if awaiting:
        blocks.append(_section(str(awaiting)))
        action_elements.extend(
            [
                _button(
                    label="Approve",
                    action_id=f"approve_task_{task_id}",
                    intent_value={
                        "intent_key": "task.approve",
                        "surface": surface,
                        "project_id": project_id,
                        "task_id": task_id,
                    },
                    style="primary",
                ),
                _button(
                    label="Stop",
                    action_id=f"stop_task_{task_id}",
                    intent_value={
                        "intent_key": "task.stop",
                        "surface": surface,
                        "project_id": project_id,
                        "task_id": task_id,
                    },
                ),
            ]
        )
    elif status == "running":
        body = live_output or "Waiting for agent output…"
        blocks.append(_section(f"```\n{_truncate(body, 2800)}\n```"))
    elif status == "queued":
        parts: list[str] = []
        if queue_position:
            parts.append(f"Queue position: *{queue_position}*")
        if blocking_task_id:
            parts.append(f"Waiting for task `{blocking_task_id}` to finish.")
        if not parts:
            parts.append("Queued. Waiting for the current task to finish.")
        blocks.append(_section("\n".join(parts)))
        can_steer = bool(
            project_id
            and blocking_task_id
            and blocking_task_status == "running"
            and agent_backend in {"codex", "claude_code", "cursor_agent"}
            and str(task.get("prompt") or "").strip()
        )
        if can_steer:
            action_elements.append(
                _button(
                    label="Steer Current Task",
                    action_id=f"steer_queued_task_{task_id}",
                    intent_value={
                        "intent_key": "task.steer_queue",
                        "surface": surface,
                        "project_id": project_id,
                        "task_id": task_id,
                    },
                    style="primary",
                )
            )
    else:
        blocks.append(_section(f"```\n{_truncate(raw_result, 2800)}\n```"))

    token_line = _token_usage_line(task)
    if token_line:
        blocks.append(_context(token_line))

    can_continue = bool(
        project_id
        and task.get("backend_session_id")
        and status in {"failed", "cancelled"}
        and raw_result and raw_result != "No result yet."
    )
    config_locked = status in {"created", "queued", "running", "waiting_for_confirmation"}

    if project_id:
        if status in {"created", "running"} and not awaiting:
            action_elements.append(
                _button(
                    label="Stop",
                    action_id=f"stop_task_{task_id}",
                    intent_value={
                        "intent_key": "task.stop",
                        "surface": surface,
                        "project_id": project_id,
                        "task_id": task_id,
                    },
                )
            )
        if can_continue:
            action_elements.append(
                _button(
                    label="Continue",
                    action_id=f"continue_task_{task_id}",
                    intent_value={
                        "intent_key": "task.continue",
                        "surface": surface,
                        "project_id": project_id,
                        "task_id": task_id,
                    },
                    style="primary",
                )
            )
        if not config_locked:
            action_elements.extend(
                [
                    _button(
                        label="Working Dir",
                        action_id=f"task_change_workdir_{task_id}",
                        intent_value={
                            "intent_key": "workspace.enter_path",
                            "surface": surface,
                            "project_id": project_id,
                        },
                    ),
                    _button(
                        label="Agent",
                        action_id=f"task_choose_agent_{task_id}",
                        intent_value={
                            "intent_key": "workspace.choose_agent",
                            "surface": surface,
                            "project_id": project_id,
                        },
                    ),
                ]
            )

    if action_elements:
        blocks.append(_actions(*action_elements))

    return _message(text=f"Task {task_id}: {status}", blocks=blocks)


def _render_fallback(template_key: str | None, data: dict[str, Any]) -> dict[str, Any]:
    key = template_key or "unknown"
    blocks = [
        _header(key),
        _section(f"Unrendered template `{key}`."),
        _section(f"```\n{_truncate(json.dumps(data, ensure_ascii=False)[:2500], 2800)}\n```"),
    ]
    return _message(text=key, blocks=blocks)


# Task helpers (kept local to avoid coupling Slack to Feishu internals) --


def _task_display_result(task: dict[str, Any]) -> str:
    raw_result = task.get("raw_result") or task.get("result_summary")
    if isinstance(raw_result, str) and raw_result.strip():
        return raw_result
    events = task.get("events")
    if isinstance(events, list):
        for event in reversed(events):
            if not isinstance(event, dict):
                continue
            kind = str(event.get("kind") or "").strip()
            message = str(event.get("message") or "").strip()
            if not message:
                continue
            if kind in {"task_failed", "task_cancelled", "confirmation_rejected"}:
                return message
    return "No result yet."


def _token_usage_line(task: dict[str, Any]) -> str | None:
    total = task.get("total_token_usage") or task.get("last_token_usage")
    if not isinstance(total, dict):
        return None
    inp = total.get("input_tokens") or 0
    out = total.get("output_tokens") or 0
    cached = total.get("cached_input_tokens") or 0
    reasoning = total.get("reasoning_output_tokens") or 0
    if not any((inp, out, cached, reasoning)):
        return None
    bits = [f"in {inp}", f"out {out}"]
    if cached:
        bits.append(f"cached {cached}")
    if reasoning:
        bits.append(f"reasoning {reasoning}")
    return "Tokens — " + ", ".join(bits)
