from __future__ import annotations

import unittest

from scripts.collectors.clock_bridge import ClockBridgeError, fit_clock_bridge


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


if __name__ == "__main__":
    unittest.main()
