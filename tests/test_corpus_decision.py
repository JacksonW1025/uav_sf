"""Tests for the corpus decision surface that selects an action and a timing."""

from __future__ import annotations

from collections import Counter
import unittest

from scripts.corpus.core_actions import wired_actions
from scripts.runtime.live_strategy_backend import (
    CORPUS_SCHEMA,
    OFFSETS_NS,
    LiveStrategyError,
    create_corpus_decision,
    create_live_decision,
    enabled_corpus_candidates,
    validate_live_decision,
)
from scripts.runtime.strategy_action_executor import (
    MARKER_SOURCES,
    ActionExecutorError,
    observed_markers,
)


CORPUS = ("stop_owned_setpoint_stream", "terminate_owning_producer")
BOUNDS = {action: [3_500_000_000, 6_500_000_000] for action in CORPUS}
OFFICIAL_OFFSET = 5_000_000_000


def decide(strategy: str, seed: int | None, covered: set[str] | None = None, **overrides):
    arguments = {
        "strategy": strategy,
        "seed": seed,
        "mechanism": "legacy_offboard",
        "corpus": CORPUS,
        "timing_bounds_ns": BOUNDS,
        "official_action": CORPUS[0],
        "official_offset_ns": OFFICIAL_OFFSET,
        "covered_units": set(covered or set()),
    }
    arguments.update(overrides)
    return create_corpus_decision(**arguments)


