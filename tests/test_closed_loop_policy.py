"""Tests for a policy that chooses in flight and is re-derived afterwards."""

from __future__ import annotations

import copy
import unittest

from scripts.corpus.episode_classes import (
    EpisodeClassError,
    episode_class,
    episode_class_records,
    validate_declarations,
)
from scripts.runtime.closed_loop_policy import (
    POLICY_SCHEMA,
    STOP,
    admissible_units,
    create_policy,
    official_offset_ns,
    policy_digest,
    replay_decision_log,
    select_step,
    validate_policy,
)
from scripts.runtime.live_strategy_backend import LiveStrategyError
from scripts.state.online_state import OnlineState


CLASS_ID = "process_exit_reclaim"
BOUNDS = {
    "terminate_owning_producer": [3_500_000_000, 6_500_000_000],
    "restart_producer_after_loss": [500_000_000, 2_500_000_000],
}


def policy(strategy: str = "official_sequence", seed: int | None = None, covered=None):
    return create_policy(
        strategy=strategy,
        seed=seed,
        mechanism="legacy_offboard",
        class_id=CLASS_ID,
        timing_bounds_ns=BOUNDS,
        covered_units=set(covered or ()),
    )


def route_active() -> OnlineState:
    """The tested route holds authority and nothing has gone wrong yet."""

    return OnlineState(
        authority_family="external_offboard", airborne=True, motion_entered=True
    )


def producer_lost() -> OnlineState:
    """The producer is gone and a safe route took over unasked."""

    return OnlineState(
        authority_family="internal_safe",
        airborne=True,
        fallback_installed=True,
        fault_observed=True,
        fault_class="process_exit",
    )


def flown(value: dict, states: list[OnlineState]) -> dict:
    """A decision log produced by applying the policy to a run of states."""

    applied: list[str] = []
    covered = set(value["covered_units_before_episode"])
    steps = []
    for index, state in enumerate(states):
        step = select_step(
            policy=value,
            step_index=index,
            state=state,
            applied=applied,
            covered_units=covered,
        )
        steps.append(step)
        if step["action"] == STOP:
            break
        applied.append(step["action"])
        covered.add(step["selected_unit"])
    return {
        "schema_version": POLICY_SCHEMA,
        "policy_digest": policy_digest(value),
        "steps": steps,
    }


class EpisodeClassTests(unittest.TestCase):
    def test_the_declared_class_is_launchable(self):
        validate_declarations()
        self.assertTrue(episode_class_records())

    def test_the_class_carries_one_fault_mode(self):
        episode = episode_class(CLASS_ID)
        self.assertEqual(episode.fault_mode, "process_exit")
        self.assertEqual(episode.maximum_steps, 2)

    def test_the_fallback_differs_by_mechanism(self):
        episode = episode_class(CLASS_ID)
        self.assertEqual(
            episode.obligations("legacy_offboard")["expected_fallback"], "internal_land"
        )
        self.assertEqual(
            episode.obligations("dynamic_external_mode")["expected_fallback"],
            "internal_rtl",
        )

    def test_an_unavailable_mechanism_is_refused(self):
        with self.assertRaises(EpisodeClassError):
            episode_class(CLASS_ID).obligations("mode_executor")

    def test_the_branch_replaces_the_baseline(self):
        episode = episode_class(CLASS_ID)
        baseline = episode.obligations("legacy_offboard")
        branch = episode.sequence_obligations()["when_observed"]
        self.assertTrue(baseline["fallback_expected"])
        self.assertFalse(branch["fallback_expected"])
        self.assertFalse(baseline["completion_expected"])
        self.assertTrue(branch["completion_expected"])

    def test_the_successor_is_a_class_property_not_a_branch_one(self):
        # The producer is launched to release to one successor, so both
        # sequences owe the same one. Declaring a different successor in the
        # branch would demand a release the workload was never configured to
        # make, which is what the first closed-loop flight reported.
        episode = episode_class(CLASS_ID)
        self.assertEqual(
            episode.obligations("legacy_offboard")["expected_successor"], "internal_hold"
        )
        self.assertNotIn("expected_successor", episode.sequence_obligations()["when_observed"])


