from __future__ import annotations

import unittest
from pathlib import Path

from scripts.analysis.runtime_observer_qualification import _physical


class RuntimeObserverQualificationTests(unittest.TestCase):
    def test_physical_summary_rejects_ground_only_trace(self) -> None:
        records = [
            {"kind": "vehicle_local_position", "x": 0.0, "y": 0.0, "z": 0.0, "xy_valid": True, "z_valid": True, "received_monotonic_ns": 0},
            {"kind": "vehicle_land_detected", "landed": False, "received_monotonic_ns": 10_000_000},
            {"kind": "vehicle_local_position", "x": 0.1, "y": 0.0, "z": -0.08, "xy_valid": True, "z_valid": True, "received_monotonic_ns": 800_000_000},
        ]
        self.assertFalse(_physical(records)["physical_takeoff_predicate"])

    def test_retained_phase_three_reproduces_when_inputs_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        run_root = root / "runs/phase3-observer-qualification"
        if not run_root.is_dir():
            self.skipTest("retained qualification runs are intentionally untracked")
        for profile in ("off", "baseline", "transition"):
            self.assertTrue((run_root / f"observer-{profile}-001/runtime_result.json").is_file())


if __name__ == "__main__":
    unittest.main()