class CorpusDecisionTests(unittest.TestCase):
    def test_every_strategy_produces_a_valid_re_derivable_decision(self) -> None:
        for strategy, seed in (
            ("official_sequence", None),
            ("bounded_random_timing", 7),
            ("state_aware", 7),
        ):
            with self.subTest(strategy=strategy):
                decision = decide(strategy, seed)
                self.assertEqual(decision["schema_version"], CORPUS_SCHEMA)
                validate_live_decision(decision)
                self.assertEqual(decision, decide(strategy, seed))

    def test_a_tampered_decision_is_refused(self) -> None:
        decision = decide("state_aware", 7)
        for field, value in (
            ("planned_offset_ns", 9_000_000_000),
            ("action", "terminate_owning_producer"),
            ("selected_unit", "stop_owned_setpoint_stream:late"),
        ):
            tampered = dict(decision)
            tampered[field] = value
            with self.subTest(field=field):
                with self.assertRaises(LiveStrategyError):
                    validate_live_decision(tampered)

    def test_the_official_sequence_needs_an_executable_official_action(self) -> None:
        with self.assertRaises(LiveStrategyError):
            decide("official_sequence", None, official_action="restart_producer_after_loss")
        with self.assertRaises(LiveStrategyError):
            decide("official_sequence", None, official_offset_ns=9_000_000_000)
        with self.assertRaises(LiveStrategyError):
            decide("official_sequence", 5)

    def test_state_aware_selection_moves_on_as_units_are_covered(self) -> None:
        covered: set[str] = set()
        chosen: list[str] = []
        for _ in range(len(CORPUS) * len(OFFSETS_NS)):
            unit = decide("state_aware", 7, covered)["selected_unit"]
            chosen.append(unit)
            covered.add(unit)
        self.assertEqual(len(set(chosen)), len(chosen))
        self.assertEqual(len(set(unit.split(":")[0] for unit in chosen)), len(CORPUS))

    def test_bounded_random_reaches_the_joint_action_and_timing_space(self) -> None:
        units = Counter(
            decide("bounded_random_timing", seed)["selected_unit"] for seed in range(40)
        )
        self.assertEqual(len(units), len(CORPUS) * len(OFFSETS_NS))

    def test_an_unwired_action_is_never_selectable(self) -> None:
        corpus = (*CORPUS, "restart_producer_after_loss")
        bounds = dict(BOUNDS, restart_producer_after_loss=[3_500_000_000, 6_500_000_000])
        decision = decide(
            "state_aware", 7, corpus=corpus, timing_bounds_ns=bounds
        )
        offered = {
            item["action"] for item in decision["candidates"] if item["enabled"]
        }
        self.assertNotIn("restart_producer_after_loss", offered)
        self.assertIn("restart_producer_after_loss", {item["action"] for item in decision["candidates"]})

    def test_a_corpus_without_an_executable_candidate_is_refused(self) -> None:
        with self.assertRaises(LiveStrategyError):
            decide(
                "state_aware",
                7,
                corpus=("restart_producer_after_loss",),
                timing_bounds_ns={"restart_producer_after_loss": [3_500_000_000, 6_500_000_000]},
                official_action="restart_producer_after_loss",
            )
        with self.assertRaises(LiveStrategyError):
            decide("state_aware", 7, corpus=())

    def test_candidates_are_offered_for_both_compared_mechanisms(self) -> None:
        for mechanism in ("legacy_offboard", "dynamic_external_mode"):
            with self.subTest(mechanism=mechanism):
                candidates = enabled_corpus_candidates(
                    mechanism=mechanism, corpus=CORPUS, timing_bounds_ns=BOUNDS
                )
                enabled = [item for item in candidates if item["enabled"]]
                self.assertEqual(len(enabled), len(CORPUS) * len(OFFSETS_NS))
                self.assertEqual(
                    {item.action_id for item in wired_actions(mechanism)}, set(CORPUS)
                )

    def test_timing_bounds_restrict_the_offered_boundaries(self) -> None:
        narrow = {action: [4_900_000_000, 5_100_000_000] for action in CORPUS}
        decision = decide("state_aware", 7, timing_bounds_ns=narrow)
        enabled = [item for item in decision["candidates"] if item["enabled"]]
        self.assertEqual({item["boundary"] for item in enabled}, {"boundary"})

    def test_the_retained_single_action_decision_still_validates(self) -> None:
        single_action = create_live_decision(
            strategy="bounded_random_timing",
            seed=11,
            timing_bounds_ns={"setpoint_stall": [3_500_000_000, 6_500_000_000]},
            official_offset_ns=OFFICIAL_OFFSET,
            covered_boundaries=set(),
        )
        self.assertEqual(single_action["schema_version"], "1.0")
        validate_live_decision(single_action)

    def test_the_executor_refuses_a_marker_it_cannot_observe(self) -> None:
        records = [
            {"kind": "offboard_observed_active", "received_monotonic_ns": 100},
            {"kind": "motion_phase_entered", "received_monotonic_ns": 200},
        ]
        self.assertEqual(
            observed_markers(records, ["route_active", "motion_entered"]),
            {"route_active": 100, "motion_entered": 200},
        )
        self.assertIsNone(observed_markers([], ["route_active"])["route_active"])
        with self.assertRaises(ActionExecutorError):
            observed_markers(records, ["fallback_installed"])

    def test_the_decision_carries_the_action_timing_anchor(self) -> None:
        decision = decide("state_aware", 7)
        self.assertEqual(decision["timing_anchor"], "route_active")
        self.assertIn(decision["timing_anchor"], decision["required_state"])
        for candidate in decision["candidates"]:
            if candidate["enabled"]:
                self.assertIn(candidate["timing_anchor"], candidate["required_state"])

    def test_the_executor_refuses_an_anchor_outside_the_required_markers(self) -> None:
        self.assertIn("successor_installed", MARKER_SOURCES)
        records = [{"kind": "successor_observed_active", "received_monotonic_ns": 7}]
        self.assertEqual(
            observed_markers(records, ["successor_installed"]),
            {"successor_installed": 7},
        )

    def test_every_wired_action_declares_only_observable_markers(self) -> None:
        for mechanism in ("legacy_offboard", "dynamic_external_mode"):
            for action in wired_actions(mechanism):
                with self.subTest(action=action.action_id):
                    self.assertEqual(
                        observed_markers(
                            [
                                {
                                    "kind": "offboard_observed_active",
                                    "received_monotonic_ns": 1,
                                },
                                {
                                    "kind": "motion_phase_entered",
                                    "received_monotonic_ns": 2,
                                },
                            ],
                            list(action.live_markers),
                        ).keys(),
                        set(action.live_markers),
                    )


if __name__ == "__main__":
    unittest.main()
