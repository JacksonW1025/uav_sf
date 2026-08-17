from __future__ import annotations

import unittest

from scripts.analysis.main_strategy_comparison import aggregate


class MainStrategyComparisonTests(unittest.TestCase):
    def test_fixed_cell_coverage_uses_executed_boundaries(self) -> None:
        base = {
            "mechanism": "legacy_offboard",
            "strategy": "state_aware",
            "outcome": "ACCEPTED",
            "evidence_gate_status": "ADMISSIBLE",
            "physical_execution_status": "PASS",
            "action_requested_count": 1,
            "evaluation_status": "VIOLATION",
            "applicable_contract_clauses": ["freshness_lineage:freshness"],
            "violation_signatures": ["freshness_lineage:freshness"],
        }
        records = [
            {**base, "ordinal": 1, "selected_boundary": "stall_offset:boundary", "absolute_request_error_ns": 5},
            {**base, "ordinal": 2, "selected_boundary": "stall_offset:post_boundary", "absolute_request_error_ns": 9},
            {**base, "ordinal": 3, "selected_boundary": "stall_offset:pre_boundary", "absolute_request_error_ns": 7},
        ]
        value = aggregate(records)
        self.assertEqual(value["executed_timing_boundary_count"], 3)
        self.assertEqual(value["launches_to_first_violation"], 1)
        self.assertEqual(value["absolute_request_error_ns"]["median"], 7)


if __name__ == "__main__":
    unittest.main()