class PolicyTests(unittest.TestCase):
    def test_a_frozen_policy_validates(self):
        for strategy, seed in (
            ("official_sequence", None),
            ("bounded_random_timing", 11),
            ("state_aware", 11),
        ):
            validate_policy(policy(strategy, seed))

    def test_official_sequence_refuses_a_seed(self):
        with self.assertRaises(LiveStrategyError):
            policy("official_sequence", 11)

    def test_a_seeded_strategy_needs_its_seed(self):
        with self.assertRaises(LiveStrategyError):
            policy("bounded_random_timing", None)

    def test_an_unknown_class_is_refused(self):
        with self.assertRaises(LiveStrategyError):
            create_policy(
                strategy="official_sequence",
                seed=None,
                mechanism="legacy_offboard",
                class_id="not_a_class",
                timing_bounds_ns=BOUNDS,
                covered_units=set(),
            )

    def test_a_tampered_policy_is_refused(self):
        value = policy()
        value["maximum_steps"] = 5
        with self.assertRaises(LiveStrategyError):
            validate_policy(value)

    def test_each_action_scores_against_its_own_window(self):
        # A reclaim's bins sit between the fallback and touchdown; scoring them
        # against the termination's offset would rank them by a property they
        # do not have.
        self.assertEqual(official_offset_ns("terminate_owning_producer"), 5_000_000_000)
        self.assertEqual(official_offset_ns("restart_producer_after_loss"), 1_500_000_000)


class AdmissibilityTests(unittest.TestCase):
    def test_the_first_decision_point_cannot_stop(self):
        # The class is launched with its fault mode installed and its plan
        # declares fault_expected, which is two-sided. An episode that applied
        # nothing would violate its own plan.
        units = admissible_units(policy(), route_active(), [])
        self.assertNotIn(STOP, [item["unit"] for item in units])

    def test_stopping_is_offered_once_something_was_applied(self):
        units = admissible_units(
            policy(), producer_lost(), ["terminate_owning_producer"]
        )
        self.assertIn(STOP, [item["unit"] for item in units])

    def test_the_gate_filters_the_offer(self):
        # The reclaim is not admissible while the tested route still holds
        # authority, and the termination is not admissible after the fault.
        early = {item["action"] for item in admissible_units(policy(), route_active(), [])}
        self.assertEqual(early, {"terminate_owning_producer"})
        late = {
            item["action"]
            for item in admissible_units(
                policy(), producer_lost(), ["terminate_owning_producer"]
            )
        }
        self.assertEqual(late, {"restart_producer_after_loss", STOP})

    def test_an_applied_action_is_not_offered_again(self):
        units = admissible_units(policy(), route_active(), ["terminate_owning_producer"])
        self.assertEqual({item["action"] for item in units}, {STOP})

    def test_a_dead_first_decision_point_fails_closed(self):
        with self.assertRaises(LiveStrategyError):
            select_step(
                policy=policy(),
                step_index=0,
                state=OnlineState(),
                applied=[],
                covered_units=set(),
            )

    def test_a_step_beyond_the_class_bound_is_refused(self):
        with self.assertRaises(LiveStrategyError):
            select_step(
                policy=policy(),
                step_index=2,
                state=route_active(),
                applied=[],
                covered_units=set(),
            )


class SelectionTests(unittest.TestCase):
    def test_the_official_sequence_applies_its_actions_in_order(self):
        value = policy()
        log = flown(value, [route_active(), producer_lost()])
        self.assertEqual(
            [step["selected_unit"] for step in log["steps"]],
            ["terminate_owning_producer:boundary", "restart_producer_after_loss:boundary"],
        )

    def test_the_same_seed_reproduces_the_same_episode(self):
        states = [route_active(), producer_lost()]
        first = flown(policy("bounded_random_timing", 21), states)
        second = flown(policy("bounded_random_timing", 21), states)
        self.assertEqual(first, second)

    def test_seeds_explore_both_the_bins_and_the_sequence_length(self):
        states = [route_active(), producer_lost()]
        bins, lengths = set(), set()
        for seed in range(1, 61):
            log = flown(policy("bounded_random_timing", seed), states)
            bins.add(log["steps"][0]["selected_boundary"])
            lengths.add(len([s for s in log["steps"] if s["action"] != STOP]))
        self.assertEqual(len(bins), 5)
        # Some episodes stop after the termination and some reclaim, so the
        # sequence length is being chosen rather than fixed by the class.
        self.assertEqual(lengths, {1, 2})

    def test_state_aware_stops_when_nothing_uncovered_is_left(self):
        covered = {
            f"restart_producer_after_loss:{name}"
            for name in ("early", "pre_boundary", "boundary", "post_boundary", "late")
        }
        step = select_step(
            policy=policy("state_aware", 9, covered),
            step_index=1,
            state=producer_lost(),
            applied=["terminate_owning_producer"],
            covered_units=covered,
        )
        self.assertEqual(step["selected_unit"], STOP)

    def test_state_aware_prefers_an_uncovered_unit(self):
        covered = {"restart_producer_after_loss:boundary"}
        step = select_step(
            policy=policy("state_aware", 9, covered),
            step_index=1,
            state=producer_lost(),
            applied=["terminate_owning_producer"],
            covered_units=covered,
        )
        self.assertNotIn(step["selected_unit"], covered | {STOP})


