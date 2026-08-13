"""Compatibility and fail-closed tests for semantic evaluation results."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluator.result_model import (
    EvaluationResultError,
    enrich_evaluation,
    load_evaluation,
    write_evaluation,
)
from scripts.evaluator.evaluate_trace import evaluate
from tests.helpers import passing_events, plan


class ResultModelTests(unittest.TestCase):
    def test_current_evaluation_preserves_compatible_status_and_adds_semantics(self) -> None:
        result = evaluate(passing_events(), plan())
        self.assertEqual(result["schema_version"], "1.1")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["semantic_disposition"]["primary"], "PASS")
        self.assertEqual(result["semantic_disposition"]["all"], ["PASS"])
        self.assertEqual(result["findings"], [])

    def test_contract_violation_is_not_promoted_to_public_spec(self) -> None:
        compatible = {
            "schema_version": "1.0",
            "plan_id": "p",
            "run_id": "r",
            "status": "VIOLATION",
            "evidence_gate": {"status": "ADMISSIBLE", "checks": {}, "reasons": []},
            "oracles": [
                {
                    "oracle": "freshness_lineage",
                    "clauses": {
                        "freshness": {
                            "status": "VIOLATION",
                            "reasons": ["command exceeded the registered bound"],
                            "evidence": {
                                "maximum_command_age_ns": 200_000_000,
                                "observed_ages_ns": [210_000_000],
                            },
                        }
                    },
                }
            ],
        }
        enriched = enrich_evaluation(compatible)
        self.assertEqual(enriched["status"], "VIOLATION")
        self.assertEqual(
            enriched["semantic_disposition"]["all"],
            ["SAFETY_CONTRACT_VIOLATION"],
        )
        self.assertNotIn("SPEC_VIOLATION", enriched["semantic_disposition"]["all"])
        self.assertIn(
            "THRESHOLD_SENSITIVE_ANOMALY",
            enriched["findings"][0]["classifications"],
        )

    def test_inadmissible_evidence_remains_inconclusive(self) -> None:
        compatible = {
            "schema_version": "1.0",
            "plan_id": "p",
            "run_id": "r",
            "status": "INCONCLUSIVE",
            "evidence_gate": {
                "status": "INADMISSIBLE",
                "checks": {"hash_chain": False},
                "reasons": ["broken chain"],
            },
            "oracles": [],
        }
        enriched = enrich_evaluation(compatible)
        self.assertEqual(enriched["status"], "INCONCLUSIVE")
        self.assertEqual(enriched["semantic_disposition"]["primary"], "UNKNOWN")
        self.assertEqual(enriched["evidence"]["admissibility"], "INADMISSIBLE")

    def test_v1_reader_accepts_frozen_result(self) -> None:
        frozen = Path(
            "experiments/motivation_thor_remediation_v1/results/"
            "timing-offboard-reentry-rtl-remediation-001/evaluation.json"
        )
        result = load_evaluation(frozen)
        self.assertEqual(result["schema_version"], "1.0")
        self.assertIn(result["status"], {"PASS", "VIOLATION", "INCONCLUSIVE"})

    def test_reader_rejects_unknown_disposition_and_writer_refuses_overwrite(self) -> None:
        result = enrich_evaluation(
            {
                "schema_version": "1.0",
                "plan_id": "p",
                "run_id": "r",
                "status": "PASS",
                "evidence_gate": {"status": "ADMISSIBLE", "checks": {}, "reasons": []},
                "oracles": [],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation.json"
            write_evaluation(path, result)
            with self.assertRaises(FileExistsError):
                write_evaluation(path, result)
            malformed = dict(result)
            malformed["semantic_disposition"] = {"primary": "MADE_UP", "all": ["MADE_UP"]}
            bad = Path(directory) / "bad.json"
            bad.write_text(json.dumps(malformed), encoding="utf-8")
            with self.assertRaises(EvaluationResultError):
                load_evaluation(bad)


if __name__ == "__main__":
    unittest.main()
