"""Tests for the proposed core action set and its precondition replay."""

from __future__ import annotations

from dataclasses import replace
import unittest

from scripts.corpus.core_actions import (
    AVAILABILITY,
    CORE_ACTIONS,
    MECHANISMS,
    CoreActionError,
    core_action_records,
    validate_declarations,
)
from scripts.state.semantic_state import SemanticState, derive_trajectory
from tests.helpers import chain, raw_event
from tests.test_semantic_state import installed_route


def action(action_id: str):
    return next(item for item in CORE_ACTIONS if item.action_id == action_id)


class CoreActionTests(unittest.TestCase):
    def test_declarations_are_valid(self) -> None:
        validate_declarations()
        records = core_action_records()
        self.assertEqual(len(records), len(CORE_ACTIONS))
        for record in records:
            self.assertEqual(set(record["availability"]), set(MECHANISMS))
            for status in record["availability"].values():
                self.assertIn(status, AVAILABILITY)

    def test_no_precondition_holds_in_the_empty_state(self) -> None:
        for item in CORE_ACTIONS:
            with self.subTest(action=item.action_id):
                self.assertFalse(item.precondition(SemanticState()))

    def test_a_precondition_that_is_always_true_is_refused(self) -> None:
        broken = replace(action("adjacent_land_request"), precondition=lambda state: True)
        original = CORE_ACTIONS
        try:
            import scripts.corpus.core_actions as module

            module.CORE_ACTIONS = (broken,)
            with self.assertRaises(CoreActionError):
                validate_declarations()
        finally:
            import scripts.corpus.core_actions as module

            module.CORE_ACTIONS = original

    def test_stall_precondition_needs_installed_external_authority(self) -> None:
        stall = action("stop_owned_setpoint_stream")
        installed = SemanticState(
            route="legacy_offboard",
            route_family="external_offboard",
            lifecycle_owner="producer",
            lineage_stages=(
                "command_consumed",
                "controller_output",
                "allocator_output",
                "actuator_write",
            ),
            phase="executing",
        )
        self.assertTrue(stall.precondition(installed))
        self.assertFalse(stall.precondition(replace(installed, lineage_stages=())))
        self.assertFalse(stall.precondition(replace(installed, fault_observed=True)))
        self.assertFalse(stall.precondition(replace(installed, phase="terminal")))

    def test_restart_precondition_depends_on_an_earlier_action(self) -> None:
        restart = action("restart_producer_after_loss")
        after_fallback = SemanticState(
            route="internal_land",
            route_family="internal_safe",
            lifecycle_owner="px4_commander",
            lineage_stages=(
                "command_consumed",
                "controller_output",
                "allocator_output",
                "actuator_write",
            ),
            phase="executing",
            fault_class="process_exit",
        )
        self.assertTrue(restart.precondition(after_fallback))
        # Without the producer loss the same installed safe route is not enough.
        self.assertFalse(restart.precondition(replace(after_fallback, fault_class="none")))

    def test_re_entry_marker_uses_the_producer_cycle_not_the_derived_phase(self) -> None:
        re_entry = action("re_enter_route_after_successor")
        first = raw_event(
            "transition_requested",
            1_000_000,
            source_route="internal_hold",
            target_route="legacy_offboard",
        )
        repeat = dict(first, cycle=1)
        empty = SemanticState()
        self.assertFalse(re_entry.marker(first, empty, replace(empty, phase="re_entry")))
        self.assertTrue(re_entry.marker(repeat, empty, empty))

    def test_precondition_is_evaluated_on_the_state_before_the_firing(self) -> None:
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
                raw_event(
                    "fault_detected",
                    30_000_000,
                    route="legacy_offboard",
                    reason="setpoint_stream_stalled_while_proof_of_life_continued",
                ),
                raw_event("collection_stopped", 40_000_000),
            ]
        )
        trajectory = derive_trajectory(events)
        stall = action("stop_owned_setpoint_stream")
        previous = SemanticState()
        fired = []
        for event, step in zip(events, trajectory.steps):
            if stall.marker(event, previous, step.state):
                fired.append((previous, step.state))
            previous = step.state
        self.assertEqual(len(fired), 1)
        before, after = fired[0]
        # The stall is legal because the route was installed before it fired,
        # and the state it produces already records the fault.
        self.assertTrue(stall.precondition(before))
        self.assertEqual(before.lineage, "complete")
        self.assertFalse(before.fault_observed)
        self.assertTrue(after.fault_observed)
        self.assertFalse(stall.precondition(after))

    def test_a_wired_action_anchors_its_timing_on_one_of_its_markers(self) -> None:
        from scripts.corpus.core_actions import OBSERVABLE_LIVE_MARKERS

        for item in CORE_ACTIONS:
            if item.live_profile is None or item.live_profile.application == "launch":
                # A launch configuration is in effect before anything is
                # observed, so it waits on no marker and has no anchor.
                continue
            with self.subTest(action=item.action_id):
                self.assertIn(item.live_profile.timing_anchor, item.live_markers)
                self.assertIn(item.live_profile.timing_anchor, OBSERVABLE_LIVE_MARKERS)

    def test_an_anchor_outside_the_declared_markers_is_refused(self) -> None:
        import scripts.corpus.core_actions as module
        from dataclasses import replace as data_replace

        wired = next(item for item in CORE_ACTIONS if item.live_profile is not None)
        broken = data_replace(
            wired,
            live_profile=data_replace(wired.live_profile, timing_anchor="successor_installed"),
        )
        original = module.CORE_ACTIONS
        try:
            module.CORE_ACTIONS = (broken,)
            with self.assertRaises(CoreActionError):
                validate_declarations()
        finally:
            module.CORE_ACTIONS = original

    def test_a_launch_configuration_has_no_timing_and_waits_on_nothing(self) -> None:
        from dataclasses import replace as data_replace
        import scripts.corpus.core_actions as module

        withhold = action("withhold_health_reply")
        self.assertEqual(withhold.live_profile.application, "launch")
        self.assertEqual(withhold.live_profile.timing_offsets_ns, ())
        self.assertEqual(withhold.live_markers, ())
        # It selects the rejection path, so it expects no activation.
        self.assertFalse(withhold.live_profile.target_activation_expected)
        self.assertTrue(withhold.live_profile.activation_rejection_expected)

        # Giving it timing bins would invent a choice the generator does not
        # have, and is refused.
        broken = data_replace(
            withhold,
            live_profile=data_replace(
                withhold.live_profile, timing_offsets_ns=(0, 1, 2, 3, 4)
            ),
        )
        original = module.CORE_ACTIONS
        try:
            module.CORE_ACTIONS = (broken,)
            with self.assertRaises(CoreActionError):
                validate_declarations()
        finally:
            module.CORE_ACTIONS = original

    def test_every_action_targets_a_boundary_and_states_cleanup(self) -> None:
        for item in CORE_ACTIONS:
            with self.subTest(action=item.action_id):
                self.assertTrue(item.target_boundaries)
                self.assertTrue(item.cleanup_text.strip())
                self.assertTrue(item.summary.strip())

if __name__ == "__main__":
    unittest.main()
