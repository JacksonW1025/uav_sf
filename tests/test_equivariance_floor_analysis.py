import unittest

import numpy as np

from scripts import equivariance_floor_analysis as efa


class EquivarianceFloorAnalysisTests(unittest.TestCase):
    def test_wrap_angle_deg_normalizes_to_signed_180(self):
        self.assertAlmostEqual(efa.wrap_angle_deg(181.0), -179.0)
        self.assertAlmostEqual(efa.wrap_angle_deg(-181.0), 179.0)
        self.assertAlmostEqual(efa.wrap_angle_deg(540.0), -180.0)

    def test_yaw_error_wraps_across_dateline(self):
        self.assertAlmostEqual(efa.yaw_error_deg(179.0, -179.0), -2.0)
        self.assertAlmostEqual(efa.yaw_error_deg(-179.0, 179.0), 2.0)

    def test_quat_tilt_deg_is_yaw_invariant(self):
        q = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [2 ** -0.5, 2 ** -0.5, 0.0, 0.0],
                [2 ** -0.5, 0.0, 0.0, 2 ** -0.5],
            ]
        )
        tilt = efa.quat_tilt_deg(q)
        self.assertAlmostEqual(tilt[0], 0.0)
        self.assertAlmostEqual(tilt[1], 90.0)
        self.assertAlmostEqual(tilt[2], 0.0)

    def test_fisher_one_sided_greater_uses_hypergeometric_tail(self):
        self.assertAlmostEqual(
            efa.fisher_exact_greater(success_a=5, total_a=5, success_b=0, total_b=2),
            1.0 / 21.0,
        )
        self.assertAlmostEqual(
            efa.fisher_exact_greater(success_a=6, total_a=6, success_b=1, total_b=5),
            7.0 / 462.0,
        )

    def test_theta_consistency_accepts_equal_base_fields(self):
        theta = {
            "yaw_equivariance_probe": {
                "plan_metadata": {
                    "base": {
                        "requested_rate_rad_s": 1.15,
                        "switch_delay_s": 0.09,
                        "wind_speed_m_s": 0.0,
                        "approach_phase_rad": 0.0,
                    }
                }
            }
        }
        result = efa.compare_theta_base(theta, efa.DENSE_BASE)
        self.assertTrue(result["matches"])
        self.assertEqual(result["mismatches"], [])

    def test_theta_consistency_reports_mismatched_field(self):
        theta = {
            "yaw_equivariance_probe": {
                "plan_metadata": {
                    "base": {
                        "requested_rate_rad_s": 1.15,
                        "switch_delay_s": 0.12,
                        "wind_speed_m_s": 0.0,
                        "approach_phase_rad": 0.0,
                    }
                }
            }
        }
        result = efa.compare_theta_base(theta, efa.DENSE_BASE)
        self.assertFalse(result["matches"])
        self.assertEqual(result["mismatches"][0]["field"], "switch_delay_s")


if __name__ == "__main__":
    unittest.main()
