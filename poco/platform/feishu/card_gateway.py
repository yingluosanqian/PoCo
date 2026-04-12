from __future__ import annotations

import json
from typing import Any

from poco.interaction.card_dispatcher import CardActionDispatcher, build_render_instruction
from poco.interaction.card_handlers import build_dm_project_list_result
from poco.interaction.card_models import ActionIntent, DispatchStatus, Surface
from poco.platform.feishu.cards import FeishuCardRenderer
from poco.platform.feishu.debug import FeishuDebugRecorder
from poco.platform.feishu.verification import FeishuRequestVerifier
from poco.project.controller import ProjectController


class FeishuCardActionGateway:
    def __init__(
        self,
        *,
        dispatcher: CardActionDispatcher,
        renderer: FeishuCardRenderer,
        project_controller: ProjectController,
        request_verifier: FeishuRequestVerifier | None = None,
        debug_recorder: FeishuDebugRecorder | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._renderer = renderer
        self._project_controller = project_controller
        self._request_verifier = request_verifier
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

    def handle_action(
        self,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        raw_body: bytes | None = None,
    ) -> dict[str, Any]:
        request_body = raw_body or json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if self._request_verifier is not None:
            verify_payload = _verification_payload(payload)
            self._request_verifier.verify(
                payload=verify_payload,
                headers=headers or {},
                raw_body=request_body,
            )

        intent = _payload_to_action_intent(payload)
        result = self._dispatcher.dispatch(intent)
        instruction = build_render_instruction(result, surface=intent.surface)
        rendered_card = None
        if instruction.template_key is not None:
            rendered_card = self._renderer.render(instruction)

        if self._debug_recorder is not None:
            self._debug_recorder.record_inbound(
                user_id=intent.actor_id,
                text=intent.intent_key,
                reply_receive_id=intent.source_message_id,
                reply_receive_id_type=intent.surface.value,
                payload=payload,
            )

        response: dict[str, Any] = {
            "toast": {
                "type": _toast_type_for_status(result.status),
                "content": result.message or "Action processed.",
            },
            "instruction": _instruction_to_dict(instruction),
        }
        if rendered_card is not None:
            response["card"] = {
                "type": "raw",
                "data": rendered_card,
            }
        return response


def _payload_to_action_intent(payload: dict[str, Any]) -> ActionIntent:
    event = payload.get("event", {})
    action = event.get("action", {})
    value = action.get("value", {})
    form_value = action.get("form_value", {})
    source_surface = str(value.get("surface", "dm")).strip().lower()
    surface = Surface.GROUP if source_surface == Surface.GROUP.value else Surface.DM
    merged_payload = {k: v for k, v in value.items() if k not in _reserved_value_keys()}
    if isinstance(form_value, dict):
        merged_payload.update(form_value)
    input_value = action.get("input_value")
    if input_value is not None:
        merged_payload["input_value"] = input_value

    operator = event.get("operator", {})
    context = event.get("context", {})
    actor_id = str(operator.get("open_id") or operator.get("user_id") or "anonymous")
    return ActionIntent(
        intent_key=_normalize_intent_key(str(value.get("intent_key", "")).strip()),
        surface=surface,
        actor_id=actor_id,
        source_message_id=str(context.get("open_message_id") or ""),
        request_id=_request_id_for_action(
            payload=payload,
            actor_id=actor_id,
            value=value,
            action=action,
            context=context,
        ),
        project_id=_optional_string(value.get("project_id")),
        session_id=_optional_string(value.get("session_id")),
        task_id=_optional_string(value.get("task_id")),
        payload=merged_payload,
    )


def _verification_payload(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("event", {})
    token = event.get("token")
    if token is None:
        return payload
    normalized = dict(payload)
    normalized["token"] = token
    return normalized


def _reserved_value_keys() -> set[str]:
    return {
        "intent_key",
        "surface",
        "project_id",
        "session_id",
        "task_id",
        "request_id",
    }


def _toast_type_for_status(status: DispatchStatus) -> str:
    if status == DispatchStatus.OK:
        return "success"
    if status == DispatchStatus.REJECTED:
        return "warning"
    return "error"


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
    context: dict[str, Any],
) -> str:
    explicit = _optional_string(value.get("request_id"))
    if explicit is not None:
        return explicit

    event_id = _optional_string(payload.get("event_id"))
    if event_id is not None:
        return event_id

    header_event_id = _optional_string((payload.get("header") or {}).get("event_id"))
    if header_event_id is not None:
        return header_event_id

    parts = [
        _optional_string(context.get("open_message_id")) or "unknown_message",
        actor_id or "anonymous",
        _optional_string(value.get("intent_key")) or "unknown_intent",
        _optional_string(action.get("name")) or "unnamed_action",
        json.dumps(value, ensure_ascii=False, sort_keys=True),
    ]
    return "::".join(parts)


def _normalize_intent_key(intent_key: str) -> str:
    legacy_intent_keys = {
        "workspace.choose_model": "workspace.choose_agent",
        "workspace.apply_model": "workspace.apply_agent",
    }
    return legacy_intent_keys.get(intent_key, intent_key)
