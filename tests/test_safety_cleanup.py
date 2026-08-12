from __future__ import annotations

import unittest

from scripts.safety.cleanup import evaluate_cleanup
from scripts.safety.supervisor import SafetyLimits, SafetySupervisor
from tests.helpers import passing_events, plan


class SafetyCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.limits = SafetyLimits(
            heartbeat_timeout_ns=100,
            collector_timeout_ns=100,
            run_timeout_ns=1_000,
            maximum_altitude_loss_m=3.0,
            maximum_horizontal_speed_m_s=8.0,
            maximum_vertical_speed_m_s=5.0,
            maximum_attitude_excursion_deg=45.0,
            maximum_body_rate_rad_s=4.0,
        )

    def test_physical_boundary_installs_safe_fallback(self) -> None:
        supervisor = SafetySupervisor(
            self.limits, started_ns=0, required_collectors={"route", "clock"}
        )
        result = supervisor.observe(
            {
                "kind": "telemetry",
                "altitude_loss_m": 4.0,
                "horizontal_speed_m_s": 0.0,
                "vertical_speed_m_s": 0.0,
                "attitude_excursion_deg": 0.0,
                "body_rate_rad_s": 0.0,
            },
            now_ns=10,
        )
        self.assertEqual(result["decision"], "STOP_AND_INSTALL_FALLBACK")
        self.assertEqual(result["fallback"], "internal_land")

    def test_heartbeat_timeout_stops(self) -> None:
        supervisor = SafetySupervisor(
            self.limits, started_ns=0, required_collectors={"route"}
        )
        self.assertEqual(supervisor.check_time(now_ns=101)["decision"], "STOP_AND_INSTALL_FALLBACK")

    def test_cleanup_passes_only_after_revocation_and_terminal_state(self) -> None:
        result = evaluate_cleanup(passing_events(), plan())
        self.assertEqual(result["status"], "PASS")
        incomplete = evaluate_cleanup(passing_events()[:-2] + passing_events()[-1:], plan())
        self.assertEqual(incomplete["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