class ReplayTests(unittest.TestCase):
    def test_an_honest_log_replays(self):
        for strategy, seed in (
            ("official_sequence", None),
            ("bounded_random_timing", 21),
            ("state_aware", 21),
        ):
            value = policy(strategy, seed)
            log = flown(value, [route_active(), producer_lost()])
            summary = replay_decision_log(value, log)
            self.assertEqual(summary["steps_replayed"], len(log["steps"]))

    def test_a_forged_choice_is_refused(self):
        value = policy()
        log = flown(value, [route_active(), producer_lost()])
        log["steps"][1]["selected_unit"] = "restart_producer_after_loss:late"
        log["steps"][1]["selected_boundary"] = "late"
        with self.assertRaises(LiveStrategyError):
            replay_decision_log(value, log)

    def test_a_widened_admissible_set_is_refused(self):
        # The admissible set is recomputed from the recorded state, so a flight
        # cannot report options the state did not offer.
        value = policy()
        log = flown(value, [route_active(), producer_lost()])
        log["steps"][0]["admissible_units"] = sorted(
            log["steps"][0]["admissible_units"] + ["restart_producer_after_loss:early"]
        )
        with self.assertRaises(LiveStrategyError):
            replay_decision_log(value, log)

    def test_a_rewritten_state_changes_the_choice_and_is_refused(self):
        # The state is the one input the flight is trusted for, and rewriting
        # it alone does not survive, because the choice is recomputed from it.
        value = policy()
        log = flown(value, [route_active(), producer_lost()])
        log["steps"][1]["observed_state"]["fallback_installed"] = False
        with self.assertRaises(LiveStrategyError):
            replay_decision_log(value, log)

    def test_a_log_from_another_policy_is_refused(self):
        log = flown(policy("bounded_random_timing", 21), [route_active(), producer_lost()])
        with self.assertRaises(LiveStrategyError):
            replay_decision_log(policy("bounded_random_timing", 22), log)

    def test_nothing_may_follow_a_stop(self):
        value = policy("bounded_random_timing", 21)
        states = [route_active(), producer_lost()]
        seed = next(
            seed
            for seed in range(1, 61)
            if flown(policy("bounded_random_timing", seed), states)["steps"][-1]["action"]
            == STOP
        )
        value = policy("bounded_random_timing", seed)
        log = flown(value, states)
        extra = copy.deepcopy(log["steps"][-1])
        extra["step_index"] = len(log["steps"])
        log["steps"].append(extra)
        with self.assertRaises(LiveStrategyError):
            replay_decision_log(value, log)

    def test_more_steps_than_the_class_allows_are_refused(self):
        value = policy()
        log = flown(value, [route_active(), producer_lost()])
        log["steps"].append(copy.deepcopy(log["steps"][-1]))
        with self.assertRaises(LiveStrategyError):
            replay_decision_log(value, log)

    def test_an_out_of_order_step_is_refused(self):
        value = policy()
        log = flown(value, [route_active(), producer_lost()])
        log["steps"][1]["step_index"] = 5
        with self.assertRaises(LiveStrategyError):
            replay_decision_log(value, log)

    def test_the_replay_reports_what_the_episode_applied(self):
        value = policy()
        log = flown(value, [route_active(), producer_lost()])
        summary = replay_decision_log(value, log)
        self.assertEqual(
            summary["applied_actions"],
            ["terminate_owning_producer", "restart_producer_after_loss"],
        )
        self.assertFalse(summary["stopped_by_choice"])
        self.assertIn("terminate_owning_producer:boundary", summary["covered_units_after_episode"])


if __name__ == "__main__":
    unittest.main()
