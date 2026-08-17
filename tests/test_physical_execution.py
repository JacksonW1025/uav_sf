"""Tests for the read-only physical-execution audit."""

from __future__ import annotations

from pathlib import Path
import unittest

from scripts.analysis.corpus import load_frozen_corpus
from scripts.analysis.physical_execution import (
    analyze_record,
    physical_metrics,
    quaternion_tilt_degrees,
    summarize,
)


def telemetry_sample(
    kind: str,
    timestamp_ns: int,
    sequence: int,
    **fields: object,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "run_id": "unit",
        "kind": kind,
        "received_monotonic_ns": timestamp_ns,
        "sequence": sequence,
        **fields,
    }


class PhysicalExecutionTests(unittest.TestCase):
    def test_physical_metrics_use_local_ned_origin_and_window(self) -> None:
        telemetry = [
            telemetry_sample(
                "vehicle_local_position",
                100,
                0,
                x=0.0,
                y=0.0,
                z=0.0,
                vx=0.0,
                vy=0.0,
                vz=-1.0,
                xy_valid=True,
                z_valid=True,
            ),
            telemetry_sample(
                "vehicle_local_position",
                200,
                1,
                x=3.0,
                y=4.0,
                z=-2.0,
                vx=3.0,
                vy=4.0,
                vz=0.5,
                xy_valid=True,
                z_valid=True,
            ),
            telemetry_sample(
                "vehicle_local_position",
                300,
                2,
                x=99.0,
                y=99.0,
                z=-99.0,
                vx=0.0,
                vy=0.0,
                vz=0.0,
                xy_valid=True,
                z_valid=True,
            ),
        ]
        metrics = physical_metrics(telemetry, start_ns=100, end_ns=200)
        self.assertEqual(metrics["maximum_height_above_local_origin_m"], 2.0)
        self.assertEqual(metrics["maximum_horizontal_distance_from_origin_m"], 5.0)
        self.assertEqual(metrics["straight_line_displacement_m"], 5.385164807)
        self.assertEqual(metrics["peak_horizontal_speed_m_s"], 5.0)
        self.assertEqual(metrics["position_sample_count"], 2)

    def test_quaternion_tilt_ignores_yaw(self) -> None:
        self.assertAlmostEqual(quaternion_tilt_degrees([1.0, 0.0, 0.0, 0.0]), 0.0)
        self.assertAlmostEqual(
            quaternion_tilt_degrees([2**-0.5, 0.0, 0.0, 2**-0.5]),
            0.0,
        )
        self.assertAlmostEqual(
            quaternion_tilt_degrees([2**-0.5, 2**-0.5, 0.0, 0.0]),
            90.0,
        )

    def test_frozen_corpus_has_the_twelve_separated_non_airborne_attempts(self) -> None:
        root = Path(".").resolve()
        if not (root / "runs/motivation-thor-v1").is_dir():
            self.skipTest("retained runtime traces are unavailable")
        results = []
        windows = []
        for record in load_frozen_corpus(root):
            result, aligned = analyze_record(
                record, root, airborne_minimum_height_m=0.5
            )
            results.append(result)
            windows.extend(aligned)
        summary = summarize(results, windows, airborne_minimum_height_m=0.5)
        expected = {
            "det-offboard-attitude-land-002",
            "det-offboard-attitude-land-004",
            "det-offboard-body-rate-land-002",
            "det-offboard-body-rate-land-004",
            "det-offboard-body-rate-land-005",
            "fault-offboard-attitude-stall-003",
            "fault-offboard-attitude-stall-005",
            "fault-offboard-body-rate-stall-001",
            "fault-offboard-body-rate-stall-003",
            "fault-offboard-body-rate-stall-004",
            "fault-offboard-body-rate-stall-005",
            "fault-offboard-body-rate-stall-008",
        }
        observed = {
            item["attempt_id"] for item in summary["non_airborne"]["attempts"]
        }
        self.assertEqual(observed, expected)
        self.assertEqual(summary["physical_execution_status_counts"]["AIRBORNE"], 139)
        self.assertEqual(summary["physical_execution_status_counts"]["NON_AIRBORNE"], 12)
        self.assertEqual(summary["physical_to_frozen_status_counts"]["NON_AIRBORNE->PASS"], 3)
        self.assertEqual(
            summary["physical_to_frozen_status_counts"]["NON_AIRBORNE->VIOLATION"],
            9,
        )
        self.assertEqual(summary["non_airborne"]["frozen_violation_clause_count"], 10)
        self.assertLessEqual(
            summary["classification_separation"]["largest_non_airborne_height_m"],
            0.08,
        )
        self.assertGreater(
            summary["classification_separation"]["smallest_airborne_height_m"],
            1.8,
        )


if __name__ == "__main__":
    unittest.main()
