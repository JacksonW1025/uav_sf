"""Tests for the Stage 2 candidate action and workload inventory."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from scripts.corpus.action_inventory import (
    CANDIDATES,
    DEFAULT_REPLAY_ROOT,
    INCLUSION,
    LIFECYCLE_PHASES,
    MECHANISMS,
    ROLES,
    ActionCandidate,
    InventoryError,
    _index_studies,
    _verify,
    build_inventory,
)
from scripts.state.semantic_state import CONTRACT_BOUNDARIES


ROOT = Path(__file__).resolve().parents[1]


class ActionInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = _index_studies(ROOT)
        cls.sample = next(
            candidate for candidate in CANDIDATES if candidate.matrix_cells
        )

    def test_every_declared_candidate_verifies_against_the_repository(self) -> None:
        for candidate in CANDIDATES:
            with self.subTest(action=candidate.action_id):
                _verify(candidate, ROOT, self.index)

    def test_candidate_identities_are_unique(self) -> None:
        identifiers = [candidate.action_id for candidate in CANDIDATES]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_axes_match_the_experiment_plan_definition(self) -> None:
        self.assertEqual(
            LIFECYCLE_PHASES,
            (
                "registration",
                "activation",
                "execution",
                "completion",
                "replacement",
                "fallback",
                "re_entry",
            ),
        )
        for mechanism in (
            "process_loss_restart",
            "setpoint_or_callback_stall",
            "communication_delay",
            "health_loss",
            "rejection",
            "manual_or_failsafe_takeover",
            "adjacent_authority_request",
        ):
            self.assertIn(mechanism, MECHANISMS)

    def test_declared_boundaries_exist_in_the_semantic_state_model(self) -> None:
        for candidate in CANDIDATES:
            for boundary in candidate.expected_boundaries:
                self.assertIn(boundary, CONTRACT_BOUNDARIES)

    def test_unknown_cell_or_missing_provenance_is_refused(self) -> None:
        for broken in (
            replace(self.sample, matrix_cells=(("motivation-thor-v1", "no-such-cell"),)),
            replace(self.sample, matrix_cells=(("no-such-study", "any-cell"),)),
            replace(self.sample, provenance=("scripts/does_not_exist.py",)),
            replace(self.sample, live_backend="unwired_action_v1"),
            replace(self.sample, expected_boundaries=("not_a_boundary",)),
            replace(self.sample, lifecycle_phase="not_a_phase"),
            replace(self.sample, mechanism="not_a_mechanism"),
            replace(self.sample, role="not_a_role"),
        ):
            with self.subTest(action=broken.action_id):
                with self.assertRaises(InventoryError):
                    _verify(broken, ROOT, self.index)

    def test_a_gap_must_not_claim_evidence_and_a_candidate_must_have_some(self) -> None:
        with self.assertRaises(InventoryError):
            _verify(replace(self.sample, inclusion="gap"), ROOT, self.index)
        gap = next(
            candidate for candidate in CANDIDATES if candidate.inclusion == "gap"
        )
        with self.assertRaises(InventoryError):
            _verify(
                replace(gap, inclusion="candidate", matrix_cells=()), ROOT, self.index
            )

    def test_inventory_is_not_a_frozen_corpus(self) -> None:
        inventory = build_inventory(ROOT, replay_root=DEFAULT_REPLAY_ROOT)
        self.assertFalse(inventory["frozen"])
        self.assertIn("only after this inventory", inventory["freeze_rule"])
        self.assertEqual(
            inventory["totals"]["candidates"] + inventory["totals"]["gaps"],
            len(CANDIDATES),
        )

    def test_evidence_is_joined_rather_than_declared(self) -> None:
        inventory = build_inventory(ROOT, replay_root=DEFAULT_REPLAY_ROOT)
        actions = {record["action_id"]: record for record in inventory["actions"]}
        stall = actions["owned_setpoint_stall_healthy"]
        self.assertGreater(stall["evidence"]["accepted"], 0)
        self.assertIn("command_stale", stall["evidence"]["observed_contract_boundaries"])
        # The preregistered process-exit cells have no ledger, so a joined count
        # must stay zero even though the candidate is implemented and qualified.
        exit_action = actions["owned_process_exit_fallback"]
        unlaunched = [
            cell
            for cell in exit_action["evidence"]["cells"]
            if cell["study_id"] == "main-process-exit-strategy-thor-v1"
        ]
        self.assertTrue(unlaunched)
        for cell in unlaunched:
            self.assertEqual(cell["launches"], 0)
            self.assertEqual(cell["accepted"], 0)
        for record in inventory["actions"]:
            if record["inclusion"] == "gap":
                self.assertEqual(record["evidence"]["accepted"], 0)

    def test_missing_stage_one_replay_is_refused(self) -> None:
        with self.assertRaises(InventoryError):
            build_inventory(ROOT, replay_root=Path("experiments/does_not_exist"))

    def test_declared_vocabularies_are_closed(self) -> None:
        self.assertEqual(set(ROLES), {"benchmark", "discovery", "realism_validation", "undecided"})
        self.assertEqual(set(INCLUSION), {"candidate", "gap"})
        self.assertTrue(all(isinstance(item, ActionCandidate) for item in CANDIDATES))


if __name__ == "__main__":
    unittest.main()
