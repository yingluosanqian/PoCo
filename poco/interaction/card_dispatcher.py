from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Protocol

from poco.interaction.card_models import (
    ActionIntent,
    IntentDispatchResult,
    PlatformRenderInstruction,
    RefreshMode,
    RenderTarget,
)


class UnknownActionIntentError(ValueError):
    pass


class IntentHandler(Protocol):
    def handle(self, intent: ActionIntent) -> IntentDispatchResult:
        ...


class IdempotencyStore(Protocol):
    def get(self, request_id: str) -> IntentDispatchResult | None:
        ...

    def save(self, request_id: str, result: IntentDispatchResult) -> None:
        ...


@dataclass(slots=True)
class InMemoryIdempotencyStore:
    _lock: RLock = field(init=False)
    _results: dict[str, IntentDispatchResult] = field(init=False)

    def __post_init__(self) -> None:
        self._lock = RLock()
        self._results: dict[str, IntentDispatchResult] = {}

    def get(self, request_id: str) -> IntentDispatchResult | None:
        with self._lock:
            return self._results.get(request_id)

    def save(self, request_id: str, result: IntentDispatchResult) -> None:
        with self._lock:
            self._results[request_id] = result


class CardActionDispatcher:
    def __init__(
        self,
        handlers: dict[str, IntentHandler],
        *,
        idempotency_store: IdempotencyStore | None = None,
    ) -> None:
        self._handlers = handlers
        self._idempotency_store = idempotency_store or InMemoryIdempotencyStore()

    def dispatch(self, intent: ActionIntent) -> IntentDispatchResult:
        handler = self._handlers.get(intent.intent_key)
        if handler is None:
            raise UnknownActionIntentError(f"Unsupported action intent: {intent.intent_key}")

        if intent.is_write:
            cached = self._idempotency_store.get(intent.request_id)
            if cached is not None:
                return cached

        result = handler.handle(intent)
        if intent.is_write:
            self._idempotency_store.save(intent.request_id, result)
        return result


def build_render_instruction(
    result: IntentDispatchResult,
    *,
    surface,
) -> PlatformRenderInstruction:
    render_target = _render_target_for_mode(result.refresh_mode)
    view_model = result.view_model
    template_key = view_model.view_type if view_model is not None else None
    template_data = view_model.data if view_model is not None else {}
    return PlatformRenderInstruction(
        surface=surface,
        render_target=render_target,
        template_key=template_key,
        template_data=template_data,
        refresh_mode=result.refresh_mode,
        message=result.message,
    )


def _render_target_for_mode(refresh_mode: RefreshMode) -> RenderTarget:
    if refresh_mode == RefreshMode.REPLACE_CURRENT:
        return RenderTarget.CURRENT_CARD
    if refresh_mode == RefreshMode.APPEND_NEW:
        return RenderTarget.NEW_MESSAGE
    return RenderTarget.ACK
