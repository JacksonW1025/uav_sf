from __future__ import annotations

import unittest

from scripts.collectors.clock_bridge import ClockBridge, ClockBridgeError, fit_clock_bridge
from scripts.collectors.closed_trace import _clock_bridge, _identity, _map_ulog, _route


class ClockBridgeTests(unittest.TestCase):
    def test_offboard_reentry_identity_is_bound_to_route_epoch(self) -> None:
        first = _identity(
            route="legacy_offboard", epoch=2, nav_state=14, source_id=1, run_id="run-1"
        )
        second = _identity(
            route="legacy_offboard", epoch=4, nav_state=14, source_id=1, run_id="run-1"
        )
        self.assertNotEqual(first["producer_session"], second["producer_session"])
        self.assertEqual(first["producer_session"], "offboard-run-1-epoch-2")

    def test_internal_mode_completion_cannot_impersonate_external_target(self) -> None:
        plan = {
            "transition": {
                "source_route": "px4_internal",
                "target_route": "mode_executor",
            }
        }
        self.assertEqual(_route(2, plan), "px4_internal")
        self.assertEqual(_route(23, plan), "mode_executor")

    def test_closed_trace_prefers_direct_px4_timesync(self) -> None:
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
        self.assertEqual(bridge.map(2_000_000), 9_002_000_000)

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

    def test_pre_bridge_command_subject_is_omitted_not_mapped(self) -> None:
        bridge = ClockBridge(
            bridge_id="clock-test", source_domain="px4_boot_ns",
            reference_source_ns=3_000_000, reference_analysis_ns=13_000_000,
            rate_ratio=1.0, uncertainty_ns=0, valid_from_ns=1_000_000,
            valid_until_ns=5_000_000, sample_count=2,
            knots=((1_000_000, 11_000_000), (5_000_000, 15_000_000)),
        )
        common = {"ulog_multi_id": 0, "profile": 2, "source_id": 1}
        observations = [
            {**common, "event_type": 4, "timestamp": 1000, "subject_timestamp": 1000, "sequence": 0, "route_epoch_id": 1, "new_nav_state": 14, "previous_nav_state": 2},
            {**common, "event_type": 1, "timestamp": 2000, "subject_timestamp": 500, "sequence": 1, "route_epoch_id": 1, "new_nav_state": 14, "previous_nav_state": 2},
            {**common, "event_type": 1, "timestamp": 3000, "subject_timestamp": 2500, "sequence": 2, "route_epoch_id": 1, "new_nav_state": 14, "previous_nav_state": 2},
        ]
        plan = {"run_id": "test", "transition": {"source_route": "px4_internal", "target_route": "legacy_offboard"}}
        result = _map_ulog(observations, bridge, plan)
        commands = [item for item in result if item["kind"] == "command_consumed"]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["command_subject_ns"], 12_500_000)


if __name__ == "__main__":
    unittest.main()
