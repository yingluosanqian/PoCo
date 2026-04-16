from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompletionGate:
    """Settle-window gate shared by agent backends that have weak terminal signals.

    The gate is armed when a backend sees a "this might be the end" signal
    (e.g. codex `phase=final_answer`). Once armed, the gate requires at least
    one additional loop tick AND a configured settle window to have elapsed
    before it will fire. Any event the backend classifies as renewed activity
    must call `disarm()` to cancel the settle.

    Rules the gate enforces:

    - The iteration that arms the gate never fires settle on the same iteration;
      the caller must still read the next message in the stream so a disarming
      event has a chance to be observed.
    - Re-arming while already armed resets the tick flag so the "one tick
      minimum" guarantee applies to every arm.
    - `tick` is a pure query; callers are expected to call it at the top of
      their event loop, before reading the next message.
    """

    settle_seconds: float
    _armed_at: float | None = None
    _tick_seen: bool = False

    @property
    def is_armed(self) -> bool:
        return self._armed_at is not None

    def arm(self, now: float) -> bool:
        """Arm or re-arm the gate.

        Returns True if the gate was previously idle (caller can log a
        first-arm message), False if the gate was already armed.
        """
        was_idle = self._armed_at is None
        self._armed_at = now
        self._tick_seen = False
        return was_idle

    def disarm(self) -> None:
        self._armed_at = None
        self._tick_seen = False

    def tick(self, now: float) -> tuple[bool, float]:
        """Advance the gate by one loop iteration.

        Returns (should_fire, elapsed_since_arm). `should_fire` is True only
        when the gate is armed, at least one prior tick has been observed,
        and the configured settle window has elapsed.
        """
        if self._armed_at is None:
            return False, 0.0
        if not self._tick_seen:
            self._tick_seen = True
            return False, 0.0
        elapsed = now - self._armed_at
        return elapsed >= self.settle_seconds, elapsed
