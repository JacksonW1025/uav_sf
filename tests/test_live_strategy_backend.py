"""Tests for the shared live strategy decision and action preconditions."""

from __future__ import annotations

import unittest

from scripts.runtime.live_strategy_backend import create_live_decision
from scripts.runtime.strategy_action_executor import observed_preconditions


class LiveStrategyBackendTests(unittest.TestCase):
    def test_random_schedule_is_seeded_and_bounded(self) -> None:
        values = [
            create_live_decision(
                strategy="bounded_random_timing",
                seed=71,
                timing_bounds_ns={"setpoint_stall": [3_500_000_000, 6_500_000_000]},
                official_offset_ns=5_000_000_000,
                covered_boundaries=set(),
            )
            for _ in range(2)
        ]
        self.assertEqual(values[0], values[1])
        self.assertTrue(3_500_000_000 <= values[0]["planned_offset_ns"] <= 6_500_000_000)

    def test_state_aware_uses_observed_coverage_feedback(self) -> None:
        first = create_live_decision(
            strategy="state_aware",
            seed=72,
            timing_bounds_ns={"setpoint_stall": [3_500_000_000, 6_500_000_000]},
            official_offset_ns=5_000_000_000,
            covered_boundaries=set(),
        )
        second = create_live_decision(
            strategy="state_aware",
            seed=73,
            timing_bounds_ns={"setpoint_stall": [3_500_000_000, 6_500_000_000]},
            official_offset_ns=5_000_000_000,
            covered_boundaries={first["selected_boundary"]},
        )
        self.assertEqual(first["selected_boundary"], "stall_offset:boundary")
        self.assertNotEqual(first["selected_boundary"], second["selected_boundary"])

    def test_action_requires_both_live_preconditions(self) -> None:
        active = {"kind": "offboard_observed_active", "received_monotonic_ns": 10}
        motion = {"kind": "motion_phase_entered", "received_monotonic_ns": 20}
        self.assertEqual(observed_preconditions([active]), (10, None))
        self.assertEqual(observed_preconditions([motion, active]), (10, 20))


if __name__ == "__main__":
    unittest.main()
