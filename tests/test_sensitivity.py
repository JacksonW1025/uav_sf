"""Continuous-metric and threshold-curve tests."""

from __future__ import annotations

import unittest

from scripts.analysis.sensitivity import (
    extract_transition_metrics,
    stability_intervals,
    threshold_curve,
)
from scripts.oracles.transition_scope import matching_transition_requests
from tests.helpers import passing_events, plan


class SensitivityTests(unittest.TestCase):
    def test_extracts_continuous_metrics_from_complete_transition(self) -> None:
        events = passing_events()
        experiment = plan()
        request = matching_transition_requests(events, experiment)[0]
        metrics = extract_transition_metrics(events, experiment, request)
        self.assertEqual(metrics["installation_latency_ns"], 18_000_000)
        self.assertEqual(metrics["revocation_latency_ns"], 6_000_000)
        self.assertEqual(metrics["continuity_gap_ns"], 13_000_000)
        self.assertEqual(metrics["maximum_command_age_ns"], 13_000_000)
        self.assertEqual(metrics["successor_latency_ns"], 18_000_000)

    def test_threshold_curve_keeps_missing_observations_unknown(self) -> None:
        point = threshold_curve([100, 200, None], 150)
        self.assertEqual(point["threshold_ns"], 150)
        self.assertEqual(point["pass_count"], 1)
        self.assertEqual(point["violation_count"], 1)
        self.assertEqual(point["unknown_count"], 1)
        self.assertEqual(point["calculable_count"], 2)

    def test_threshold_equality_passes(self) -> None:
        point = threshold_curve([200], 200)
        self.assertEqual(point["pass_count"], 1)
        self.assertEqual(point["violation_count"], 0)

    def test_stability_intervals_change_only_at_observed_crossings(self) -> None:
        intervals = stability_intervals([100, 200, None], 50, 250)
        self.assertEqual(
            [(item["lower_threshold_ns"], item["upper_threshold_ns"]) for item in intervals],
            [(50, 100), (100, 200), (200, 250)],
        )
        self.assertFalse(intervals[0]["upper_inclusive"])
        self.assertEqual(intervals[1]["pass_count"], 1)
        self.assertEqual(intervals[-1]["pass_count"], 2)
        self.assertTrue(intervals[-1]["upper_inclusive"])


if __name__ == "__main__":
    unittest.main()
