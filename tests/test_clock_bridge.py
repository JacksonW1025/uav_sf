from __future__ import annotations

import unittest

from scripts.collectors.clock_bridge import ClockBridge, ClockBridgeError, fit_clock_bridge


class ClockBridgeTests(unittest.TestCase):
    def test_affine_mapping_and_bound(self) -> None:
        samples = [
            {
                "source_domain": "ros_monotonic",
                "source_ns": index * 1_000,
                "analysis_ns": 50_000 + index * 1_001,
                "round_trip_ns": 20,
            }
            for index in range(8)
        ]
        bridge = fit_clock_bridge(samples, maximum_uncertainty_ns=100)
        self.assertEqual(bridge.sample_count, 8)
        self.assertAlmostEqual(bridge.rate_ratio, 1.001, places=5)
        self.assertEqual(bridge.map(3_000), 53_003)

    def test_insufficient_samples_are_rejected(self) -> None:
        with self.assertRaises(ClockBridgeError):
            fit_clock_bridge([], maximum_uncertainty_ns=100)

    def test_mapping_refuses_out_of_range_subject_time(self) -> None:
        bridge = ClockBridge(
            bridge_id="clock-test",
            source_domain="px4_boot_ns",
            reference_source_ns=3_000_000,
            reference_analysis_ns=13_000_000,
            rate_ratio=1.0,
            uncertainty_ns=0,
            valid_from_ns=1_000_000,
            valid_until_ns=5_000_000,
            sample_count=2,
            knots=((1_000_000, 11_000_000), (5_000_000, 15_000_000)),
        )
        self.assertEqual(bridge.map(2_500_000), 12_500_000)
        with self.assertRaises(ClockBridgeError):
            bridge.map(500_000)


if __name__ == "__main__":
    unittest.main()
