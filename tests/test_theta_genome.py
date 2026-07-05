#!/usr/bin/env python3
from __future__ import annotations

import math
import random
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import theta_genome  # noqa: E402


class ThetaGenomeTest(unittest.TestCase):
    def test_random_mutation_and_crossover_are_legal(self) -> None:
        rng = random.Random(20260626)
        parents = [theta_genome.random_genome(rng) for _ in range(200)]
        mutants = [theta_genome.mutate_genome(parent, rng) for parent in parents]
        children = [theta_genome.crossover_genome(a, b, rng) for a, b in zip(parents, reversed(mutants))]
        for genome in parents + mutants + children:
            self.assertEqual([], theta_genome.validate_genome(genome))
            theta = theta_genome.theta_from_genome(genome, "unit_theta", 20260626)
            feature = theta["theta_genome"]["map_elites"]
            self.assertIn(feature["disturbance_type"], theta_genome.SHIM_FREE_DISTURBANCE_TYPES)
            if feature["disturbance_type"] == "switching":
                self.assertEqual(
                    ["switch_roll_pitch_bucket", "wind_bucket"],
                    feature["feature_dimensions"],
                )
                self.assertRegex(feature["switch_roll_pitch_bucket"], r"^rp_[0-4]$")
                self.assertRegex(feature["wind_bucket"], r"^wind_[0-4]$")
            else:
                self.assertIn(feature["amplitude_bucket"], {"low", "mid", "high"})

    def test_step_theta_has_p5_sized_command_and_settling_window(self) -> None:
        genome = theta_genome.default_genome("step")
        genome["step_magnitude_m"] = 0.5
        genome["step_axis"] = "y"
        genome["step_sign"] = -1
        genome["step_time_s"] = 34.0
        genome["mission_end_s"] = 50.0
        genome = theta_genome.normalize_genome(genome)
        theta = theta_genome.theta_from_genome(genome, "unit_step", 20260626)
        delta = theta["setpoint"]["step"]["delta_ned"]
        self.assertGreaterEqual(math.sqrt(sum(value * value for value in delta)), 0.5)
        self.assertGreaterEqual(theta["timing"]["mission_end_s"] - theta["setpoint"]["step"]["start_s"], 12.0)

    def test_steady_combo_keeps_wind_and_physics_and_uses_2d_descriptor(self) -> None:
        genome = theta_genome.default_genome(theta_genome.COMBINED_STEADY_DISTURBANCE_TYPE)
        genome.update(
            {
                "wind_speed_m_s": 8.0,
                "wind_direction_rad": 1.8,
                "mass_scale": 1.25,
                "inertia_roll_scale": 1.60,
                "inertia_pitch_scale": 1.60,
                "inertia_yaw_scale": 1.80,
                "twr_scale": 1.0,
            }
        )
        genome = theta_genome.normalize_genome(genome)
        self.assertEqual([], theta_genome.validate_genome(genome))
        theta = theta_genome.theta_from_genome(genome, "unit_steady_combo", 20260627)
        feature = theta["theta_genome"]["map_elites"]
        self.assertEqual(["wind_bucket", "physics_bucket"], feature["feature_dimensions"])
        self.assertEqual("high", feature["wind_bucket"])
        self.assertEqual("high", feature["physics_bucket"])
        self.assertGreater(abs(theta["boot_px4_params"]["SIH_WIND_N"]), 0.1)
        self.assertNotEqual(theta_genome.NOMINAL["mass"], theta["boot_px4_params"]["SIH_MASS"])
        self.assertTrue(theta["environment"]["steady_combo"]["combined_wind_and_physics"])

    def test_switching_and_step_subspaces_keep_existing_gates(self) -> None:
        switching = theta_genome.default_genome("switching")
        switching.update({"wind_speed_m_s": 6.0, "mass_scale": 1.25, "inertia_roll_scale": 1.60})
        switching = theta_genome.normalize_genome(switching)
        self.assertEqual(6.0, switching["wind_speed_m_s"])
        self.assertEqual(1.0, switching["mass_scale"])
        switching_theta = theta_genome.theta_from_genome(switching, "unit_switching", 20260627)
        self.assertEqual("circle", switching_theta["setpoint"]["type"])
        self.assertEqual(
            ["switch_roll_pitch_bucket", "wind_bucket"],
            switching_theta["theta_genome"]["map_elites"]["feature_dimensions"],
        )

        step = theta_genome.default_genome("step")
        step.update({"wind_speed_m_s": 8.0, "mass_scale": 1.25})
        step = theta_genome.normalize_genome(step)
        self.assertEqual(0.0, step["wind_speed_m_s"])
        self.assertEqual(1.0, step["mass_scale"])
        step_theta = theta_genome.theta_from_genome(step, "unit_step_gate", 20260627)
        self.assertNotIn("steady_combo", step_theta["environment"])

    def test_state_contamination_generates_executable_shim_theta(self) -> None:
        genome = theta_genome.default_genome("state_contam")
        genome.update(
            {
                "fake_velocity_bias_m_s": -0.30,
                "fake_angular_rate_bias_rad_s": 0.12,
                "position_estimate_jump_m": 0.25,
            }
        )
        genome = theta_genome.normalize_genome(genome)

        self.assertEqual([], theta_genome.validate_genome(genome))
        self.assertTrue(all(spec.enabled for spec in theta_genome.VARIABLE_SPECS if spec.group == "state_contam"))

        theta = theta_genome.theta_from_genome(genome, "unit_state_contam", 20260703)
        for target_name in ["boot_px4_params", "px4_params"]:
            params = theta[target_name]
            self.assertEqual(1, params["M2B_EN"])
            self.assertEqual(2, params["M2B_P_PROF"])
            self.assertEqual(0.25, params["M2B_P_X"])
            self.assertEqual(0.0, params["M2B_P_Y"])
            self.assertEqual(0.0, params["M2B_P_Z"])
            self.assertEqual(2, params["M2B_V_PROF"])
            self.assertEqual(-0.30, params["M2B_V_X"])
            self.assertEqual(0.0, params["M2B_V_Y"])
            self.assertEqual(0.0, params["M2B_V_Z"])
            self.assertEqual(2, params["M2B_G_PROF"])
            self.assertEqual(0.0, params["M2B_G_X"])
            self.assertEqual(0.0, params["M2B_G_Y"])
            self.assertEqual(0.12, params["M2B_G_Z"])

        feature = theta["theta_genome"]["map_elites"]
        self.assertEqual(["velocity_bias_bucket", "angular_rate_bias_bucket"], feature["feature_dimensions"])
        self.assertRegex(feature["velocity_bias_bucket"], r"^vel_[0-4]$")
        self.assertRegex(feature["angular_rate_bias_bucket"], r"^gyro_[0-4]$")
        self.assertEqual("ACTIVE - routed through m2b_state_shim.patch", theta["theta_genome"]["state_contam_status"])
        self.assertTrue(theta["environment"]["uses_state_shim"])
        self.assertEqual(3, len(theta["sensor_perturbations"]))


if __name__ == "__main__":
    unittest.main()
