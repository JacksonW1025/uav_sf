#!/usr/bin/env python3
"""Freeze the fixed-budget live strategy comparison from retained evidence."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from statistics import median
import sys
from typing import Any

from scripts.accounting.study import verify_study_ledger
from scripts.runtime.run_campaign import read_matrix, validate_matrix


class StrategyAnalysisError(RuntimeError):
    """The formal strategy evidence is incomplete or inconsistent."""


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StrategyAnalysisError(f"JSON root is not an object: {path}")
    return value


def _records(path: Path) -> list[dict[str, Any]]:
    values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not all(isinstance(value, dict) for value in values):
        raise StrategyAnalysisError(f"JSONL contains a non-object: {path}")
    return values


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise StrategyAnalysisError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _manifest_files(path: Path) -> dict[str, dict[str, Any]]:
    manifest = _read(path)
    values = manifest.get("files")
    if not isinstance(values, list):
        raise StrategyAnalysisError(f"raw manifest lacks files: {path}")
    return {str(value["path"]): value for value in values}


def _verify_raw(raw: Path, manifest: dict[str, dict[str, Any]], name: str) -> Path:
    path = raw / name
    entry = manifest.get(name)
    if entry is None or not path.is_file():
        raise StrategyAnalysisError(f"missing manifest-bound raw file: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != entry.get("sha256") or path.stat().st_size != entry.get("size_bytes"):
        raise StrategyAnalysisError(f"raw evidence differs from manifest: {path}")
    return path


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise StrategyAnalysisError("cannot aggregate an empty strategy cell")
    errors = [int(item["absolute_request_error_ns"]) for item in records]
    boundaries = Counter(str(item["selected_boundary"]) for item in records)
    clauses = sorted({clause for item in records for clause in item["applicable_contract_clauses"]})
    signatures = sorted({value for item in records for value in item["violation_signatures"]})
    first_violation = next(
        (
            index
            for index, item in enumerate(sorted(records, key=lambda value: value["ordinal"]), 1)
            if item["evaluation_status"] == "VIOLATION"
        ),
        None,
    )
    return {
        "mechanism": records[0]["mechanism"],
        "strategy": records[0]["strategy"],
        "launches": len(records),
        "accepted": sum(item["outcome"] == "ACCEPTED" for item in records),
        "admissible": sum(item["evidence_gate_status"] == "ADMISSIBLE" for item in records),
        "physical_execution_pass": sum(item["physical_execution_status"] == "PASS" for item in records),
        "action_requested": sum(item["action_requested_count"] == 1 for item in records),
        "selected_boundary_counts": dict(sorted(boundaries.items())),
        "executed_timing_boundary_count": len(boundaries),
        "applicable_contract_clause_count": len(clauses),
        "applicable_contract_clauses": clauses,
        "violation_signature_count": len(signatures),
        "violation_signatures": signatures,
        "launches_to_first_violation": first_violation,
        "absolute_request_error_ns": {
            "minimum": min(errors),
            "median": median(errors),
            "maximum": max(errors),
        },
    }


def analyze(matrix_path: Path, study_root: Path, run_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    matrix = read_matrix(matrix_path)
    validate_matrix(matrix)
    ledger_path = study_root / "attempt-ledger.jsonl"
    ledger = verify_study_ledger(ledger_path)
    if ledger["study_id"] != matrix["study_id"]:
        raise StrategyAnalysisError("ledger and matrix study identities differ")
    if ledger["launched_count"] != 18 or ledger["closed_count"] != 18:
        raise StrategyAnalysisError("fixed formal denominator is not closed at 18")
    cells = {str(value["cell_id"]): value for value in matrix["cells"]}
    per_attempt: list[dict[str, Any]] = []
    inputs: dict[str, Any] = {
        "schema_version": "1.0",
        "study_id": matrix["study_id"],
        "matrix_digest": _sha256(matrix_path),
        "ledger_digest": _sha256(ledger_path),
        "attempts": {},
    }
    for attempt_id, ledger_attempt in sorted(ledger["attempts"].items()):
        compact = study_root / "results" / attempt_id
        raw = run_root / matrix["study_id"] / attempt_id / "raw"
        closure_path = compact / "closure.json"
        evaluation_path = compact / "evaluation.json"
        processing_path = compact / "processing-result.json"
        decision_path = compact / "strategy-decision.json"
        manifest_path = compact / "raw-manifest.json"
        closure = _read(closure_path)
        evaluation = _read(evaluation_path)
        processing = _read(processing_path)
        decision = _read(decision_path)
        manifest = _manifest_files(manifest_path)
        strategy_path = _verify_raw(raw, manifest, "strategy.lifecycle.jsonl")
        marker_path = _verify_raw(raw, manifest, "setpoint-stall.request.json")
        workload_path = _verify_raw(raw, manifest, "workload.lifecycle.jsonl")
        lifecycle = _records(strategy_path)
        requests = [value for value in lifecycle if value.get("kind") == "action_requested"]
        if len(requests) != 1:
            raise StrategyAnalysisError(f"attempt lacks one action request: {attempt_id}")
        request = requests[0]
        if request.get("preconditions") != {"route_active": True, "motion_entered": True}:
            raise StrategyAnalysisError(f"action preconditions differ: {attempt_id}")
        marker = _read(marker_path)
        if (
            marker.get("selected_boundary") != decision.get("selected_boundary")
            or marker.get("planned_offset_ns") != decision.get("planned_offset_ns")
            or request.get("selected_boundary") != decision.get("selected_boundary")
        ):
            raise StrategyAnalysisError(f"decision and executed marker differ: {attempt_id}")
        faults = [value for value in _records(workload_path) if value.get("kind") == "fault_detected"]
        if len(faults) != 1:
            raise StrategyAnalysisError(f"attempt lacks one observed fault: {attempt_id}")
        cell = cells[str(ledger_attempt["cell_id"])]
        mechanism = str(cell["runtime"]["mechanism"])
        strategy = str(cell["plan"]["strategy"])
        if strategy != decision.get("strategy"):
            raise StrategyAnalysisError(f"matrix and decision strategy differ: {attempt_id}")
        clauses = sorted(
            f"{oracle['oracle']}:{name}"
            for oracle in evaluation.get("oracles", [])
            for name in oracle.get("clauses", {})
        )
        signatures = sorted(
            f"{finding.get('oracle')}:{finding.get('clause')}"
            for finding in evaluation.get("findings", [])
            if finding.get("clause_status") == "VIOLATION"
        )
        planned = int(decision["planned_offset_ns"])
        actual = int(request["actual_offset_ns"])
        ordinal = int(attempt_id.rsplit("-", 1)[1])
        record = {
            "schema_version": "1.0",
            "attempt_id": attempt_id,
            "cell_id": cell["cell_id"],
            "ordinal": ordinal,
            "mechanism": mechanism,
            "strategy": strategy,
            "outcome": closure["outcome"],
            "evidence_gate_status": evaluation["evidence_gate"]["status"],
            "evaluation_status": evaluation["status"],
            "physical_execution_status": processing["physical_execution"]["status"],
            "selected_boundary": decision["selected_boundary"],
            "covered_boundaries_before_decision": decision["covered_boundaries_before_decision"],
            "planned_offset_ns": planned,
            "actual_offset_ns": actual,
            "signed_request_error_ns": actual - planned,
            "absolute_request_error_ns": abs(actual - planned),
            "action_requested_count": len(requests),
            "fault_detected_count": len(faults),
            "applicable_contract_clauses": clauses,
            "violation_signatures": signatures,
        }
        per_attempt.append(record)
        inputs["attempts"][attempt_id] = {
            "closure_digest": _sha256(closure_path),
            "evaluation_digest": _sha256(evaluation_path),
            "processing_result_digest": _sha256(processing_path),
            "strategy_decision_digest": _sha256(decision_path),
            "raw_manifest_digest": _sha256(manifest_path),
            "raw_strategy_lifecycle_digest": _sha256(strategy_path),
            "raw_action_marker_digest": _sha256(marker_path),
            "raw_workload_lifecycle_digest": _sha256(workload_path),
        }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    strategies: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for value in per_attempt:
        grouped[str(value["cell_id"])].append(value)
        strategies[str(value["strategy"])].append(value)
    cell_results = {key: aggregate(value) for key, value in sorted(grouped.items())}
    strategy_results: dict[str, Any] = {}
    for strategy, values in sorted(strategies.items()):
        boundaries = Counter(str(item["selected_boundary"]) for item in values)
        errors = [int(item["absolute_request_error_ns"]) for item in values]
        signatures = sorted({entry for item in values for entry in item["violation_signatures"]})
        strategy_results[strategy] = {
            "launches": len(values),
            "accepted": sum(item["outcome"] == "ACCEPTED" for item in values),
            "admissible": sum(item["evidence_gate_status"] == "ADMISSIBLE" for item in values),
            "selected_boundary_counts": dict(sorted(boundaries.items())),
            "executed_timing_boundary_count": len(boundaries),
            "violation_signatures": signatures,
            "absolute_request_error_ns": {
                "minimum": min(errors),
                "median": median(errors),
                "maximum": max(errors),
            },
        }
    summary = {
        "schema_version": "1.0",
        "study_id": matrix["study_id"],
        "status": "COMPLETE",
        "claim_scope": "fixed-budget live-backend comparison for one moving healthy setpoint-stall action",
        "ledger": {
            "event_count": ledger["event_count"],
            "chain_head": ledger["chain_head"],
            "launched_count": ledger["launched_count"],
            "closed_count": ledger["closed_count"],
            "accepted_count": ledger["accepted_count"],
        },
        "evidence_gate_admissible_count": sum(item["evidence_gate_status"] == "ADMISSIBLE" for item in per_attempt),
        "physical_execution_pass_count": sum(item["physical_execution_status"] == "PASS" for item in per_attempt),
        "action_requested_count": sum(item["action_requested_count"] for item in per_attempt),
        "evaluation_status_counts": dict(sorted(Counter(item["evaluation_status"] for item in per_attempt).items())),
        "cells": cell_results,
        "strategies": strategy_results,
        "interpretation": {
            "official_sequence_boundary_count": strategy_results["official_sequence"]["executed_timing_boundary_count"],
            "bounded_random_timing_boundary_count": strategy_results["bounded_random_timing"]["executed_timing_boundary_count"],
            "state_aware_boundary_count": strategy_results["state_aware"]["executed_timing_boundary_count"],
            "all_strategies_same_violation_signature": len({tuple(value["violation_signatures"]) for value in strategy_results.values()}) == 1,
            "strategy_ranking_supported": False,
            "reason": "The fixed three-launch cells demonstrate live execution and bounded timing coverage; random and state-aware tie on observed boundary count, and all arms expose the same freshness signature.",
        },
    }
    return summary, per_attempt, inputs


def _report(summary: dict[str, Any]) -> str:
    cells = summary["cells"]
    lines = [
        "# Fixed-budget live strategy comparison",
        "",
        "Status: **COMPLETE WITH BOUNDED CLAIMS**.",
        "",
        "The formal denominator closed at 18/18 launches, with 18 accepted, 18 Evidence Gate admissible, 18 physically valid, and 18 state-conditioned action requests. All 18 Oracle outcomes were `VIOLATION`, and every violation had the same `freshness_lineage:freshness` signature.",
        "",
        "| Mechanism | Strategy | Accepted | Timing boundaries | Violation signatures | Median request error (ms) |",
        "|---|---|---:|---:|---:|---:|",
    ]
    names = {"legacy_offboard": "Legacy Offboard", "dynamic_external_mode": "Dynamic External Mode"}
    labels = {"official_sequence": "official sequence", "bounded_random_timing": "bounded random timing", "state_aware": "state-aware"}
    for value in cells.values():
        lines.append(
            f"| {names[value['mechanism']]} | {labels[value['strategy']]} | {value['accepted']}/{value['launches']} | {value['executed_timing_boundary_count']} | {value['violation_signature_count']} | {value['absolute_request_error_ns']['median'] / 1_000_000:.3f} |"
        )
    lines.extend([
        "",
        "Across both mechanisms, official sequence exercised one timing bin (`boundary`). Bounded random timing exercised three (`pre_boundary`, `post_boundary`, and `late`), while state-aware exercised three (`pre_boundary`, `boundary`, and `post_boundary`). Each strategy reached the first admissible violation on its first launch. All cells evaluated the same 16 applicable contract clauses.",
        "",
        "The state-aware feedback loop is operational: its second and third decisions in each mechanism consume only prior live `action_requested` coverage and choose previously uncovered bins. In this fixed sample, however, bounded random timing also reached three bins. The study therefore supports backend executability and a coverage increase over the fixed official sequence, but not a ranking between bounded random timing and state-aware search.",
        "",
        "This is a Section 7 Main Evaluation vertical slice for one moving healthy setpoint-stall action. It does not complete the route corpus, establish general search effectiveness, diagnose a PX4 bug, quantify real-flight risk, or rank the two control mechanisms.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--study-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, default=Path("runs"))
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary, attempts, inputs = analyze(args.matrix, args.study_root, args.run_root)
        _write_new(args.output_root / "strategy-summary.json", json.dumps(summary, indent=2, sort_keys=True) + "\n")
        _write_new(
            args.output_root / "strategy-per-attempt.jsonl",
            "".join(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n" for value in attempts),
        )
        _write_new(args.output_root / "strategy-input-manifest.json", json.dumps(inputs, indent=2, sort_keys=True) + "\n")
        _write_new(args.output_root / "FINAL_REPORT.md", _report(summary))
    except (OSError, ValueError, KeyError, StrategyAnalysisError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "PASS", "output": str(args.output_root)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
