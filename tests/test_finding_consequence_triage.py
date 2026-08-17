"""Tests for frozen finding, consequence, and Dynamic-timeout triage."""

from __future__ import annotations

from pathlib import Path
import unittest

from scripts.analysis.finding_consequence_triage import (
    dynamic_timeout_triage,
    freshness_triage,
    installation_triage,
    summarize,
)


class FindingConsequenceTriageTests(unittest.TestCase):
    def test_frozen_triage_selects_concentrated_and_distinct_signatures(self) -> None:
        root = Path(".").resolve()
        if not (root / "runs/motivation-thor-v1").is_dir():
            self.skipTest("retained runtime traces are unavailable")
        installation, _ = installation_triage(root)
        freshness = freshness_triage(root)
        timeouts, _, source = dynamic_timeout_triage(root)
        summary = summarize(installation, freshness, timeouts)

        self.assertEqual(summary["installation"]["violation_trace_count"], 11)
        self.assertEqual(summary["installation"]["airborne_trace_count"], 9)
        self.assertEqual(summary["installation"]["setpoint_path"], "attitude")
        self.assertEqual(
            summary["installation"]["root_cause_status"],
            "UNRESOLVED_PENDING_HIGH_RATE_REPRODUCTION",
        )
        self.assertEqual(summary["freshness"]["airborne_observed_window_count"], 41)
        self.assertEqual(
            summary["freshness"]["role_summaries"]["INJECTED_UPDATE_STARVATION"][
                "window_count"
            ],
            8,
        )
        self.assertEqual(
            summary["freshness"]["primary_a2_hypothesis"]["fault"],
            "SETPOINT_STALL_HEALTHY",
        )
        self.assertEqual(summary["dynamic_timeouts"]["timeout_count"], 8)
        self.assertEqual(
            summary["dynamic_timeouts"]["classification_counts"][
                "CPP_REGISTERED_REQUESTER_MISSED_READINESS"
            ],
            7,
        )
        self.assertEqual(
            summary["dynamic_timeouts"]["classification_counts"][
                "DISTINCT_POST_REGISTRATION_TIMEOUT"
            ],
            1,
        )
        self.assertTrue(source["subscribes_registration_reply"])
        self.assertTrue(source["actions_gate_on_mode_id"])


if __name__ == "__main__":
    unittest.main()
