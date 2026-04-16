from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    total_tokens: int | None = None

    def is_empty(self) -> bool:
        return all(
            value is None or value == 0
            for value in (
                self.input_tokens,
                self.cached_input_tokens,
                self.output_tokens,
                self.reasoning_output_tokens,
                self.total_tokens,
            )
        )

    def to_dict(self) -> dict[str, int]:
        data: dict[str, int] = {}
        if self.input_tokens is not None:
            data["input_tokens"] = self.input_tokens
        if self.cached_input_tokens is not None:
            data["cached_input_tokens"] = self.cached_input_tokens
        if self.output_tokens is not None:
            data["output_tokens"] = self.output_tokens
        if self.reasoning_output_tokens is not None:
            data["reasoning_output_tokens"] = self.reasoning_output_tokens
        if self.total_tokens is not None:
            data["total_tokens"] = self.total_tokens
        return data

    @classmethod
    def from_dict(cls, data: object) -> "TokenUsage | None":
        if not isinstance(data, dict):
            return None
        usage = cls(
            input_tokens=_coerce_int(data.get("input_tokens")),
            cached_input_tokens=_coerce_int(data.get("cached_input_tokens")),
            output_tokens=_coerce_int(data.get("output_tokens")),
            reasoning_output_tokens=_coerce_int(data.get("reasoning_output_tokens")),
            total_tokens=_coerce_int(data.get("total_tokens")),
        )
        if usage.is_empty():
            return None
        return usage


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None
