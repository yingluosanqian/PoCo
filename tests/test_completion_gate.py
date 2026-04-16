from __future__ import annotations

import unittest

from poco.agent.completion_gate import CompletionGate


class CompletionGateTest(unittest.TestCase):
    def test_new_gate_is_idle(self) -> None:
        gate = CompletionGate(settle_seconds=1.0)
        self.assertFalse(gate.is_armed)
        should_fire, elapsed = gate.tick(now=0.0)
        self.assertFalse(should_fire)
        self.assertEqual(elapsed, 0.0)

    def test_first_arm_returns_true(self) -> None:
        gate = CompletionGate(settle_seconds=1.0)
        self.assertTrue(gate.arm(now=10.0))
        self.assertTrue(gate.is_armed)

    def test_subsequent_arm_returns_false(self) -> None:
        gate = CompletionGate(settle_seconds=1.0)
        gate.arm(now=10.0)
        self.assertFalse(gate.arm(now=10.5))
        self.assertTrue(gate.is_armed)

    def test_arm_always_resets_tick_seen(self) -> None:
        gate = CompletionGate(settle_seconds=0.0)
        gate.arm(now=10.0)
        # First tick consumes the mandatory tick slot.
        self.assertEqual(gate.tick(now=10.0), (False, 0.0))
        # Re-arming must restore the one-tick guarantee even with 0 settle.
        gate.arm(now=20.0)
        self.assertEqual(gate.tick(now=20.0), (False, 0.0))

    def test_disarm_clears_state(self) -> None:
        gate = CompletionGate(settle_seconds=1.0)
        gate.arm(now=10.0)
        gate.disarm()
        self.assertFalse(gate.is_armed)
        self.assertEqual(gate.tick(now=100.0), (False, 0.0))

    def test_disarm_is_idempotent(self) -> None:
        gate = CompletionGate(settle_seconds=1.0)
        gate.disarm()
        gate.disarm()
        self.assertFalse(gate.is_armed)

    def test_first_tick_after_arm_never_fires(self) -> None:
        gate = CompletionGate(settle_seconds=0.0)
        gate.arm(now=10.0)
        # Even with zero settle, the iteration that armed the gate cannot fire.
        self.assertEqual(gate.tick(now=100.0), (False, 0.0))

    def test_fires_after_tick_and_settle(self) -> None:
        gate = CompletionGate(settle_seconds=1.0)
        gate.arm(now=10.0)
        self.assertEqual(gate.tick(now=10.5), (False, 0.0))
        should_fire, elapsed = gate.tick(now=11.5)
        self.assertTrue(should_fire)
        self.assertAlmostEqual(elapsed, 1.5)

    def test_does_not_fire_before_settle_elapses(self) -> None:
        gate = CompletionGate(settle_seconds=1.0)
        gate.arm(now=10.0)
        gate.tick(now=10.2)
        should_fire, elapsed = gate.tick(now=10.5)
        self.assertFalse(should_fire)
        self.assertAlmostEqual(elapsed, 0.5)

    def test_disarm_between_arm_and_fire_prevents_firing(self) -> None:
        gate = CompletionGate(settle_seconds=0.5)
        gate.arm(now=10.0)
        gate.tick(now=10.1)
        gate.disarm()
        # Even though enough time has passed, disarm blocks settle.
        should_fire, _ = gate.tick(now=100.0)
        self.assertFalse(should_fire)

    def test_re_arm_after_fire_requires_fresh_tick(self) -> None:
        gate = CompletionGate(settle_seconds=0.0)
        gate.arm(now=10.0)
        gate.tick(now=10.0)
        should_fire, _ = gate.tick(now=10.0)
        self.assertTrue(should_fire)
        # Caller now re-arms for a new final-answer signal.
        gate.arm(now=20.0)
        self.assertEqual(gate.tick(now=20.0), (False, 0.0))
        should_fire, _ = gate.tick(now=20.0)
        self.assertTrue(should_fire)


if __name__ == "__main__":
    unittest.main()
