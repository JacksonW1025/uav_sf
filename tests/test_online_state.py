"""Tests for the in-flight state projection and its agreement measurement."""

from __future__ import annotations

import unittest

from scripts.corpus.core_actions import CORE_ACTIONS, core_action, validate_declarations
from scripts.corpus.online_state_check import _disagreement, _value_at
from scripts.state.online_state import (
    OFFBOARD_NAV_STATE,
    OnlineState,
    OnlineStateError,
    derive_online_trajectory,
    merge_records,
    state_at,
    validate_vocabularies,
)


def record(kind: str, monotonic_ns: int, **payload):
    return {"kind": kind, "received_monotonic_ns": monotonic_ns, **payload}


def offboard_episode() -> list[dict]:
    """A minimal offboard episode: takeoff, activation, motion, completion."""

    return [
        record("attempt_started", 100, mechanism="legacy_offboard"),
        record("vehicle_land_detected", 200, landed=True),
        record("takeoff_requested", 300),
        record("vehicle_land_detected", 400, landed=False),
        record("vehicle_status", 500, nav_state=17),
        record("offboard_requested", 600),
        record("offboard_observed_active", 700, cycle=0),
        record("vehicle_status", 800, nav_state=OFFBOARD_NAV_STATE),
        record("motion_phase_entered", 900, along_track_progress_m=0.8),
        record("motion_phase_completed", 1000, along_track_progress_m=2.5),
        record("completion", 1100, route="legacy_offboard"),
        record("successor_requested", 1200, route="internal_hold"),
        record("successor_observed_active", 1300, route="internal_hold"),
        record("vehicle_status", 1400, nav_state=4),
    ]


class OnlineStateTests(unittest.TestCase):
    def test_vocabularies_match_the_offline_model(self):
        validate_vocabularies()

    def test_lineage_is_never_claimed(self):
        steps = derive_online_trajectory(offboard_episode(), mechanism="legacy_offboard")
        self.assertTrue(steps)
        for step in steps:
            self.assertEqual(step.state.lineage, "unobservable")

    def test_authority_follows_the_episode(self):
        steps = derive_online_trajectory(offboard_episode(), mechanism="legacy_offboard")
        self.assertEqual(state_at(steps, 50).authority_family, "unknown")
        self.assertEqual(state_at(steps, 550).authority_family, "internal_navigator")
        active = state_at(steps, 850)
        self.assertEqual(active.authority_family, "external_offboard")
        self.assertTrue(active.tested_route_active)
        self.assertTrue(active.external_authority)
        final = state_at(steps, 1400)
        self.assertEqual(final.authority_family, "internal_safe")
        self.assertFalse(final.tested_route_active)
        self.assertTrue(final.completion_observed)
        self.assertTrue(final.successor_installed)

    def test_airborne_then_landed_is_terminal(self):
        steps = derive_online_trajectory(
            offboard_episode() + [record("vehicle_land_detected", 1500, landed=True)],
            mechanism="legacy_offboard",
        )
        final = state_at(steps, 1500)
        self.assertTrue(final.terminal)
        self.assertFalse(final.holds_authority)

    def test_ground_contact_before_takeoff_is_not_terminal(self):
        steps = derive_online_trajectory(offboard_episode(), mechanism="legacy_offboard")
        self.assertFalse(state_at(steps, 250).terminal)

    def test_dynamic_navigation_state_is_learned_from_registration(self):
        records = [
            record("registration_reply", 100, mode_id=23, success=True),
            record("transition_requested", 200, source_route="internal_hold", target_route="dynamic_external_mode"),
            record("vehicle_status", 300, nav_state=23),
        ]
        steps = derive_online_trajectory(records, mechanism="dynamic_external_mode")
        state = state_at(steps, 300)
        self.assertEqual(state.authority_family, "external_dynamic")
        self.assertEqual(state.registration_state, "accepted")
        # Without the registration reply the same navigation state is not the
        # tested route, because nothing established which identifier it has.
        blind = derive_online_trajectory(records[1:], mechanism="dynamic_external_mode")
        self.assertEqual(state_at(blind, 300).authority_family, "internal_navigator")

    def test_a_request_away_from_the_tested_route_is_not_an_activation(self):
        steps = derive_online_trajectory(
            [
                record(
                    "transition_requested",
                    100,
                    source_route="legacy_offboard",
                    target_route="internal_hold",
                )
            ],
            mechanism="legacy_offboard",
        )
        self.assertEqual(state_at(steps, 100).activation_state, "none")

    def test_a_safe_route_taking_over_unasked_shows_the_fallback(self):
        records = offboard_episode()[:8] + [record("vehicle_status", 900, nav_state=5)]
        steps = derive_online_trajectory(records, mechanism="legacy_offboard")
        state = state_at(steps, 900)
        self.assertTrue(state.fallback_installed)
        self.assertEqual(state.authority_family, "internal_safe")
        self.assertTrue(state.internal_authority)

    def test_a_handover_the_producer_asked_for_is_not_a_fallback(self):
        records = offboard_episode()[:8] + [
            record("successor_requested", 850, route="internal_hold"),
            record("vehicle_status", 900, nav_state=4),
        ]
        steps = derive_online_trajectory(records, mechanism="legacy_offboard")
        state = state_at(steps, 900)
        self.assertFalse(state.fallback_installed)
        self.assertEqual(state.authority_family, "internal_safe")

    def test_merge_orders_sources_by_arrival(self):
        merged = merge_records(
            [record("completion", 300), record("motion_phase_entered", 100)],
            [record("vehicle_status", 200, nav_state=4)],
        )
        self.assertEqual([value["received_monotonic_ns"] for value in merged], [100, 200, 300])

    def test_a_record_without_an_arrival_time_is_refused(self):
        with self.assertRaises(OnlineStateError):
            merge_records([{"kind": "completion"}])

    def test_an_internal_route_is_not_a_tested_route(self):
        with self.assertRaises(OnlineStateError):
            derive_online_trajectory([], mechanism="internal_hold")


