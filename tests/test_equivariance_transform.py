#!/usr/bin/env python3
from __future__ import annotations

import copy
import math
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import theta_genome  # noqa: E402
from equivariance_transform import (  # noqa: E402
    apply_yaw_rotation,
    body_frame_maneuver_signature,
    circle_bearing_rad,
    wind_bearing_rad,
    wind_speed_m_s,
    zero_wind,
)


def angle_close(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(math.atan2(math.sin(a - b), math.cos(a - b))) <= tol


class EquivarianceTransformTest(unittest.TestCase):
    def setUp(self) -> None:
        genome = theta_genome.default_genome("switching")
        genome.update(
            {
                "approach_radius_m": 3.6,
                "approach_frequency_hz": 0.25,
                "approach_phase_rad": 0.4,
                "switch_roll_pitch_deg": theta_genome.expected_circle_tilt_deg(genome),
                "switch_rate_rad_s": 1.05,
                "wind_speed_m_s": 4.0,
                "wind_direction_rad": 0.3,
                "switch_delay_s": 0.09,
            }
        )
        genome = theta_genome.normalize_genome(genome)
        self.theta = theta_genome.theta_from_genome(genome, "unit_equivariance_base", 20260708)

    def test_rotation_preserves_body_frame_maneuver_and_adds_semantic_bearings(self) -> None:
        base = self.theta
        base_signature = body_frame_maneuver_signature(base)
        base_circle_bearing = circle_bearing_rad(base)
        base_wind_bearing = wind_bearing_rad(base)
        base_genome = base["theta_genome"]["genome"]

        for psi in [0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0]:
            with self.subTest(psi=psi):
                rotated = apply_yaw_rotation(base, psi)
                genome = rotated["theta_genome"]["genome"]

                self.assertTrue(angle_close(rotated["setpoint"]["yaw_rad"], psi))
                self.assertTrue(angle_close(circle_bearing_rad(rotated), base_circle_bearing + psi))
                self.assertTrue(angle_close(wind_bearing_rad(rotated), base_wind_bearing + psi))
                self.assertEqual(base_signature, body_frame_maneuver_signature(rotated))

                self.assertEqual(base["setpoint"]["circle"]["radius_m"], rotated["setpoint"]["circle"]["radius_m"])
                self.assertEqual(base["setpoint"]["circle"]["frequency_hz"], rotated["setpoint"]["circle"]["frequency_hz"])
                self.assertEqual(
                    base["setpoint"]["activation_trigger"]["roll_pitch_abs_min_deg"],
                    rotated["setpoint"]["activation_trigger"]["roll_pitch_abs_min_deg"],
                )
                self.assertEqual(
                    base["setpoint"]["activation_trigger"]["angular_rate_norm_min_rad_s"],
                    rotated["setpoint"]["activation_trigger"]["angular_rate_norm_min_rad_s"],
                )
                self.assertAlmostEqual(wind_speed_m_s(base), wind_speed_m_s(rotated), places=9)
                self.assertEqual(base_genome["switch_roll_pitch_deg"], genome["switch_roll_pitch_deg"])
                self.assertEqual(base_genome["switch_rate_rad_s"], genome["switch_rate_rad_s"])
                self.assertEqual([], theta_genome.validate_genome(genome))

    def test_legacy_anchor_shape_rotates_case_phase_wind_and_yaw(self) -> None:
        theta = {
            "tag": "legacy_anchor",
            "seed": 1,
            "setpoint": {
                "yaw_rad": 0.0,
                "type": "circle",
                "hover_ned": [0.0, 0.0, -2.5],
                "circle": {"radius_m": 6.0, "frequency_hz": 0.45, "phase_rad": 0.0},
            },
            "boot_px4_params": {"SIH_WIND_N": 6.0, "SIH_WIND_E": 0.0},
            "px4_params": {},
            "environment": {"case": {"phase_rad": 0.0, "wind_n": 6.0, "wind_e": 0.0}},
        }
        original = copy.deepcopy(theta)

        rotated = apply_yaw_rotation(theta, math.pi / 2.0)

        self.assertEqual(original, theta)
        self.assertTrue(angle_close(rotated["setpoint"]["yaw_rad"], math.pi / 2.0))
        self.assertTrue(angle_close(circle_bearing_rad(rotated), circle_bearing_rad(original) + math.pi / 2.0))
        self.assertAlmostEqual(rotated["boot_px4_params"]["SIH_WIND_N"], 0.0, places=9)
        self.assertAlmostEqual(rotated["boot_px4_params"]["SIH_WIND_E"], 6.0, places=9)
        self.assertAlmostEqual(rotated["environment"]["case"]["wind_n"], 0.0, places=9)
        self.assertAlmostEqual(rotated["environment"]["case"]["wind_e"], 6.0, places=9)
        self.assertEqual(body_frame_maneuver_signature(original), body_frame_maneuver_signature(rotated))

    def test_zero_wind_removes_wind_amplitude_without_touching_circle_or_yaw(self) -> None:
        base_signature = body_frame_maneuver_signature(self.theta)
        no_wind = zero_wind(self.theta)

        self.assertAlmostEqual(wind_speed_m_s(no_wind), 0.0, places=9)
        self.assertEqual(self.theta["setpoint"]["yaw_rad"], no_wind["setpoint"]["yaw_rad"])
        self.assertEqual(self.theta["setpoint"]["circle"], no_wind["setpoint"]["circle"])
        self.assertEqual(
            base_signature["body_circle_samples"],
            body_frame_maneuver_signature(no_wind)["body_circle_samples"],
        )
        self.assertEqual([], theta_genome.validate_genome(no_wind["theta_genome"]["genome"]))


if __name__ == "__main__":
    unittest.main()
