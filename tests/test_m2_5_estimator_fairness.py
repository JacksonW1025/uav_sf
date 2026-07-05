#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import m2_5_estimator_fairness as fairness  # noqa: E402


def summary(params: dict[str, Any], *, raptor: bool = False) -> dict[str, Any]:
    return {
        "effective_shared_params": params,
        "local_position_vs_groundtruth": {
            "present": True,
            "position_error_rms_m": 0.25,
            "position_estimate_nonfinite_count": 0,
            "position_estimate_nonfinite_count_all": 0,
            "velocity_error_rms_m_s": 0.30,
            "velocity_estimate_nonfinite_count": 0,
            "velocity_estimate_nonfinite_count_all": 0,
        },
        "estimator_status": {"present": True},
        "angular_velocity_vs_groundtruth": {
            "present": True,
            "error_rms_rad_s": 0.12,
            "estimate_nonfinite_count": 0,
            "estimate_nonfinite_count_all": 0,
        },
        "attitude_vs_groundtruth": {
            "present": True,
            "quaternion_error_rms_deg": 0.02,
            "attitude_quaternion_nonfinite_count": 0,
            "attitude_quaternion_nonfinite_count_all": 0,
        },
        "raptor_input": {
            "present": raptor,
            "active_samples": 120 if raptor else 0,
            "position_shared_route_verified": raptor,
            "linear_velocity_shared_route_verified": raptor,
            "angular_velocity_vehicle_route_verified": raptor,
            "orientation_shared_route_verified": raptor,
            "position_nonfinite_count": 0,
            "linear_velocity_nonfinite_count": 0,
            "angular_velocity_nonfinite_count": 0,
            "orientation_nonfinite_count": 0,
        },
    }


class M25EstimatorFairnessTest(unittest.TestCase):
    def state_contam_params(self) -> dict[str, Any]:
        return {
            "M2B_EN": 1,
            "M2B_START": 22.0,
            "M2B_END": 54.0,
            "M2B_SEED": 20260703,
            "M2B_P_PROF": 2,
            "M2B_P_DLY": 0,
            "M2B_P_X": 0.25,
            "M2B_P_Y": 0.0,
            "M2B_P_Z": 0.0,
            "M2B_V_PROF": 2,
            "M2B_V_DLY": 0,
            "M2B_V_X": -0.30,
            "M2B_V_Y": 0.0,
            "M2B_V_Z": 0.0,
            "M2B_G_PROF": 2,
            "M2B_G_DLY": 0,
            "M2B_G_X": 0.0,
            "M2B_G_Y": 0.0,
            "M2B_G_Z": 0.12,
        }

    def test_position_velocity_and_angular_rate_shim_channels_are_checked(self) -> None:
        params = self.state_contam_params()
        theta = {"boot_px4_params": params, "px4_params": params}

        self.assertIn("M2B_P_PROF", fairness.theta_state_shim_params(theta))
        result = fairness.fairness(theta, summary(params), summary(params, raptor=True))

        channels = {item["channel"] for item in result["state_shim_channels"]}
        self.assertEqual({"position", "velocity", "angular_velocity"}, channels)
        self.assertTrue(result["state_shim_topic_polluted_both_runs"])
        self.assertTrue(result["state_shim_raptor_input_touch_verified"])
        self.assertTrue(result["fair_shared_state_shim_pollution"])

    def test_bias_profile_delivery_failure_is_reported(self) -> None:
        params = self.state_contam_params()
        theta = {"boot_px4_params": params, "px4_params": params}
        classical = summary(params)
        classical["local_position_vs_groundtruth"]["position_error_rms_m"] = 0.0
        classical["local_position_vs_groundtruth"]["velocity_error_rms_m_s"] = 0.0
        classical["angular_velocity_vs_groundtruth"]["error_rms_rad_s"] = 0.0

        result = fairness.fairness(theta, classical, summary(params, raptor=True))

        self.assertFalse(result["state_shim_delivery_valid"])
        self.assertIn("position/bias: classical shared topic not polluted", result["state_shim_delivery_failures"])

    def test_mode23_neural_observation_satisfies_state_shim_touch_without_raptor_input(self) -> None:
        params = self.state_contam_params()
        theta = {"boot_px4_params": params, "px4_params": params}
        mcnn = summary(params, raptor=False)
        mcnn["neural_control_observation"] = {
            "present": True,
            "active_samples": 120,
            "position_shared_route_verified": True,
            "linear_velocity_shared_route_verified": True,
            "angular_velocity_vehicle_route_verified": True,
        }

        result = fairness.fairness(theta, summary(params), mcnn)

        self.assertTrue(result["mc_nn_observation_active"])
        self.assertFalse(result["raptor_input_active"])
        self.assertTrue(result["state_shim_mc_nn_observation_touch_verified"])
        self.assertTrue(result["state_shim_delivery_valid"])
        self.assertTrue(result["fair_shared_state_shim_pollution"])


if __name__ == "__main__":
    unittest.main()