class OnlineGateTests(unittest.TestCase):
    def test_every_runtime_action_declares_a_checkable_gate(self):
        validate_declarations()
        for action in CORE_ACTIONS:
            launch = (
                action.live_profile is not None
                and action.live_profile.application == "launch"
            )
            if action.backend is not None and not launch:
                self.assertIsNotNone(action.online_gate, action.action_id)
                self.assertTrue(action.online_gate_text.strip(), action.action_id)
                self.assertFalse(action.online_gate(OnlineState()), action.action_id)
            else:
                self.assertIsNone(action.online_gate, action.action_id)

    def test_the_stall_gate_needs_external_authority_without_a_fault(self):
        gate = core_action("stop_owned_setpoint_stream").online_gate
        self.assertTrue(gate(OnlineState(authority_family="external_offboard")))
        self.assertFalse(
            gate(OnlineState(authority_family="external_offboard", fault_observed=True))
        )
        self.assertFalse(gate(OnlineState(authority_family="internal_safe")))
        self.assertFalse(
            gate(OnlineState(authority_family="external_offboard", terminal=True))
        )

    def test_the_reclaim_gate_asks_for_the_effect_not_the_classified_loss(self):
        gate = core_action("restart_producer_after_loss").online_gate
        # The loss is not classifiable in flight, so an internal route holding
        # authority after the tested route lost it is what the gate can see.
        self.assertTrue(
            gate(OnlineState(authority_family="internal_safe", fallback_installed=True))
        )
        self.assertFalse(gate(OnlineState(authority_family="internal_safe")))
        self.assertFalse(
            gate(
                OnlineState(
                    authority_family="external_offboard", fallback_installed=True
                )
            )
        )

    def test_the_re_entry_gate_needs_a_completion_first(self):
        gate = core_action("re_enter_route_after_successor").online_gate
        self.assertFalse(gate(OnlineState(authority_family="internal_safe")))
        self.assertTrue(
            gate(OnlineState(authority_family="internal_safe", completion_observed=True))
        )

    def test_a_ground_navigation_state_does_not_grant_authority(self):
        gate = core_action("adjacent_land_request").online_gate
        self.assertFalse(gate(OnlineState(authority_family="internal_safe")))
        self.assertTrue(
            gate(OnlineState(authority_family="internal_safe", airborne=True))
        )


class AgreementMeasurementTests(unittest.TestCase):
    def test_an_early_online_gate_is_measured_as_an_online_only_window(self):
        measured = _disagreement(
            [(100, True)], [(300, True)], horizon_ns=500
        )
        self.assertEqual(measured["online_only_ns"], 200)
        self.assertEqual(measured["offline_only_ns"], 0)
        self.assertEqual(measured["online_only_intervals"], 1)
        self.assertEqual(measured["online_true_from_ns"], 100)
        self.assertEqual(measured["offline_true_from_ns"], 300)

    def test_a_late_online_gate_leaves_no_online_only_window(self):
        measured = _disagreement([(300, True)], [(100, True)], horizon_ns=500)
        self.assertEqual(measured["online_only_ns"], 0)
        self.assertEqual(measured["offline_only_ns"], 200)

    def test_separate_windows_are_counted_separately(self):
        measured = _disagreement(
            [(100, True), (200, False), (300, True)],
            [(400, True)],
            horizon_ns=500,
        )
        self.assertEqual(measured["online_only_ns"], 200)
        self.assertEqual(measured["online_only_intervals"], 2)

    def test_nothing_beyond_the_shared_horizon_is_measured(self):
        measured = _disagreement([(100, True)], [], horizon_ns=150)
        self.assertEqual(measured["online_only_ns"], 50)

    def test_a_value_before_any_change_point_is_false(self):
        self.assertFalse(_value_at([(100, True)], 50))
        self.assertTrue(_value_at([(100, True)], 100))


if __name__ == "__main__":
    unittest.main()
