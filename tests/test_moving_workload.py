from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

from scripts.runtime.moving_workload import progress_from_origin, straight_line_target
from scripts.runtime.process_attempt import _physical_execution_contract


class MovingWorkloadTests(unittest.TestCase):
    def test_target_holds_then_moves_and_saturates(self) -> None:
        values = [straight_line_target(t, settle_s=1.0, speed_m_s=0.75, distance_m=3.5) for t in (0.0, 1.0, 3.0, 10.0)]
        self.assertEqual(values, [0.0, 0.0, 1.5, 3.5])

    def test_reverse_motion_does_not_satisfy_progress(self) -> None:
        self.assertEqual(progress_from_origin(-1.0, 0.0), 0.0)

    def test_physical_contract_requires_takeoff_before_tested_transition(self) -> None:
        telemetry = [
            {"kind": "vehicle_local_position", "z": -0.6, "z_valid": True, "received_monotonic_ns": 0},
            {"kind": "vehicle_land_detected", "landed": False, "received_monotonic_ns": 10_000_000},
            {"kind": "vehicle_local_position", "z": -0.7, "z_valid": True, "received_monotonic_ns": 300_000_000},
            {"kind": "vehicle_land_detected", "landed": False, "received_monotonic_ns": 520_000_000},
        ]
        lifecycle = [
            {"kind": "physical_takeoff_ready", "received_monotonic_ns": 520_000_000},
            {"kind": "transition_requested", "target_route": "legacy_offboard", "received_monotonic_ns": 600_000_000},
            {"kind": "motion_phase_entered", "along_track_progress_m": 0.8, "received_monotonic_ns": 700_000_000},
            {"kind": "motion_phase_completed", "along_track_progress_m": 2.6, "received_monotonic_ns": 800_000_000},
        ]
        plan = {
            "transition": {"target_route": "legacy_offboard", "fault_expected": False},
            "workload": {"physical_validity": {"minimum_takeoff_height_m": 0.5, "takeoff_dwell_s": 0.5, "minimum_motion_entry_progress_m": 0.75, "minimum_nominal_completion_progress_m": 2.5}},
        }
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory)
            (raw / "telemetry.sidecar.jsonl").write_text("".join(json.dumps(item) + "\n" for item in telemetry), encoding="utf-8")
            lifecycle_path = raw / "workload.lifecycle.jsonl"
            lifecycle_path.write_text("".join(json.dumps(item) + "\n" for item in lifecycle), encoding="utf-8")
            self.assertEqual(_physical_execution_contract(raw, plan)["status"], "PASS")
            lifecycle[1]["received_monotonic_ns"] = 400_000_000
            lifecycle_path.write_text("".join(json.dumps(item) + "\n" for item in lifecycle), encoding="utf-8")
            result = _physical_execution_contract(raw, plan)
            self.assertFalse(result["checks"]["takeoff_before_tested_transition"])


if __name__ == "__main__":
    unittest.main()
