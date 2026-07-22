#!/usr/bin/env python3
"""Validate the frozen M-FINAL evidence accounting and authorization boundary."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]
M_FINAL = ROOT / "experiments/motivation/m_final"
GATE_PATH = M_FINAL / "motivation_completion_gate.json"
SCHEMA_PATH = ROOT / "data/schemas/motivation_completion_gate.schema.json"
LEDGER_PATH = M_FINAL / "evidence_ledger.tsv"
SOURCE_LOCK_PATH = M_FINAL / "source_lock.yaml"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def read_tsv(path: Path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def assert_ancestor(commit: str, reference: str = "origin/main") -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, reference],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def validate() -> dict[str, int]:
    gate = read_json(GATE_PATH)
    schema = read_json(SCHEMA_PATH)
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(gate)

    ledger_rows = read_tsv(LEDGER_PATH)
    assert len(ledger_rows) == gate["evidence_units_total"] == 23
    ledger = {row["evidence_id"]: row for row in ledger_rows}
    assert len(ledger) == len(ledger_rows)

    for path in gate["source_reports"] + gate["source_gates"]:
        assert (ROOT / path).exists(), path
    for commit in gate["source_commits"]:
        assert_ancestor(commit)
    for row in ledger_rows:
        assert_ancestor(row["final_commit"])
        assert int(row["formal_attempts"]) == int(row["accepted"]) + int(row["rejected"])

    source_lock = read_yaml(SOURCE_LOCK_PATH)
    for artifact in source_lock["protected_artifacts"]:
        path = ROOT / artifact["path"]
        assert path.exists(), artifact["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]

    p0_results = [
        read_json(path)["status"]
        for path in sorted((ROOT / "data/processed/p0_phase_a2").glob("*/route_oracle.json"))
    ]
    assert len(p0_results) == 9 and p0_results.count("PASS") == 9
    assert (int(ledger["P0_NORMAL"]["accepted"]), int(ledger["P0_NORMAL"]["PASS_count"])) == (9, 9)

    with (ROOT / "experiments/probes/p2/experiment_matrix.tsv").open(encoding="utf-8", newline="") as handle:
        p2 = list(csv.DictReader(handle, delimiter="\t"))
    assert len(p2) == 18
    assert sum(row["route_oracle_status"] == "PASS" for row in p2) == 18
    assert int(ledger["P2_PROCESS_LOSS"]["accepted"]) == 18

    with (ROOT / "experiments/probes/p3/experiment_matrix.tsv").open(encoding="utf-8", newline="") as handle:
        p3 = list(csv.DictReader(handle, delimiter="\t"))
    p3_counts = {status: sum(row["route_oracle_status"] == status for row in p3) for status in ("PASS", "UNKNOWN")}
    assert len(p3) == 24 and p3_counts == {"PASS": 19, "UNKNOWN": 5}
    assert int(ledger["P3_CHANNEL_DECOUPLING"]["PASS_count"]) == 19
    assert int(ledger["P3_CHANNEL_DECOUPLING"]["UNKNOWN_count"]) == 5

    p5 = read_json(ROOT / "experiments/probes/p5/p5_v6_differential_gate.json")["evidence"]
    assert p5["accepted_attempt_count"] == int(ledger["P5_TRANSITION"]["accepted"]) == 70
    assert p5["environment_failure_count"] == int(ledger["P5_TRANSITION"]["rejected"]) == 25
    assert p5["oracle_pass_count"] == int(ledger["P5_TRANSITION"]["PASS_count"]) == 70

    freshness = read_json(ROOT / "experiments/motivation/freshness/freshness_pilot_gate.json")
    for cell_id in ("F1", "F2", "F3", "F4"):
        row = ledger[f"FRESHNESS_{cell_id}"]
        cell = freshness["cells"][cell_id]
        assert int(row["formal_attempts"]) == cell["total_attempts"]
        assert int(row["accepted"]) == cell["accepted_runs"]
    assert freshness["accepted_oracle_results"]["freshness"]["EXPOSURE"] == 10
    assert freshness["accepted_oracle_results"]["route"] == {"PASS": 9, "VIOLATION": 1, "UNKNOWN": 0}

    n1 = read_json(ROOT / "data/processed/motivation/n1_trajectory_residue/n1_adjudication.json")
    assert n1["formal_matrix"]["attempts"] == int(ledger["N1_FULL"]["formal_attempts"]) == 14
    assert n1["formal_matrix"]["accepted_runs"] == int(ledger["N1_FULL"]["accepted"]) == 8
    assert n1["formal_matrix"]["matching_violations"] == int(ledger["N1_FULL"]["VIOLATION_count"]) == 2
    assert n1["observation_reduced_confirmation"]["route_oracle"] == "PASS"

    c1 = read_json(ROOT / "experiments/motivation/c1_concurrency/c1_gate.json")
    assert (c1["formal_attempts"], c1["accepted_runs"], c1["accepted_oracle_pass"]) == (17, 14, 14)
    assert int(ledger["C1_MATRIX"]["rejected"]) == sum(c1["excluded_attempts"].values()) == 3

    r1 = read_json(ROOT / "experiments/motivation/r1_session/r1_gate.json")
    assert (r1["formal_attempts"], r1["accepted_runs"]) == (6, 0)
    assert int(ledger["R1_SESSION"]["accepted"]) == 0
    assert all(value == 0 for value in r1["oracle_outcomes"].values())

    w1 = read_json(ROOT / "data/processed/motivation/w1_workload/w1_summary.json")
    assert w1["source_trace"] == {
        "accepted": 0,
        "attempts": 3,
        "maximum_attempts": 3,
        "excluded_FORMAL_SAFETY_STOP": 3,
    }
    assert int(ledger["W1_RUNTIME"]["accepted"]) == 0

    b1 = read_json(ROOT / "data/processed/motivation/b1_family_b/b1_summary.json")
    assert b1["formal_accounting"]["build"]["accepted"] == 0
    assert b1["formal_accounting"]["build"]["attempts"] == 3
    assert b1["formal_accounting"]["normal"]["accepted"] == 0
    assert b1["formal_accounting"]["recovery"]["accepted"] == 0
    assert int(ledger["B1_RUNTIME"]["accepted"]) == 0

    accepted_issue_results = [
        ROOT / "data/processed/motivation/successor/historical/successor_historical_a5b9f3c_seed16214_r1/attempt_result.json",
        ROOT / "data/processed/motivation/successor/historical/successor_historical_a5b9f3c_seed16216_r1/attempt_result.json",
        ROOT / "data/processed/motivation/successor/historical/successor_historical_a5b9f3c_seed16217_r1/attempt_result.json",
        ROOT / "data/processed/motivation/successor/historical/successor_historical_reduced_seed16218_r1/attempt_result.json",
    ]
    for path in accepted_issue_results:
        result = read_json(path)
        assert result["status"] == "ACCEPTED"
        assert result["classification"] == "HISTORICAL_DEFECT_REPRODUCED"
        assert result["route_oracle_status"] == "NOT_APPLICABLE"
        assert result["successor_oracle_status"] == "VIOLATION"

    assert gate["authorizes_family_b_campaign"] is False
    assert gate["authorizes_real_workload_campaign"] is False
    assert gate["authorizes_random_campaign"] is False
    assert gate["authorizes_stateful_testing_full_campaign"] is False
    assert gate["authorizes_hitl"] is False
    assert gate["authorizes_real_flight"] is False
    assert gate["state_aware_search_gain_supported"] is False
    assert gate["full_fuzzing_effectiveness_supported"] is False

    tracked_runs = subprocess.run(
        ["git", "ls-files", "runs"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert tracked_runs == []
    assert gate["tracked_raw_files"] == 0

    current_narrative = (ROOT / "docs/narrative/CURRENT_NARRATIVE.md").read_text(encoding="utf-8")
    for stale in ("M-FINAL has not started", "M-FINAL is the exact next", "N1 is the next", "C1 is the next"):
        assert stale not in current_narrative

    statuses = {f"MG{i}": gate[f"mg{i}_status"] for i in range(1, 11)}
    assert statuses == {name: result["status"] for name, result in gate["mg_results"].items()}
    assert gate["disposition"] == "CONDITIONAL_PASS_MOTIVATION_COMPLETE_AUTHORIZE_FAMILY_A_FUZZER_V0"

    return {
        "evidence_units": len(ledger_rows),
        "source_reports": len(gate["source_reports"]),
        "source_gates": len(gate["source_gates"]),
        "source_commits": len(gate["source_commits"]),
        "tracked_raw_files": len(tracked_runs),
        "blocking_findings": sum(item["blocks_m_final"] for item in gate["consistency_findings"]),
    }


def main() -> None:
    result = validate()
    print("M-FINAL consistency check passed")
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
