"""Tests for registered Stage A2 physical metric definitions."""

from __future__ import annotations

import unittest

from scripts.analysis.stage_a2_physical import compute_metrics


class StageA2PhysicalTests(unittest.TestCase):
    def test_stall_freezes_reference_and_separates_recovery(self) -> None:
        positions = []
        for second in range(10):
            positions.append(
                {
                    "timestamp_ns": second * 1_000_000_000,
                    "x": min(3.0, float(second)),
                    "y": 0.1,
                    "z": -3.0 + max(0.0, second - 8.0),
                    "vx": 1.0 if second < 3 else 0.0,
                    "vy": 0.0,
                }
            )
        result = compute_metrics(
            positions=positions,
            activation_ns=0,
            completion_ns=6_000_000_000,
            successor_ns=6_000_000_000,
            landed_ns=9_000_000_000,
            settle_s=0.0,
            speed_m_s=1.0,
            distance_m=5.0,
            stall_after_s=3.0,
            fault_mode="setpoint_stall",
        )
        self.assertEqual(result["completion_target_x_m"], 3.0)
        self.assertEqual(result["completion_actual_x_m"], 3.0)
        self.assertEqual(result["exposure_duration_s"], 3.0)
        self.assertEqual(result["exposure_distance_m"], 0.0)
        self.assertEqual(result["cross_track_error_m"], 0.1)
        self.assertGreater(result["recovery_distance_m"], 0.0)

    def test_nominal_has_zero_exposure(self) -> None:
        positions = [
            {
                "timestamp_ns": second * 1_000_000_000,
                "x": float(second),
                "y": 0.0,
                "z": -3.0,
                "vx": 1.0,
                "vy": 0.0,
            }
            for second in range(6)
        ]
        result = compute_metrics(
            positions=positions,
            activation_ns=0,
            completion_ns=4_000_000_000,
            successor_ns=4_000_000_000,
            landed_ns=5_000_000_000,
            settle_s=0.0,
            speed_m_s=1.0,
            distance_m=4.0,
            stall_after_s=3.0,
            fault_mode="normal",
        )
        self.assertEqual(result["along_track_lag_m"], 0.0)
        self.assertEqual(result["exposure_duration_s"], 0.0)
        self.assertEqual(result["exposure_distance_m"], 0.0)


if __name__ == "__main__":
    unittest.main()
