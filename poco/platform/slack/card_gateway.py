from __future__ import annotations

import json
from typing import Any

from poco.interaction.card_dispatcher import (
    CardActionDispatcher,
    build_render_instruction,
)
from poco.interaction.card_handlers import build_dm_project_list_result
from poco.interaction.card_models import ActionIntent, DispatchStatus, Surface
from poco.platform.slack.cards import SlackCardRenderer
from poco.platform.slack.debug import SlackDebugRecorder
from poco.project.controller import ProjectController


class SlackCardActionGateway:
    """Translate Slack ``block_actions`` payloads into :class:`ActionIntent`.

    Each PoCo Block Kit button embeds a JSON blob (the ``value`` field) that
    mirrors the Feishu card action payload: ``intent_key``, ``surface``,
    plus optional resource ids. The intent is dispatched through the shared
    :class:`CardActionDispatcher` and the resulting render instruction is
    materialized into a Slack Block Kit card for the caller to send (or
    patch via ``chat.update``).
    """

    def __init__(
        self,
        *,
        dispatcher: CardActionDispatcher,
        renderer: SlackCardRenderer,
        project_controller: ProjectController,
        debug_recorder: SlackDebugRecorder | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._renderer = renderer
        self._project_controller = project_controller
        self._debug_recorder = debug_recorder

    def render_dm_project_list(self, *, actor_id: str | None = None) -> dict[str, Any]:
        result = build_dm_project_list_result(
            self._project_controller,
            actor_id=actor_id,
        )
        instruction = build_render_instruction(result, surface=Surface.DM)
        return {
            "instruction": _instruction_to_dict(instruction),
            "card": self._renderer.render(instruction),
        }

    def handle_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        intent = _payload_to_action_intent(payload)
        result = self._dispatcher.dispatch(intent)
        instruction = build_render_instruction(result, surface=intent.surface)
        rendered_card = None
        if instruction.template_key is not None:
            rendered_card = self._renderer.render(instruction)

        if self._debug_recorder is not None:
            channel = (payload.get("channel") or {}).get("id")
            self._debug_recorder.record_inbound(
                user_id=intent.actor_id,
                text=intent.intent_key,
                channel=channel,
                surface=intent.surface.value,
                payload=payload,
            )

        response: dict[str, Any] = {
            "status": result.status.value,
            "message": result.message or "Action processed.",
            "instruction": _instruction_to_dict(instruction),
        }
        if rendered_card is not None:
            response["card"] = rendered_card
        # Slack interactive responses typically target the originating message
        # (chat.update via response_url). Surface the address so callers can
        # decide whether to replace in place or post a new message.
        container = payload.get("container") or {}
        channel = (payload.get("channel") or {}).get("id") or container.get("channel_id")
        message_ts = container.get("message_ts") or (payload.get("message") or {}).get("ts")
        if channel:
            response["channel"] = channel
        if message_ts:
            response["message_ts"] = message_ts
        response["response_url"] = payload.get("response_url")
        return response


def _payload_to_action_intent(payload: dict[str, Any]) -> ActionIntent:
    actions = payload.get("actions") or []
    action = actions[0] if actions else {}
    value = _decode_button_value(action.get("value"))

    state_values = _flatten_state_values(payload.get("state", {}))
    merged_payload: dict[str, Any] = {
        k: v for k, v in value.items() if k not in _reserved_value_keys()
    }
    merged_payload.update(state_values)

    source_surface = str(value.get("surface", "dm")).strip().lower()
    surface = Surface.GROUP if source_surface == Surface.GROUP.value else Surface.DM

    user = payload.get("user") or {}
    actor_id = str(user.get("id") or user.get("username") or "anonymous")
    container = payload.get("container") or {}
    message_id = (
        container.get("message_ts")
        or (payload.get("message") or {}).get("ts")
        or ""
    )

    return ActionIntent(
        intent_key=_normalize_intent_key(str(value.get("intent_key", "")).strip()),
        surface=surface,
        actor_id=actor_id,
        source_message_id=str(message_id),
        request_id=_request_id_for_action(
            payload=payload,
            actor_id=actor_id,
            value=value,
            action=action,
        ),
        project_id=_optional_string(value.get("project_id")),
        session_id=_optional_string(value.get("session_id")),
        task_id=_optional_string(value.get("task_id")),
        payload=merged_payload,
    )


def _decode_button_value(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, dict):
            return decoded
    return {}


def _flatten_state_values(state: dict[str, Any]) -> dict[str, Any]:
    """Collapse Slack's nested ``state.values`` shape into a flat dict.

    Slack returns
    ``state.values[block_id][action_id] = {"type": ..., "value": "..."}``
    — we only care about the effective user-entered values, keyed by the
    innermost ``action_id`` so handlers can treat them like Feishu's
    ``form_value``.
    """

    flat: dict[str, Any] = {}
    values = state.get("values") if isinstance(state, dict) else None
    if not isinstance(values, dict):
        return flat
    for block in values.values():
        if not isinstance(block, dict):
            continue
        for action_id, field in block.items():
            if not isinstance(field, dict):
                continue
            field_type = field.get("type")
            if field_type == "plain_text_input":
                flat[action_id] = field.get("value") or ""
            elif field_type == "static_select":
                selected = field.get("selected_option") or {}
                flat[action_id] = selected.get("value") or ""
            elif "selected_option" in field:
                selected = field.get("selected_option") or {}
                flat[action_id] = selected.get("value") or ""
            elif "value" in field:
                flat[action_id] = field.get("value")
    return flat


def _reserved_value_keys() -> set[str]:
    return {
        "intent_key",
        "surface",
        "project_id",
        "session_id",
        "task_id",
        "request_id",
    }


def _instruction_to_dict(instruction) -> dict[str, Any]:
    return {
        "surface": instruction.surface.value,
        "render_target": instruction.render_target.value,
        "template_key": instruction.template_key,
        "template_data": instruction.template_data,
        "refresh_mode": instruction.refresh_mode.value,
        "message": instruction.message,
    }


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _request_id_for_action(
    *,
    payload: dict[str, Any],
    actor_id: str,
    value: dict[str, Any],
    action: dict[str, Any],
) -> str:
    explicit = _optional_string(value.get("request_id"))
    if explicit is not None:
        return explicit

    trigger_id = _optional_string(payload.get("trigger_id"))
    if trigger_id is not None:
        return trigger_id

    action_ts = _optional_string(action.get("action_ts"))
    container = payload.get("container") or {}
    parts = [
        _optional_string(container.get("message_ts")) or "unknown_message",
        actor_id or "anonymous",
        _optional_string(value.get("intent_key")) or "unknown_intent",
        _optional_string(action.get("action_id")) or "unnamed_action",
        action_ts or "",
        json.dumps(value, ensure_ascii=False, sort_keys=True),
    ]
    return "::".join(parts)


def _normalize_intent_key(intent_key: str) -> str:
    legacy_intent_keys = {
        "workspace.choose_model": "workspace.choose_agent",
        "workspace.apply_model": "workspace.apply_agent",
    }
    return legacy_intent_keys.get(intent_key, intent_key)
