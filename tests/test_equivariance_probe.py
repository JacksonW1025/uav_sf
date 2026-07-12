#!/usr/bin/env python3
from __future__ import annotations

import importlib
import math
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from equivariance_transform import body_frame_maneuver_signature, wind_speed_m_s  # noqa: E402


class EquivarianceProbePlanTest(unittest.TestCase):
    def test_phase1_plan_has_locked_six_theta_four_yaws_and_expected_evals(self) -> None:
        probe = importlib.import_module("run_equivariance_probe")

        points = probe.planned_theta_points()
        floor, neural = probe.phase1_plan("unit_equivariance", points=points, wind_zero=True)

        self.assertEqual(
            ["attitude_deg_42", "attitude_deg_45", "attitude_deg_48", "pair2", "pair5", "hard_attitude_deg_50"],
            [point.theta_id for point in points],
        )
        self.assertEqual(24, len(floor))
        self.assertEqual(48, len(neural))
        self.assertEqual({"classical"}, {item.controller for item in floor})
        self.assertEqual({"mcnn"}, {item.controller for item in neural})
        self.assertEqual({0, 90, 180, 270}, {round(math.degrees(item.psi_rad)) for item in floor})
        self.assertEqual({2026070801}, {item.seed for item in floor})
        self.assertEqual({2026070801, 2026070802}, {item.seed for item in neural})

    def test_stage0_plan_uses_single_windy_anchor_and_preserves_body_signature(self) -> None:
        probe = importlib.import_module("run_equivariance_probe")

        stage0 = probe.stage0_plan("unit_equivariance")

        self.assertEqual(4, len(stage0))
        self.assertEqual({"pair2"}, {item.theta_id for item in stage0})
        self.assertEqual({"classical"}, {item.controller for item in stage0})
        self.assertGreater(wind_speed_m_s(stage0[0].point.base_theta), 0.0)

        base_signature = body_frame_maneuver_signature(stage0[0].point.base_theta)
        for item in stage0:
            theta = probe.theta_for_eval(item)
            self.assertEqual(
                [0.0, 0.25, 0.5, 1.0],
                theta["setpoint"]["diagnostic_probe"]["relative_times_s"],
            )
            self.assertEqual(base_signature, body_frame_maneuver_signature(theta))

    def test_list_plan_exposes_phase1_scale(self) -> None:
        probe = importlib.import_module("run_equivariance_probe")

        listing = probe.list_plan("unit_equivariance", wind_zero=True)

        self.assertEqual(6, listing["phase1"]["theta_count"])
        self.assertEqual(24, listing["phase1"]["floor_gate_eval_count"])
        self.assertEqual(48, listing["phase1"]["mcnn_eval_count"])
        self.assertEqual(4, listing["stage0"]["eval_count"])
        self.assertTrue(listing["phase1"]["wind_zero"])


if __name__ == "__main__":
    unittest.main()
