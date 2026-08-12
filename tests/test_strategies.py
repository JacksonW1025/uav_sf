from __future__ import annotations

import unittest

from scripts.evaluator.strategies import (
    ActionCandidate,
    StrategyError,
    bounded_random_timing,
    choose_state_aware,
    official_sequence,
)


class StrategyTests(unittest.TestCase):
    def test_official_sequence_has_no_mutation(self) -> None:
        self.assertEqual(
            official_sequence(["register", "activate"]),
            [
                {"action": "register", "delay_ns": 0},
                {"action": "activate", "delay_ns": 0},
            ],
        )

    def test_bounded_timing_is_deterministic_and_in_range(self) -> None:
        bounds = {"register": [10, 20], "activate": [30, 40]}
        first = bounded_random_timing(["register", "activate"], bounds, seed=42)
        second = bounded_random_timing(["register", "activate"], bounds, seed=42)
        self.assertEqual(first, second)
        self.assertTrue(10 <= int(first[0]["delay_ns"]) <= 20)
        with self.assertRaises(StrategyError):
            bounded_random_timing(["missing"], bounds, seed=42)

    def test_state_aware_prefers_uncovered_enabled_boundary(self) -> None:
        candidates = [
            ActionCandidate("covered", (("armed", True),), ("revocation",), 20),
            ActionCandidate("new", (("armed", True),), ("lineage",), 30),
            ActionCandidate("disabled", (("armed", False),), ("fallback",), 1),
        ]
        selected = choose_state_aware(
            candidates,
            state={"armed": True},
            covered_contract_boundaries={"revocation"},
            seed=7,
        )
        self.assertEqual(selected.name, "new")


if __name__ == "__main__":
    unittest.main()
