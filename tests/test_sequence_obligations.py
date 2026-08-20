"""Tests for obligations that depend on which sequence an episode carried."""

from __future__ import annotations

import copy
import unittest

from scripts.evaluator.evaluate_trace import evaluate
from scripts.evaluator.plan import PlanError, validate_plan
from scripts.evaluator.sequence_obligations import (
    SequenceObligationError,
    resolve_obligations,
)
from tests.helpers import chain, identity, plan, raw_event


RECLAIM_BRANCH = {
    "condition": "external_route_reclaimed_after_fault",
    "when_observed": {
        "expected_successor": "internal_hold",
        "completion_expected": True,
        "fallback_expected": False,
    },
}
# The branch deliberately leaves target_activation_count alone. A reclaim does
# enter the tested route twice, but the clause that reads that count judges
# repeated *public requests from the declared source route*, and a reclaim's
# request comes from the internal navigator the failsafe left the vehicle in.
# Declaring [2, 2] therefore gives the reclaim an obligation it does not owe --
# repeated-entry identity is the re-entry action's contract boundary, not the
# reclaim's, whose boundary is target_installed and is judged by the
# installation clause.


def process_exit_plan() -> dict:
    """A plan for the episode class that terminates the owning producer.

    The transition carries the obligations of the sequence that stops there: a
    fault, a completely installed fallback, one entry, no completion. The
    branch carries the ones that replace them when the route is reclaimed.
    """

    value = plan()
    value["schema_version"] = "1.4"
    value["transition"].update(
        {
            "expected_successor": "internal_land",
            "expected_fallback": "internal_land",
            "target_activation_count": [1, 1],
            "completion_expected": False,
            "fault_expected": True,
            "fallback_expected": True,
        }
    )
    value["required_event_kinds"] = sorted(
        set(value["required_event_kinds"]) | {"fault_detected", "fallback_triggered"}
    )
    value["workload"] = {
        "profile": "straight_line",
        "phases": ["public_takeoff", "route_activation", "safe_fallback"],
    }
    value["sequence_obligations"] = copy.deepcopy(RECLAIM_BRANCH)
    return value


def _prelude() -> list[dict]:
    source = identity("legacy_offboard", "source")
    target = identity("dynamic_external_mode", "target")
    return [
        raw_event("collection_started", 0),
        raw_event(
            "environment_attested",
            1_000_000,
            execution_environment=plan()["execution_environment"],
        ),
        raw_event("activation", 10_000_000, **source),
        raw_event("actuator_write", 115_000_000, command_subject_ns=100_000_000, **source),
        raw_event(
            "transition_requested",
            110_000_000,
            source_route="legacy_offboard",
            target_route="dynamic_external_mode",
        ),
        raw_event("revocation", 116_000_000, **source),
        raw_event("activation", 120_000_000, **target),
        raw_event("command_consumed", 122_000_000, command_subject_ns=115_000_000, **target),
        raw_event("controller_output", 124_000_000, command_subject_ns=115_000_000, **target),
        raw_event("allocator_output", 126_000_000, command_subject_ns=115_000_000, **target),
        raw_event("actuator_write", 128_000_000, command_subject_ns=115_000_000, **target),
        raw_event(
            "fault_detected",
            130_000_000,
            route="dynamic_external_mode",
            reason="owned_producer_process_exit",
        ),
        raw_event("revocation", 131_000_000, **target),
    ]


def _install(route: str, label: str, start_ns: int) -> list[dict]:
    marks = identity(route, label)
    return [
        raw_event("activation", start_ns, **marks),
        raw_event(
            "command_consumed", start_ns + 2_000_000, command_subject_ns=start_ns - 5_000_000, **marks
        ),
        raw_event(
            "controller_output", start_ns + 4_000_000, command_subject_ns=start_ns - 5_000_000, **marks
        ),
        raw_event(
            "allocator_output", start_ns + 6_000_000, command_subject_ns=start_ns - 5_000_000, **marks
        ),
        raw_event(
            "actuator_write", start_ns + 8_000_000, command_subject_ns=start_ns - 5_000_000, **marks
        ),
    ]


def terminated_only_events() -> list[dict]:
    """The producer was terminated and the fallback took over. No reclaim."""

    return chain(
        _prelude()
        + [raw_event("fallback_triggered", 132_000_000, route="internal_land")]
        + _install("internal_land", "fallback", 140_000_000)
        + [
            raw_event(
                "terminal_state", 170_000_000, route="internal_land", landed=True, disarmed=True
            ),
            raw_event("collection_stopped", 500_000_000),
        ]
    )


def reclaimed_events() -> list[dict]:
    """The producer was terminated and then reclaimed the tested route."""

    return chain(
        _prelude()
        + [raw_event("fallback_triggered", 132_000_000, route="internal_land")]
        + _install("dynamic_external_mode", "reclaim", 140_000_000)
        + [
            raw_event("completion", 155_000_000, route="dynamic_external_mode"),
            raw_event("revocation", 156_000_000, **identity("dynamic_external_mode", "reclaim")),
        ]
        + _install("internal_hold", "successor", 160_000_000)
        + [
            raw_event(
                "terminal_state", 175_000_000, route="internal_hold", landed=True, disarmed=True
            ),
            raw_event("collection_stopped", 500_000_000),
        ]
    )


