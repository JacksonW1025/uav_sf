from __future__ import annotations

import unittest

from scripts.runtime.formal_attempt import FormalAttemptError, _cell


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
