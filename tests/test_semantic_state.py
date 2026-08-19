"""Tests for the deterministic semantic-state extractor."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.state.semantic_state import (
    FAULT_CLASSES,
    FRESHNESS_STATES,
    LIFECYCLE_PHASES,
    MODE_LABEL_FIELDS,
    MOTION_PHASES,
    MotionContext,
    SemanticStateError,
    derive_trajectory,
    is_instrumented,
    mode_label_fields,
    observation_dependence,
    public_events,
    with_perturbed_mode_labels,
    without_mode_labels,
)
from tests.helpers import chain, identity, passing_events, raw_event


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "data/schemas/semantic_state.schema.json"


def instrumented(kind: str, timestamp_ns: int, **values: object) -> dict[str, object]:
    """An event that only the tracked observability instrumentation produces."""

    return raw_event(
        kind,
        timestamp_ns,
        raw_source_domain="px4_boot_us",
        raw_timestamp_us=timestamp_ns // 1000,
        **values,
    )


def installed_route(label: str, route: str, start_ns: int, *, subject_ns: int) -> list:
    marks = identity(route, label)
    return [
        instrumented("activation", start_ns, **marks),
        instrumented(
            "command_consumed",
            start_ns + 2_000_000,
            command_subject_ns=subject_ns,
            **marks,
        ),
        instrumented(
            "controller_output",
            start_ns + 4_000_000,
            command_subject_ns=subject_ns,
            **marks,
        ),
        instrumented(
            "allocator_output",
            start_ns + 6_000_000,
            command_subject_ns=subject_ns,
            **marks,
        ),
        instrumented(
            "actuator_write",
            start_ns + 8_000_000,
            command_subject_ns=subject_ns,
            **marks,
        ),
    ]


class SemanticStateTests(unittest.TestCase):
    def test_normal_transition_installs_target_then_successor(self) -> None:
        trajectory = derive_trajectory(passing_events())
        final = trajectory.final_state
        self.assertEqual(final.phase, "terminal")
        self.assertEqual(final.lineage, "complete")
        self.assertTrue(final.successor_installed)
        self.assertTrue(final.source_revoked)
        self.assertIn("target_installed", trajectory.coverage.contract_boundaries)
        self.assertIn("source_revoked", trajectory.coverage.contract_boundaries)
        self.assertIn("request_external_route", trajectory.coverage.actions)

    def test_equivalent_evidence_produces_one_trajectory_digest(self) -> None:
        first = derive_trajectory(passing_events())
        second = derive_trajectory(passing_events())
        self.assertEqual(first.digest(), second.digest())
        self.assertEqual(first.state_keys(), second.state_keys())

    def test_declared_mode_label_never_changes_the_derived_state(self) -> None:
        events = passing_events()
        for index, event in enumerate(events):
            event["nav_state"] = index
            event["flight_mode"] = "AUTO.LOITER"
        baseline = derive_trajectory(events)
        self.assertEqual(mode_label_fields(events), ["flight_mode", "nav_state"])
        self.assertEqual(
            baseline.digest(), derive_trajectory(without_mode_labels(events)).digest()
        )
        self.assertEqual(
            baseline.digest(),
            derive_trajectory(with_perturbed_mode_labels(events)).digest(),
        )

    def test_stale_command_is_visible_without_any_mode_label(self) -> None:
        marks = identity("legacy_offboard", "target")
        events = chain(
            [
                raw_event("collection_started", 0),
                *installed_route("target", "legacy_offboard", 10_000_000, subject_ns=9_000_000),
                instrumented(
                    "command_consumed",
                    900_000_000,
                    command_subject_ns=100_000_000,
                    **marks,
                ),
                raw_event("collection_stopped", 1_000_000_000),
            ]
        )
        trajectory = derive_trajectory(events, maximum_command_age_ns=200_000_000)
        self.assertEqual(trajectory.final_state.freshness, "stale")
        self.assertEqual(trajectory.final_state.command_age_ns, 800_000_000)
        self.assertIn("command_stale", trajectory.coverage.contract_boundaries)
        self.assertNotIn("nav_state", set().union(*(set(event) for event in events)))

    def test_freshness_buckets_follow_the_frozen_bound(self) -> None:
        def age(consumed_ns: int, subject_ns: int) -> str:
            events = chain(
                [
                    raw_event("collection_started", 0),
                    *installed_route(
                        "target", "legacy_offboard", 10_000_000, subject_ns=9_000_000
                    ),
                    instrumented(
                        "command_consumed",
                        consumed_ns,
                        command_subject_ns=subject_ns,
                        **identity("legacy_offboard", "target"),
                    ),
                ]
            )
            return derive_trajectory(
                events, maximum_command_age_ns=200_000_000
            ).final_state.freshness

        self.assertEqual(age(500_000_000, 450_000_000), "fresh")
        self.assertEqual(age(500_000_000, 350_000_000), "aging")
        self.assertEqual(age(500_000_000, 250_000_000), "stale")

    def test_route_epoch_distinguishes_repeated_entry_to_one_route(self) -> None:
        first = identity("legacy_offboard", "first")
        second = identity("legacy_offboard", "second")
        events = chain(
            [
                raw_event("collection_started", 0),
                instrumented("activation", 10_000_000, **first),
                instrumented("revocation", 20_000_000, **first),
                raw_event(
                    "transition_requested",
                    25_000_000,
                    source_route="internal_hold",
                    target_route="legacy_offboard",
                ),
                instrumented("activation", 30_000_000, **second),
            ]
        )
        trajectory = derive_trajectory(events)
        self.assertEqual(trajectory.final_state.route_epoch_index, 2)
        self.assertEqual(trajectory.final_state.route_epoch, second["route_epoch"])
        self.assertEqual(trajectory.final_state.re_entry_count, 1)
        self.assertNotEqual(
            trajectory.steps[1].state.key(), trajectory.final_state.key()
        )

    def test_owner_change_updates_authority_without_a_new_activation(self) -> None:
        marks = identity("mode_executor", "target")
        moved = dict(marks, lifecycle_owner="lifecycle-handover")
        events = chain(
            [
                raw_event("collection_started", 0),
                instrumented("activation", 10_000_000, **marks),
                instrumented("owner_changed", 20_000_000, **moved),
            ]
        )
        final = derive_trajectory(events).final_state
        self.assertEqual(final.lifecycle_owner, "lifecycle-handover")
        self.assertEqual(final.activation_id, marks["activation_id"])
        self.assertEqual(final.owner_class, "external")

    def test_fallback_installation_is_recorded_after_a_fault(self) -> None:
        target = identity("legacy_offboard", "target")
        events = chain(
            [
                raw_event("collection_started", 0),
                *installed_route("target", "legacy_offboard", 10_000_000, subject_ns=9_000_000),
                raw_event(
                    "fault_detected",
                    30_000_000,
                    route="legacy_offboard",
                    reason="source_process_exit",
                ),
                raw_event("fallback_triggered", 31_000_000, route="internal_land"),
                instrumented("revocation", 32_000_000, **target),
                *installed_route(
                    "fallback", "internal_land", 40_000_000, subject_ns=39_000_000
                ),
                raw_event("collection_stopped", 90_000_000),
            ]
        )
        trajectory = derive_trajectory(events)
        final = trajectory.final_state
        self.assertEqual(final.fault_class, "process_exit")
        self.assertTrue(final.fault_observed)
        self.assertTrue(final.fallback_installed)
        self.assertIn("fallback_installed", trajectory.coverage.contract_boundaries)

    def test_reduced_observation_loses_lineage_freshness_and_boundaries(self) -> None:
        events = chain(
            [
                raw_event("collection_started", 0),
                raw_event(
                    "transition_requested",
                    5_000_000,
                    source_route="internal_hold",
                    target_route="legacy_offboard",
                ),
                *installed_route(
                    "target", "legacy_offboard", 10_000_000, subject_ns=9_000_000
                ),
                raw_event("completion", 30_000_000, route="legacy_offboard"),
                raw_event("collection_stopped", 40_000_000),
            ]
        )
        self.assertEqual(len(public_events(events)), 4)
        full = derive_trajectory(events)
        reduced = derive_trajectory(public_events(events))
        dependence = observation_dependence(full, reduced)
        self.assertFalse(dependence["lineage_observable_without_instrumentation"])
        self.assertFalse(dependence["freshness_observable_without_instrumentation"])
        self.assertEqual(reduced.coverage.contract_boundaries, {})
        self.assertTrue(dependence["lost_contract_boundaries"])
        self.assertFalse(dependence["final_state_equal"])

    def test_instrumented_events_are_identified_by_raw_provenance(self) -> None:
        self.assertTrue(is_instrumented(instrumented("activation", 1)))
        self.assertFalse(is_instrumented(raw_event("completion", 1)))

    def test_action_history_is_bounded(self) -> None:
        events = [raw_event("collection_started", 0)]
        for index in range(6):
            events.append(
                raw_event(
                    "adjacent_request",
                    (index + 1) * 1_000_000,
                    route="internal_land",
                )
            )
        trajectory = derive_trajectory(chain(events), history_limit=3)
        self.assertEqual(
            trajectory.final_state.action_history,
            ("adjacent_request", "adjacent_request", "adjacent_request"),
        )

    def test_semantic_edge_carries_action_and_timing_bucket(self) -> None:
        events = chain(
            [
                raw_event("collection_started", 0),
                *installed_route("target", "legacy_offboard", 1_000_000_000, subject_ns=999_000_000),
                raw_event("completion", 6_000_000_000, route="legacy_offboard"),
            ]
        )
        trajectory = derive_trajectory(events)
        steps = [step for step in trajectory.steps if step.action is not None]
        self.assertEqual([step.action for step in steps], ["complete"])
        self.assertEqual(steps[0].timing_bucket, "t3_8s")
        self.assertEqual(len(trajectory.coverage.edges), 1)

    def test_motion_context_is_unobserved_until_a_physical_source_supplies_it(self) -> None:
        events = passing_events()
        self.assertEqual(derive_trajectory(events).final_state.motion_phase, "unobserved")
        motion = MotionContext([(0, "ground"), (120_000_000, "translating")])
        trajectory = derive_trajectory(events, motion=motion)
        self.assertEqual(trajectory.final_state.motion_phase, "translating")
        self.assertEqual(trajectory.steps[0].state.motion_phase, "ground")

    def test_motion_context_refuses_unsupported_or_unordered_samples(self) -> None:
        with self.assertRaises(SemanticStateError):
            MotionContext([(0, "cruising")])
        with self.assertRaises(SemanticStateError):
            MotionContext([(10, "hover"), (5, "ground")])

    def test_fold_refuses_incomplete_or_inconsistent_evidence(self) -> None:
        with self.assertRaises(SemanticStateError):
            derive_trajectory([])
        with self.assertRaises(SemanticStateError):
            derive_trajectory(
                [
                    raw_event("collection_started", 0, sequence=1),
                    raw_event("collection_stopped", 1, sequence=0),
                ]
            )
        mixed = chain([raw_event("collection_started", 0), raw_event("collection_stopped", 1)])
        mixed[1]["run_id"] = "another-run"
        with self.assertRaises(SemanticStateError):
            derive_trajectory(mixed)
        with self.assertRaises(SemanticStateError):
            derive_trajectory(passing_events(), maximum_command_age_ns=0)
        with self.assertRaises(SemanticStateError):
            derive_trajectory(passing_events(), history_limit=0)

    def test_authority_event_without_complete_identity_is_refused(self) -> None:
        partial = dict(identity("legacy_offboard", "target"))
        partial.pop("writer_id")
        events = chain(
            [
                raw_event("collection_started", 0),
                raw_event("activation", 10_000_000, **partial),
            ]
        )
        with self.assertRaises(SemanticStateError):
            derive_trajectory(events)

    def test_command_consumed_before_its_subject_time_is_refused(self) -> None:
        events = chain(
            [
                raw_event("collection_started", 0),
                *installed_route("target", "legacy_offboard", 10_000_000, subject_ns=900_000_000),
            ]
        )
        with self.assertRaises(SemanticStateError):
            derive_trajectory(events)

    def test_state_record_matches_the_tracked_schema(self) -> None:
        record = derive_trajectory(passing_events()).final_state.as_dict()
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        try:
            import jsonschema
        except ImportError:
            self.assertEqual(set(record), set(schema["required"]))
            self.assertIn(record["lifecycle"]["phase"], schema["$defs"]["lifecycle_phase"]["enum"])
            return
        jsonschema.Draft202012Validator(schema).validate(record)

    def test_model_constants_equal_the_tracked_schema_enums(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            list(LIFECYCLE_PHASES), schema["$defs"]["lifecycle_phase"]["enum"]
        )
        self.assertEqual(
            list(FRESHNESS_STATES), schema["$defs"]["freshness_state"]["enum"]
        )
        self.assertEqual(list(FAULT_CLASSES), schema["$defs"]["fault_class"]["enum"])
        self.assertEqual(list(MOTION_PHASES), schema["$defs"]["motion_phase"]["enum"])

    def test_mode_label_fields_are_declared_and_absent_from_the_state_key(self) -> None:
        key = derive_trajectory(passing_events()).final_state.key()
        for name in MODE_LABEL_FIELDS:
            self.assertNotIn(name, key)


if __name__ == "__main__":
    unittest.main()