class PlanValidationTests(unittest.TestCase):
    def test_a_conditional_plan_validates(self):
        validate_plan(process_exit_plan())

    def test_a_conditional_plan_needs_the_block(self):
        value = process_exit_plan()
        del value["sequence_obligations"]
        with self.assertRaises(PlanError):
            validate_plan(value)

    def test_an_earlier_plan_stays_valid_and_unchanged(self):
        # Schema 1.2 and 1.3 must keep evaluating exactly as before, so every
        # retained study stays reproducible.
        validate_plan(plan())

    def test_an_unsupported_condition_is_refused(self):
        value = process_exit_plan()
        value["sequence_obligations"]["condition"] = "whatever_the_tester_says"
        with self.assertRaises(PlanError):
            validate_plan(value)

    def test_a_branch_identical_to_the_transition_is_refused(self):
        value = process_exit_plan()
        value["sequence_obligations"]["when_observed"] = {
            "completion_expected": value["transition"]["completion_expected"]
        }
        with self.assertRaises(PlanError):
            validate_plan(value)

    def test_a_branch_may_not_restate_a_class_property(self):
        value = process_exit_plan()
        value["sequence_obligations"]["when_observed"]["target_route"] = "legacy_offboard"
        with self.assertRaises(PlanError):
            validate_plan(value)

    def test_an_illegal_branch_is_refused(self):
        # A fallback without a fault is inconsistent whichever branch declares
        # it, so the plan is refused rather than being valid one way only.
        value = process_exit_plan()
        value["sequence_obligations"]["when_observed"] = {
            "fault_expected": False,
            "fallback_expected": True,
        }
        with self.assertRaises(PlanError):
            validate_plan(value)

    def test_required_event_kinds_cover_both_branches(self):
        value = process_exit_plan()
        value["required_event_kinds"] = [
            kind for kind in value["required_event_kinds"] if kind != "completion"
        ]
        # The branch expects a completion, so the evidence for it must be
        # collected whichever way the condition goes.
        with self.assertRaises(PlanError):
            validate_plan(value)


class ResolutionTests(unittest.TestCase):
    def test_a_plan_without_the_block_resolves_to_itself(self):
        value = plan()
        resolved, resolution = resolve_obligations(terminated_only_events(), value)
        self.assertIs(resolved, value)
        self.assertIsNone(resolution)

    def test_the_condition_holds_only_when_the_route_installs_again(self):
        _, reclaimed = resolve_obligations(reclaimed_events(), process_exit_plan())
        _, stopped = resolve_obligations(terminated_only_events(), process_exit_plan())
        self.assertTrue(reclaimed["held"])
        self.assertEqual(reclaimed["branch"], "when_observed")
        self.assertFalse(stopped["held"])
        self.assertEqual(stopped["branch"], "when_absent")

    def test_the_applied_obligations_are_named(self):
        _, resolution = resolve_obligations(reclaimed_events(), process_exit_plan())
        self.assertEqual(
            resolution["applied_obligations"],
            {
                "completion_expected": True,
                "expected_successor": "internal_hold",
                "fallback_expected": False,
            },
        )

    def test_resolution_does_not_mutate_the_plan(self):
        value = process_exit_plan()
        before = copy.deepcopy(value)
        resolve_obligations(reclaimed_events(), value)
        self.assertEqual(value, before)

    def test_an_unsupported_condition_is_refused_at_resolution(self):
        value = process_exit_plan()
        value["sequence_obligations"]["condition"] = "not_a_condition"
        with self.assertRaises(SequenceObligationError):
            resolve_obligations(reclaimed_events(), value)


class EndToEndTests(unittest.TestCase):
    def test_both_sequences_pass_under_the_conditional_plan(self):
        for events in (terminated_only_events(), reclaimed_events()):
            result = evaluate(events, process_exit_plan())
            self.assertEqual(result["evidence_gate"]["status"], "ADMISSIBLE")
            self.assertEqual(result["status"], "PASS", result["sequence_obligations"])

    def test_the_evaluation_records_which_branch_was_applied(self):
        result = evaluate(reclaimed_events(), process_exit_plan())
        self.assertEqual(result["sequence_obligations"]["branch"], "when_observed")
        self.assertEqual(
            result["sequence_obligations"]["condition"],
            "external_route_reclaimed_after_fault",
        )

    def test_the_branch_is_doing_real_work(self):
        # The whole point is that the two branches are not interchangeable. A
        # reclaim judged by the terminate-only obligations must not pass, or
        # the conditional plan would be decoration.
        flat = process_exit_plan()
        del flat["sequence_obligations"]
        flat["schema_version"] = "1.3"
        result = evaluate(reclaimed_events(), flat)
        self.assertNotEqual(result["status"], "PASS")

    def test_an_earlier_plan_records_no_resolution(self):
        result = evaluate(terminated_only_events(), process_exit_plan())
        self.assertIn("sequence_obligations", result)
        flat = process_exit_plan()
        del flat["sequence_obligations"]
        flat["schema_version"] = "1.3"
        self.assertNotIn("sequence_obligations", evaluate(terminated_only_events(), flat))


if __name__ == "__main__":
    unittest.main()
