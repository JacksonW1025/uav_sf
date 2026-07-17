#!/usr/bin/env python3
"""Evaluate the frozen O1-O9 Oracle Validation Gate."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CLAUSES = {"revocation", "installation", "exclusivity", "continuity", "recovery"}


def _no_run_id_decision_special_cases(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = {"run_id", "case_id", "ground_truth_case_id"}
    for node in ast.walk(tree):
        condition = None
        if isinstance(node, (ast.If, ast.IfExp, ast.While)):
            condition = node.test
        if condition is not None and {
            child.id for child in ast.walk(condition) if isinstance(child, ast.Name)
        } & forbidden:
            return False
    return True


def evaluate(
    trace: dict[str, Any],
    live: dict[str, Any],
    *,
    validator_passed: bool,
    criteria_frozen_commit: str,
) -> dict[str, Any]:
    status_coverage: dict[str, set[str]] = {clause: set() for clause in CLAUSES}
    for case in trace["cases"]:
        for clause, status in case["expected_clauses"].items():
            if clause in status_coverage:
                status_coverage[clause].add(status)
    controls = [result for result in live["results"] if result["mutant_type"] == "control"]
    mutants = [result for result in live["results"] if result["mutant_type"] != "control"]
    live_types = sorted({result["mutant_type"] for result in mutants if result["classification"] == "VALID"})
    criteria = {
        "O1": {
            "pass": all({"PASS", "VIOLATION", "UNKNOWN"} <= statuses for statuses in status_coverage.values()),
            "evidence": {key: sorted(value) for key, value in sorted(status_coverage.items())},
        },
        "O2": {"pass": trace["normal_case_false_positive_count"] == 0, "count": trace["normal_case_false_positive_count"]},
        "O3": {"pass": trace["mutant_miss_count"] == 0 and trace["mutant_detection_count"] > 0, "detections": trace["mutant_detection_count"], "misses": trace["mutant_miss_count"]},
        "O4": {"pass": trace["unexpected_unknown_count"] == 0 and trace["incomplete_evidence_unknown_count"] > 0, "incomplete_unknowns": trace["incomplete_evidence_unknown_count"], "unexpected_unknowns": trace["unexpected_unknown_count"]},
        "O5": {"pass": len(live_types) >= 3, "valid_live_mutant_types": live_types},
        "O6": {
            "pass": len(controls) >= 3 and all(
                result["classification"] == "VALID"
                and all(assertion["predicted"] != "VIOLATION" for assertion in result["assertions"])
                for result in controls
            ),
            "valid_control_count": sum(result["classification"] == "VALID" for result in controls),
        },
        "O7": {
            "pass": bool(mutants) and all(
                result["classification"] == "VALID" and result["all_assertions_match"]
                for result in mutants
            ),
            "valid_mutant_run_count": sum(result["classification"] == "VALID" for result in mutants),
            "correct_target_assertions": sum(
                assertion["correct"] for result in mutants for assertion in result["assertions"]
            ),
            "target_assertions": sum(len(result["assertions"]) for result in mutants),
        },
        "O8": {
            "pass": _no_run_id_decision_special_cases(ROOT / "scripts" / "oracles" / "route_oracle_v0.py"),
            "check": "AST decision conditions contain no run_id/case_id/ground_truth_case_id",
        },
        "O9": {"pass": validator_passed, "check": "scripts/validation/validate_repo.sh"},
    }
    passed = all(item["pass"] for item in criteria.values())
    return {
        "schema_version": "1.0",
        "gate": "oracle_validation",
        "status": "PASS" if passed else "FAIL",
        "criteria_frozen_commit": criteria_frozen_commit,
        "oracle_version": "0.3",
        "route_trace_schema_version": "1.2",
        "criteria": criteria,
        "fuzzer_v0_authorized": passed,
        "failed_criteria": [name for name, item in criteria.items() if not item["pass"]],
        "evidence": {
            "trace_results": "data/processed/oracle_validation/case_results.json",
            "live_results": "data/processed/oracle_validation/live_case_results.json",
            "confusion_matrix": "data/processed/oracle_validation/clause_confusion_matrix.tsv",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--criteria-frozen-commit", required=True)
    parser.add_argument("--validator-passed", action="store_true")
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.trace.read_text(encoding="utf-8")),
        json.loads(args.live.read_text(encoding="utf-8")),
        validator_passed=args.validator_passed,
        criteria_frozen_commit=args.criteria_frozen_commit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "failed_criteria": result["failed_criteria"]}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
