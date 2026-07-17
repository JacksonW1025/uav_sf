#!/usr/bin/env python3
"""Run preregistered Route Oracle trace mutations and score each clause."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import yaml

from scripts.oracles.route_oracle_v0 import DEFAULT_THRESHOLDS, run as run_oracle
from scripts.oracles.trace_mutator import mutate


ROOT = Path(__file__).resolve().parents[2]
CASE_SCHEMA = json.loads(
    (ROOT / "data" / "schemas" / "oracle_mutation_case.schema.json").read_text(
        encoding="utf-8"
    )
)
CLAUSES = ("revocation", "installation", "exclusivity", "continuity", "recovery")


def _load_manifest(path: Path) -> dict[str, Any]:
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("cases"), list):
        raise ValueError("trace case manifest must contain a cases list")
    validator = Draft202012Validator(CASE_SCHEMA)
    for case in manifest["cases"]:
        validator.validate(case)
    case_ids = [case["case_id"] for case in manifest["cases"]]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("trace case IDs must be unique")
    return manifest


def _resolve(path: str | None) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def run_suite(manifest_path: Path, output_root: Path, processed_dir: Path) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    output_root.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    threshold_profile = manifest["threshold_profile"]
    thresholds = {**DEFAULT_THRESHOLDS, **threshold_profile.get("thresholds", {})}
    rows: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []

    for case in manifest["cases"]:
        case_id = case["case_id"]
        case_dir = output_root / case_id
        trace_path = case_dir / "route_trace.jsonl"
        mutation_report = mutate(
            _resolve(case["base_trace"]),
            trace_path,
            case_id,
            case["operations"],
        )
        clock_path = _resolve(case.get("base_clock_bridge"))
        clock_bridge = (
            None
            if case.get("omit_clock_bridge") or clock_path is None
            else json.loads(clock_path.read_text(encoding="utf-8"))
        )
        result = run_oracle(
            trace_path,
            clock_bridge,
            ground_truth_case_id=case_id,
            oracle_validation_profile=manifest["oracle_validation_profile"],
            threshold_profile_id=threshold_profile["id"],
            thresholds=thresholds,
            source_artifact_complete=case["source_artifact_complete"],
            candidate_writers=case.get("candidate_writers"),
            instrumented_candidates=case.get("instrumented_candidates"),
        )
        result_path = case_dir / "route_oracle.json"
        result_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        expected = case["expected_clauses"]
        scored_predictions: dict[str, str] = {}
        for clause, truth in expected.items():
            predicted = result["clauses"][clause]["status"]
            scored_predictions[clause] = predicted
            rows.append(
                {
                    "case_id": case_id,
                    "case_class": case["case_class"],
                    "target_clause": case["target_clause"],
                    "clause": clause,
                    "true_status": truth,
                    "predicted_status": predicted,
                    "correct": predicted == truth,
                    "false_positive": truth != "VIOLATION" and predicted == "VIOLATION",
                    "false_negative": truth == "VIOLATION" and predicted != "VIOLATION",
                    "unexpected_unknown": truth != "UNKNOWN" and predicted == "UNKNOWN",
                }
            )
        unspecified_violations = sorted(
            clause
            for clause in CLAUSES
            if clause not in expected and result["clauses"][clause]["status"] == "VIOLATION"
        )
        cases.append(
            {
                "case_id": case_id,
                "case_class": case["case_class"],
                "target_clause": case["target_clause"],
                "expected_clauses": expected,
                "predicted_clauses": {
                    clause: result["clauses"][clause]["status"] for clause in CLAUSES
                },
                "correct": all(scored_predictions[name] == truth for name, truth in expected.items()),
                "cross_clause_side_effects": unspecified_violations,
                "oracle_status": result["status"],
                "evidence_completeness": result["evidence_completeness"],
                "mutation_report": mutation_report,
                "raw_result": _display_path(result_path),
            }
        )

    matrix_path = processed_dir / "clause_confusion_matrix.tsv"
    fields = [
        "case_id",
        "case_class",
        "target_clause",
        "clause",
        "true_status",
        "predicted_status",
        "correct",
        "false_positive",
        "false_negative",
        "unexpected_unknown",
    ]
    with matrix_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "schema_version": "1.0",
        "oracle_version": "0.3",
        "manifest": _display_path(manifest_path),
        "oracle_validation_profile": manifest["oracle_validation_profile"],
        "threshold_profile": {"id": threshold_profile["id"], "thresholds": thresholds},
        "case_count": len(cases),
        "scored_clause_count": len(rows),
        "correct_clause_count": sum(bool(row["correct"]) for row in rows),
        "normal_case_false_positive_count": sum(
            bool(row["false_positive"])
            for row in rows
            if row["case_class"] in {"PASS", "NOT_APPLICABLE"}
        ),
        "mutant_detection_count": sum(
            row["true_status"] == "VIOLATION" and row["predicted_status"] == "VIOLATION"
            for row in rows
        ),
        "mutant_miss_count": sum(bool(row["false_negative"]) for row in rows),
        "incomplete_evidence_unknown_count": sum(
            row["true_status"] == "UNKNOWN" and row["predicted_status"] == "UNKNOWN"
            for row in rows
        ),
        "unexpected_unknown_count": sum(bool(row["unexpected_unknown"]) for row in rows),
        "all_expected_predictions_match": all(bool(row["correct"]) for row in rows),
        "cases": cases,
    }
    (processed_dir / "case_results.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "experiments" / "oracle_validation" / "trace_cases.yaml",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "runs" / "oracle_validation" / "trace_mutations",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=ROOT / "data" / "processed" / "oracle_validation",
    )
    args = parser.parse_args()
    summary = run_suite(args.manifest, args.output_root, args.processed_dir)
    print(
        json.dumps(
            {
                "case_count": summary["case_count"],
                "all_expected_predictions_match": summary[
                    "all_expected_predictions_match"
                ],
                "output": str(args.processed_dir),
            },
            sort_keys=True,
        )
    )
    return 0 if summary["all_expected_predictions_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
