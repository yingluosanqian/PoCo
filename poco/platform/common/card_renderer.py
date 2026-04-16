from __future__ import annotations

from typing import Any, Protocol

from poco.interaction.card_models import PlatformRenderInstruction


class CardRenderer(Protocol):
    """Protocol for per-platform card/template renderers.

    Given a platform-neutral ``PlatformRenderInstruction`` (the output of
    ``build_render_instruction``), the renderer produces the wire-format
    payload expected by that platform's messaging client (Feishu 2.0 card
    JSON, Slack Block Kit, etc.).
    """

    def render(self, instruction: PlatformRenderInstruction) -> dict[str, Any]: ...
