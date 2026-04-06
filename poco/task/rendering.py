from __future__ import annotations

from poco.task.models import Task, TaskStatus


def render_task_text(task: Task, *, headline: str, result_limit: int = 1200) -> str:
    lines = [
        headline,
        f"task_id={task.id}",
        f"agent_backend={task.agent_backend}",
        f"status={task.status.value}",
        f"source={task.source}",
        f"prompt={task.prompt}",
    ]

    if task.awaiting_confirmation_reason:
        lines.append(f"awaiting_confirmation={task.awaiting_confirmation_reason}")

    if task.result_summary:
        lines.append(f"result={_truncate(task.result_summary, limit=result_limit)}")

    if task.events:
        lines.append(f"latest_event={task.events[-1].message}")

    if task.status == TaskStatus.WAITING_FOR_CONFIRMATION:
        lines.append(f"next=/approve {task.id} or /reject {task.id}")

    return "\n".join(lines)


def headline_for_notification(task: Task) -> str:
    if task.status == TaskStatus.WAITING_FOR_CONFIRMATION:
        return "Task waiting for confirmation."
    if task.status == TaskStatus.COMPLETED:
        return "Task completed."
    if task.status == TaskStatus.FAILED:
        return "Task failed."
    if task.status == TaskStatus.CANCELLED:
        return "Task cancelled."
    if task.status == TaskStatus.RUNNING:
        return "Task running."
    return "Task updated."


def _truncate(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."
