"""Tests for launching one episode that admits a whole sequence."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import types
import unittest

from scripts.corpus.episode_classes import episode_class
from scripts.evaluator.plan import validate_plan
from scripts.evaluator.sequence_obligations import SEQUENCE_CONDITIONS
from scripts.runtime.closed_loop_policy import create_policy
from scripts.runtime.make_plan import create_plan
from scripts.runtime.run_sitl import RuntimeFailure, resolve_episode_class


CLASS_ID = "process_exit_reclaim"
BOUNDS = {
    "terminate_owning_producer": [3_500_000_000, 6_500_000_000],
    "restart_producer_after_loss": [500_000_000, 2_500_000_000],
}
ENVIRONMENT = {
    "environment_id": "target-lab-a",
    "execution_host_id": "runner-a",
    "collector_host_id": "collector-a",
    "target_kind": "sitl",
    "architecture": "aarch64",
    "operating_system": "Ubuntu 24.04 Noble container",
    "px4_binary_digest": "sha256:" + "2" * 64,
    "environment_manifest_digest": "sha256:" + "3" * 64,
}
ATTESTATION = {
    "attestation_payload": {
        "container": {
            "candidate": {
                "repository_revision": "1" * 40,
                "locks": {"dependencies": "sha256:" + "4" * 64},
            }
        }
    },
    "execution_environment": ENVIRONMENT,
}
THRESHOLDS = {
    "revocation_deadline_ns": 1,
    "installation_deadline_ns": 1,
    "maximum_effect_gap_ns": 1,
    "maximum_command_age_ns": 1,
    "successor_deadline_ns": 1,
    "fallback_deadline_ns": 1,
}


def policy(mechanism: str = "legacy_offboard"):
    return create_policy(
        strategy="official_sequence",
        seed=None,
        mechanism=mechanism,
        class_id=CLASS_ID,
        timing_bounds_ns=BOUNDS,
        covered_units=set(),
    )


def class_plan(mechanism: str = "legacy_offboard") -> dict:
    """The plan a class launch generates, as qualification_attempt builds it."""

    episode = episode_class(CLASS_ID)
    obligations = episode.obligations(mechanism)
    return create_plan(
        attestation=ATTESTATION,
        run_id="closed-loop-001",
        plan_id="closed-loop-001-plan",
        source_route="internal_hold",
        target_route=mechanism,
        expected_successor=obligations["expected_successor"],
        expected_fallback=obligations["expected_fallback"],
        target_activation_expected=obligations["target_activation_expected"],
        target_activation_count=obligations["target_activation_count"],
        registration_rejection_expected=obligations["registration_rejection_expected"],
        activation_rejection_expected=obligations["activation_rejection_expected"],
        completion_expected=obligations["completion_expected"],
        fault_expected=obligations["fault_expected"],
        fallback_expected=obligations["fallback_expected"],
        thresholds=THRESHOLDS,
        workload={
            "profile": episode.workload_profile,
            "phases": list(episode.workload_phases),
            "injection_phase": episode.injection_phase,
        },
        sequence_obligations=episode.sequence_obligations(),
    )


class ClassPlanTests(unittest.TestCase):
    def test_a_class_launch_generates_a_conditional_plan(self):
        plan = class_plan()
        validate_plan(plan)
        self.assertEqual(plan["schema_version"], "1.4")
        self.assertIn(
            plan["sequence_obligations"]["condition"], SEQUENCE_CONDITIONS
        )

    def test_the_plan_collects_the_evidence_both_branches_need(self):
        plan = class_plan()
        # The baseline owes a fallback and the branch owes a completion, so
        # both have to be collected whichever way the episode goes.
        for kind in ("fault_detected", "fallback_triggered", "completion"):
            self.assertIn(kind, plan["required_event_kinds"])

    def test_the_fallback_follows_the_mechanism(self):
        self.assertEqual(
            class_plan("legacy_offboard")["transition"]["expected_fallback"],
            "internal_land",
        )
        self.assertEqual(
            class_plan("dynamic_external_mode")["transition"]["expected_fallback"],
            "internal_rtl",
        )

    def test_the_successor_matches_what_the_workload_will_request(self):
        # Flown once with the branch naming a different successor: the reclaim
        # released to the route the workload was configured for and the plan
        # reported it as never installed.
        plan = class_plan()
        self.assertEqual(plan["transition"]["expected_successor"], "internal_hold")
        self.assertNotIn(
            "expected_successor", plan["sequence_obligations"]["when_observed"]
        )

    def test_the_baseline_and_the_branch_disagree_where_they_must(self):
        plan = class_plan()
        branch = plan["sequence_obligations"]["when_observed"]
        self.assertTrue(plan["transition"]["fallback_expected"])
        self.assertFalse(branch["fallback_expected"])
        self.assertFalse(plan["transition"]["completion_expected"])
        self.assertTrue(branch["completion_expected"])
        # The fault is not conditional: it is two-sided and the class installs
        # its fault mode at launch.
        self.assertTrue(plan["transition"]["fault_expected"])
        self.assertNotIn("fault_expected", branch)


class LaunchGuardTests(unittest.TestCase):
    def _arguments(self, directory: Path, **overrides):
        path = directory / "policy.json"
        path.write_text(json.dumps(overrides.pop("policy", policy())), encoding="utf-8")
        values = {
            "episode_class": CLASS_ID,
            "strategy_decision_path": None,
            "strategy_policy_path": path,
            "mechanism": "legacy_offboard",
            "fault_mode": "process_exit",
            "workload_profile": "straight_line",
            "scheduled_action": "",
        }
        values.update(overrides)
        return types.SimpleNamespace(**values)

    def test_a_consistent_launch_resolves(self):
        with tempfile.TemporaryDirectory() as directory:
            episode = resolve_episode_class(self._arguments(Path(directory)))
            self.assertEqual(episode.class_id, CLASS_ID)

    def test_no_class_means_the_single_action_path(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self._arguments(Path(directory), episode_class=None)
            self.assertIsNone(resolve_episode_class(args))

    def test_a_class_without_its_policy_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self._arguments(Path(directory), strategy_policy_path=None)
            with self.assertRaises(RuntimeFailure):
                resolve_episode_class(args)

    def test_a_class_with_a_single_action_decision_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self._arguments(
                Path(directory), strategy_decision_path=Path(directory) / "d.json"
            )
            with self.assertRaises(RuntimeFailure):
                resolve_episode_class(args)

    def test_a_class_with_a_scheduled_action_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self._arguments(Path(directory), scheduled_action="stop_owned_setpoint_stream")
            with self.assertRaises(RuntimeFailure):
                resolve_episode_class(args)

    def test_a_launch_whose_fault_mode_differs_is_refused(self):
        # One launch installs one fault mode, and every action the policy may
        # select has to be reachable under it.
        with tempfile.TemporaryDirectory() as directory:
            args = self._arguments(Path(directory), fault_mode="setpoint_stall")
            with self.assertRaises(RuntimeFailure):
                resolve_episode_class(args)

    def test_a_policy_frozen_for_another_mechanism_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self._arguments(
                Path(directory), policy=policy("dynamic_external_mode")
            )
            with self.assertRaises(RuntimeFailure):
                resolve_episode_class(args)

    def test_a_tampered_policy_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            value = policy()
            value["corpus"] = ["terminate_owning_producer"]
            args = self._arguments(Path(directory), policy=value)
            with self.assertRaises(RuntimeFailure):
                resolve_episode_class(args)

    def test_a_launch_whose_workload_differs_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self._arguments(Path(directory), workload_profile="hover")
            with self.assertRaises(RuntimeFailure):
                resolve_episode_class(args)


if __name__ == "__main__":
    unittest.main()
