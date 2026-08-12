from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.accounting.attempts import AccountingError, AttemptLedger, verify_ledger
from scripts.evaluator.plan import PlanError, validate_plan
from tests.helpers import plan


class PlanAndAccountingTests(unittest.TestCase):
    def test_current_plan_contract(self) -> None:
        validate_plan(plan())
        invalid = plan()
        invalid["transition"]["expected_fallback"] = "legacy_offboard"
        with self.assertRaises(PlanError):
            validate_plan(invalid)

    def test_plan_requires_a_registered_target_environment(self) -> None:
        invalid = plan()
        invalid["execution_environment"]["execution_host_id"] = (
            "REPLACE-BEFORE-EXECUTION"
        )
        with self.assertRaises(PlanError):
            validate_plan(invalid)

    def test_launch_consumes_attempt_and_closure_is_hash_chained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attempt.jsonl"
            ledger = AttemptLedger(path, attempt_id="attempt-001", plan_id="plan-001")
            for state in (
                "REGISTERED",
                "PREFLIGHT_PASSED",
                "LAUNCHED",
                "COLLECTION_CLOSED",
                "EVALUATED",
                "CLEANUP_COMPLETED",
                "CLOSED",
            ):
                ledger.append(state)
            result = verify_ledger(path)
            self.assertTrue(result["formal_attempt_consumed"])
            self.assertTrue(result["closed"])

    def test_accounting_transition_cannot_skip_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = AttemptLedger(
                Path(directory) / "attempt.jsonl",
                attempt_id="attempt-002",
                plan_id="plan-002",
            )
            ledger.append("REGISTERED")
            with self.assertRaises(AccountingError):
                ledger.append("LAUNCHED")


if __name__ == "__main__":
    unittest.main()
