from __future__ import annotations

import unittest

from scripts.evaluator.evaluate_trace import evaluate
from tests.helpers import chain, identity, passing_events, passing_raw_events, plan, raw_event


class EvaluationTests(unittest.TestCase):
    def test_complete_admissible_transition_passes(self) -> None:
        result = evaluate(passing_events(), plan())
        self.assertEqual(result["evidence_gate"]["status"], "ADMISSIBLE")
        self.assertEqual(result["status"], "PASS")

    def test_missing_required_evidence_is_never_pass(self) -> None:
        raw = [event for event in passing_raw_events() if event["kind"] != "revocation"]
        result = evaluate(chain(raw), plan())
        self.assertEqual(result["evidence_gate"]["status"], "INADMISSIBLE")
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_missing_environment_attestation_is_never_pass(self) -> None:
        raw = [
            event
            for event in passing_raw_events()
            if event["kind"] != "environment_attested"
        ]
        result = evaluate(chain(raw), plan())
        self.assertEqual(result["evidence_gate"]["status"], "INADMISSIBLE")
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_environment_attestation_must_match_plan(self) -> None:
        raw = passing_raw_events()
        for event in raw:
            if event["kind"] == "environment_attested":
                event["execution_environment"]["execution_host_id"] = "wrong-host"
        result = evaluate(chain(raw), plan())
        self.assertEqual(result["evidence_gate"]["status"], "INADMISSIBLE")
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_environment_attestation_must_open_the_trace(self) -> None:
        raw = passing_raw_events()
        attestation = raw.pop(1)
        raw.insert(3, attestation)
        result = evaluate(chain(raw), plan())
        self.assertEqual(result["evidence_gate"]["status"], "INADMISSIBLE")
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_hash_tampering_is_inconclusive(self) -> None:
        events = passing_events()
        events[7]["controller_id"] = "tampered"
        result = evaluate(events, plan())
        self.assertEqual(result["evidence_gate"]["status"], "INADMISSIBLE")
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_stale_target_command_is_violation(self) -> None:
        raw = passing_raw_events()
        for event in raw:
            if event.get("route") == "dynamic_external_mode" and "command_subject_ns" in event:
                event["command_subject_ns"] = 0
        result = evaluate(chain(raw), plan())
        self.assertEqual(result["status"], "VIOLATION")

    def test_setpoint_stall_after_installation_is_still_a_violation(self) -> None:
        raw = passing_raw_events()
        raw.insert(
            11,
            raw_event(
                "actuator_write",
                149_000_000,
                command_subject_ns=20_000_000,
                **identity("dynamic_external_mode", "target"),
            ),
        )
        result = evaluate(chain(raw), plan())
        freshness = result["oracles"][1]["clauses"]["freshness"]
        self.assertEqual(freshness["status"], "VIOLATION")

    def test_conflicting_target_lineage_is_violation(self) -> None:
        raw = passing_raw_events()
        conflict = raw_event(
            "controller_output",
            125_000_000,
            command_subject_ns=115_000_000,
            **identity("dynamic_external_mode", "conflict"),
        )
        raw.insert(8, conflict)
        result = evaluate(chain(raw), plan())
        self.assertEqual(result["status"], "VIOLATION")

    def test_missing_successor_installation_is_violation(self) -> None:
        raw = [
            event
            for event in passing_raw_events()
            if event.get("route") != "internal_hold" and event["kind"] != "terminal_state"
        ]
        raw.insert(
            -1,
            raw_event(
                "terminal_state",
                170_000_000,
                route="internal_land",
                landed=True,
                disarmed=True,
            ),
        )
        result = evaluate(chain(raw), plan())
        self.assertEqual(result["evidence_gate"]["status"], "ADMISSIBLE")
        self.assertEqual(result["status"], "VIOLATION")

    def test_source_effect_after_revocation_is_violation(self) -> None:
        raw = passing_raw_events()
        raw.insert(
            10,
            raw_event(
                "actuator_write",
                129_000_000,
                command_subject_ns=100_000_000,
                **identity("legacy_offboard", "source"),
            ),
        )
        result = evaluate(chain(raw), plan())
        route = result["oracles"][0]["clauses"]
        self.assertEqual(route["revocation"]["status"], "VIOLATION")
        self.assertEqual(route["exclusivity"]["status"], "VIOLATION")

    def test_continuity_gap_is_violation(self) -> None:
        raw = passing_raw_events()
        for event in raw:
            if event["kind"] == "actuator_write" and event.get("route") == "dynamic_external_mode":
                event["timestamp_ns"] = 200_000_000
        result = evaluate(chain(raw), plan())
        route = result["oracles"][0]["clauses"]
        self.assertEqual(route["continuity"]["status"], "VIOLATION")

    def test_expected_fault_requires_complete_safe_fallback(self) -> None:
        experiment = plan()
        experiment["transition"]["fault_expected"] = True
        experiment["transition"]["fallback_expected"] = True
        fallback = identity("internal_land", "fallback")
        raw = passing_raw_events()
        additions = [
            raw_event("fault_detected", 200_000_000),
            raw_event("fallback_triggered", 201_000_000, route="internal_land"),
            raw_event("activation", 202_000_000, **fallback),
            raw_event("command_consumed", 204_000_000, command_subject_ns=199_000_000, **fallback),
            raw_event("controller_output", 206_000_000, command_subject_ns=199_000_000, **fallback),
            raw_event("allocator_output", 208_000_000, command_subject_ns=199_000_000, **fallback),
            raw_event("actuator_write", 210_000_000, command_subject_ns=199_000_000, **fallback),
        ]
        raw[-1:-1] = additions
        result = evaluate(chain(raw), experiment)
        successor = result["oracles"][2]["clauses"]
        self.assertEqual(successor["safe_fallback"]["status"], "PASS")

    def test_fault_without_expected_fallback_is_independently_representable(self) -> None:
        experiment = plan()
        experiment["transition"]["fault_expected"] = True
        raw = passing_raw_events()
        raw.insert(-1, raw_event("fault_detected", 200_000_000, reason="setpoint_stall"))
        result = evaluate(chain(raw), experiment)
        successor = result["oracles"][2]["clauses"]
        self.assertEqual(successor["fault_observation"]["status"], "PASS")
        self.assertEqual(successor["safe_fallback"]["status"], "NOT_APPLICABLE")

    def test_expected_activation_rejection_does_not_require_route_installation(self) -> None:
        experiment = plan()
        transition = experiment["transition"]
        transition["target_activation_expected"] = False
        transition["activation_rejection_expected"] = True
        transition["completion_expected"] = False
        transition["fault_expected"] = True
        experiment["required_event_kinds"] = [
            "collection_started",
            "collection_stopped",
            "environment_attested",
            "activation_requested",
            "fault_detected",
        ]
        raw = [
            raw_event("collection_started", 0),
            raw_event(
                "environment_attested",
                1,
                execution_environment=experiment["execution_environment"],
            ),
            raw_event(
                "activation_requested",
                10,
                source_route="px4_internal",
                target_route="dynamic_external_mode",
            ),
            raw_event(
                "fault_detected",
                20,
                reason="activation_rejected_after_health_loss",
                result_code=2,
            ),
            raw_event("collection_stopped", 30),
        ]
        result = evaluate(chain(raw), experiment)
        self.assertEqual(result["evidence_gate"]["status"], "ADMISSIBLE")
        self.assertEqual(result["status"], "PASS")
        registration = result["oracles"][3]["clauses"]
        self.assertEqual(registration["activation_rejection"]["status"], "PASS")

    def test_expected_registration_rejection_is_checked_separately(self) -> None:
        experiment = plan()
        experiment["transition"]["registration_rejection_expected"] = True
        experiment["required_event_kinds"].append("registration")
        raw = passing_raw_events()
        raw.insert(
            11,
            raw_event(
                "registration",
                140_000_000,
                result_code=2,
                reason_code=4,
            ),
        )
        result = evaluate(chain(raw), experiment)
        registration = result["oracles"][3]["clauses"]
        self.assertEqual(registration["registration_rejection"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
