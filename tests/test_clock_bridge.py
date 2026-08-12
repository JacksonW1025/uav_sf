from __future__ import annotations

import unittest

from scripts.collectors.clock_bridge import ClockBridgeError, fit_clock_bridge
from scripts.collectors.closed_trace import _clock_bridge


class ClockBridgeTests(unittest.TestCase):
    def test_closed_trace_prefers_dense_gazebo_clock(self) -> None:
        records = [
            {
                "kind": "gazebo_clock_sample",
                "source_ns": index * 4_000_000,
                "analysis_projection_ns": 1_000_000_000 + index * 4_000_000,
            }
            for index in range(8)
        ]
        records.extend(
            {
                "kind": "timesync_sample",
                "source_us": index * 1000,
                "analysis_projection_ns": 9_000_000_000 + index * 1_000_000,
            }
            for index in range(8)
        )
        bridge = _clock_bridge(records, 1_000_000)
        self.assertEqual(bridge.sample_count, 8)
        self.assertEqual(bridge.map(8_000_000), 1_008_000_000)

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
