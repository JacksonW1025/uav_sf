from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
import yaml

from scripts.oracles.oracle_validation_runner import CASE_SCHEMA, CLAUSES, ROOT, run_suite


MANIFEST = ROOT / "experiments" / "oracle_validation" / "trace_cases.yaml"


def test_manifest_is_schema_valid_and_covers_clause_states() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    validator = Draft202012Validator(CASE_SCHEMA)
    coverage = {clause: set() for clause in CLAUSES}
    for case in manifest["cases"]:
        validator.validate(case)
        for clause, status in case["expected_clauses"].items():
            coverage[clause].add(status)
    for clause in CLAUSES:
        assert {"PASS", "VIOLATION", "UNKNOWN"} <= coverage[clause]
    assert any(
        "NOT_APPLICABLE" in case["expected_clauses"].values()
        for case in manifest["cases"]
    )


def test_trace_mutation_suite_detects_all_preregistered_cases(tmp_path) -> None:
    summary = run_suite(MANIFEST, tmp_path / "raw", tmp_path / "processed")
    assert summary["all_expected_predictions_match"] is True
    assert summary["normal_case_false_positive_count"] == 0
    assert summary["mutant_miss_count"] == 0
    assert summary["mutant_detection_count"] >= 5
    results = json.loads(
        (tmp_path / "processed" / "case_results.json").read_text(encoding="utf-8")
    )
    assert results["case_count"] == 25
