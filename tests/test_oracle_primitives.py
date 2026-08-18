from __future__ import annotations

import unittest

from scripts.oracles.evidence_gate import evaluate_evidence
from scripts.oracles.freshness_lineage import evaluate_freshness_lineage
from scripts.oracles.registration_contract import evaluate_registration_contract
from scripts.oracles.route_conformance import evaluate_route_conformance
from scripts.oracles.successor_progression import evaluate_successor_progression
from tests.helpers import chain, obligation_contract, passing_events, passing_raw_events


class OraclePrimitiveTests(unittest.TestCase):
    def test_retained_trace_gate_detects_missing_required_evidence(self) -> None:
        contract = obligation_contract()
        raw = [event for event in passing_raw_events() if event["kind"] != "revocation"]
        result = evaluate_evidence(chain(raw), contract)
        self.assertEqual(result["status"], "INADMISSIBLE")

    def test_retained_trace_gate_detects_hash_tampering(self) -> None:
        events = passing_events()
        events[7]["controller_id"] = "tampered"
        result = evaluate_evidence(events, obligation_contract())
        self.assertEqual(result["status"], "INADMISSIBLE")

    def test_contract_primitives_accept_a_complete_fixture(self) -> None:
        events = passing_events()
        contract = obligation_contract()
        self.assertEqual(
            evaluate_route_conformance(events, contract)["clauses"]["installation"]["status"],
            "PASS",
        )
        self.assertEqual(
            evaluate_freshness_lineage(events, contract)["clauses"]["freshness"]["status"],
            "PASS",
        )
        self.assertEqual(
            evaluate_successor_progression(events, contract)["clauses"]["expected_successor"]["status"],
            "PASS",
        )
        registration = evaluate_registration_contract(events, contract)["clauses"]
        self.assertEqual(registration["registration_rejection"]["status"], "NOT_APPLICABLE")


if __name__ == "__main__":
    unittest.main()
