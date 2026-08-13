from __future__ import annotations

import unittest

from scripts.runtime.formal_attempt import FormalAttemptError, _cell
from scripts.runtime.run_campaign import (
    CampaignError,
    _exact_digest,
    balanced_batch,
    validate_matrix,
)


class FormalAttemptTests(unittest.TestCase):
    def test_attempt_belongs_to_one_frozen_cell(self) -> None:
        matrix = {
            "cells": [
                {"cell_id": "normal", "attempt_ids": ["normal-01", "normal-02"]},
                {"cell_id": "fault", "attempt_ids": ["fault-01"]},
            ]
        }
        self.assertEqual(_cell(matrix, "normal-02")["cell_id"], "normal")

    def test_duplicate_attempt_assignment_is_refused(self) -> None:
        matrix = {
            "cells": [
                {"cell_id": "a", "attempt_ids": ["same-01"]},
                {"cell_id": "b", "attempt_ids": ["same-01"]},
            ]
        }
        with self.assertRaises(FormalAttemptError):
            _cell(matrix, "same-01")

    def test_derived_attempt_namespace_is_capped(self) -> None:
        matrix = {
            "cells": [
                {"cell_id": "normal", "attempt_id_prefix": "normal", "launch_cap": 10}
            ]
        }
        self.assertEqual(_cell(matrix, "normal-010")["cell_id"], "normal")
        with self.assertRaises(FormalAttemptError):
            _cell(matrix, "normal-011")

    def test_matrix_rejects_unqualified_concurrency(self) -> None:
        with self.assertRaises(CampaignError):
            validate_matrix({"schema_version": "1.0", "formal_concurrency": 6})

    def test_matrix_digest_contract_is_exact(self) -> None:
        self.assertTrue(_exact_digest("sha256:" + "a" * 64))
        self.assertFalse(_exact_digest("sha256:" + "A" * 64))
        self.assertFalse(_exact_digest("a" * 64))

    def test_campaign_balances_cells_and_rotates_slots(self) -> None:
        states = [
            {
                "cell": {"cell_id": name},
                "launches": launches,
                "complete": False,
                "insufficient": False,
            }
            for name, launches in (("a", 1), ("b", 0), ("c", 0), ("d", 0), ("e", 0))
        ]
        batch = balanced_batch(states, concurrency=4, launched_count=4)
        self.assertEqual([state["cell"]["cell_id"] for _, state in batch], ["b", "c", "d", "e"])
        self.assertEqual([slot for slot, _ in batch], [1, 2, 3, 0])
