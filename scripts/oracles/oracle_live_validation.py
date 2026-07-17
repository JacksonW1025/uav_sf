#!/usr/bin/env python3
"""Run bounded hover-SITL controls and test-only Route Oracle live mutants."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.oracles.route_oracle_v0 import run as run_oracle


MATRIX = ROOT / "experiments" / "oracle_validation" / "live_mutants.tsv"
CANONICAL_DIR = ROOT / "external" / "PX4-Autopilot-oracle-validation-control"
MUTANT_DIR = ROOT / "external" / "PX4-Autopilot-oracle-validation-mutant"


def load_matrix(path: Path = MATRIX) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    required = {
        "case_id",
        "sut_profile",
        "mutant_type",
        "delay_ms",
        "repeat",
        "expected_profile",
    }
    if not rows or set(rows[0]) != required:
        raise ValueError("live mutant matrix header does not match the locked contract")
    if len({row["case_id"] for row in rows}) != len(rows):
        raise ValueError("live mutant case IDs must be unique")
    return rows


def expected_assertions(row: dict[str, str]) -> list[dict[str, Any]]:
    mutant_type = row["mutant_type"]
    if mutant_type == "control":
        return [
            {
                "selector": [17, 14],
                "clause": "installation",
                "expected": "PASS",
            },
            {"selector": [14, 4], "clause": "revocation", "expected": "PASS"},
            {"selector": [14, 4], "clause": "recovery", "expected": "PASS"},
        ]
    if mutant_type == "install_delay":
        return [
            {
                "selector": [17, 14],
                "clause": "installation",
                "expected": (
                    "VIOLATION"
                    if row["expected_profile"] == "above_threshold"
                    else "PASS"
                ),
            }
        ]
    if mutant_type == "recovery_incomplete":
        return [
            {"selector": [14, 4], "clause": "recovery", "expected": "VIOLATION"}
        ]
    if mutant_type == "old_route_late_consumption":
        return [
            {"selector": [14, 4], "clause": "revocation", "expected": "VIOLATION"},
            {"selector": [14, 4], "clause": "recovery", "expected": "VIOLATION"},
        ]
    raise ValueError(f"unsupported live mutant type: {mutant_type}")


def _run_case(row: dict[str, str], run_root: Path) -> dict[str, Any]:
    case_id = row["case_id"]
    case_dir = run_root / case_id
    processed_root = case_dir / "processed"
    # run_p0_scenario treats P0_PROCESSED_ROOT as a campaign root and appends
    # RUN_ID, matching its canonical data/processed/p0/<run_id> layout.
    processed = processed_root / case_id
    result_path = case_dir / "live_result.json"
    if result_path.exists():
        return json.loads(result_path.read_text(encoding="utf-8"))
    case_dir.mkdir(parents=True, exist_ok=True)
    px4_dir = CANONICAL_DIR if row["sut_profile"] == "canonical" else MUTANT_DIR
    environment = os.environ.copy()
    environment.update(
        {
            "PX4_OBSERVABILITY_DIR": str(px4_dir),
            "P0_RUN_ROOT": str(run_root / "raw_runs"),
            "P0_PROCESSED_ROOT": str(processed_root),
            "P0_HOVER_ONLY": "1",
            "P0_ACTIVE_DURATION_S": "4",
            "P0_OBSERVATION_PROFILE": "TRANSITION",
            "P0_UORB_QUEUE_LENGTH": "4",
            "ROS_DISTRO_SETUP": environment.get(
                "ORACLE_LIVE_ROS_DISTRO_SETUP", "/opt/ros/humble/setup.bash"
            ),
            "ROS_WORKSPACE_SETUP": environment.get(
                "ORACLE_LIVE_ROS_WORKSPACE_SETUP",
                str(ROOT / "ros2_ws_humble_live" / "install" / "setup.bash"),
            ),
            "MICROXRCE_AGENT_BIN": environment.get(
                "ORACLE_LIVE_MICROXRCE_AGENT_BIN", "/usr/local/bin/MicroXRCEAgent"
            ),
            "MICROXRCE_AGENT_LD_LIBRARY_PATH": environment.get(
                "ORACLE_LIVE_MICROXRCE_AGENT_LD_LIBRARY_PATH", "/usr/local/lib"
            ),
        }
    )
    environment.pop("UAV_SF_ORACLE_MUTANT_MODE", None)
    environment.pop("UAV_SF_ORACLE_MUTANT_DELAY_MS", None)
    if row["sut_profile"] == "mutant":
        environment["UAV_SF_ORACLE_MUTANT_MODE"] = row["mutant_type"]
        environment["UAV_SF_ORACLE_MUTANT_DELAY_MS"] = row["delay_ms"]

    started = time.monotonic()
    with (case_dir / "scenario.log").open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            [str(ROOT / "scripts" / "probes" / "run_p0_scenario.sh"), "offboard", case_id],
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=240,
        )
    elapsed = time.monotonic() - started
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "case_id": case_id,
        "sut_profile": row["sut_profile"],
        "mutant_type": row["mutant_type"],
        "delay_ms": int(row["delay_ms"]),
        "repeat": int(row["repeat"]),
        "expected_profile": row["expected_profile"],
        "scenario_exit_code": completed.returncode,
        "elapsed_s": elapsed,
        "classification": "ENVIRONMENT_FAILURE" if completed.returncode else "VALID",
        "assertions": [],
    }
    if completed.returncode == 0:
        trace = processed / "route_trace.jsonl"
        clock_path = processed / "clock_bridge.json"
        clock = (
            json.loads(clock_path.read_text(encoding="utf-8"))
            if clock_path.exists()
            else None
        )
        oracle_cache: dict[tuple[int, int], dict[str, Any]] = {}
        for assertion in expected_assertions(row):
            selector = tuple(assertion["selector"])
            if selector not in oracle_cache:
                oracle_cache[selector] = run_oracle(
                    trace,
                    clock,
                    ground_truth_case_id=case_id,
                    oracle_validation_profile="live-mutant-v1",
                    threshold_profile_id="oracle-validation-preregistered-v1",
                    source_artifact_complete=True,
                    transition_source_mode=selector[0],
                    transition_target_mode=selector[1],
                )
                selector_output = processed / f"route_oracle_{selector[0]}_{selector[1]}.json"
                selector_output.write_text(
                    json.dumps(oracle_cache[selector], indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            prediction = oracle_cache[selector]["clauses"][assertion["clause"]]["status"]
            result["assertions"].append(
                {
                    **assertion,
                    "predicted": prediction,
                    "correct": prediction == assertion["expected"],
                }
            )
        result["all_assertions_match"] = all(
            assertion["correct"] for assertion in result["assertions"]
        )
    else:
        result["all_assertions_match"] = False
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def run_campaign(
    rows: list[dict[str, str]],
    run_root: Path,
    output: Path,
    case_pattern: str | None = None,
) -> dict[str, Any]:
    selected = (
        [row for row in rows if re.search(case_pattern, row["case_id"])]
        if case_pattern
        else rows
    )
    results = [_run_case(row, run_root) for row in selected]
    summary = {
        "schema_version": "1.0",
        "oracle_version": "0.3",
        "threshold_profile_id": "oracle-validation-preregistered-v1",
        "case_count": len(results),
        "valid_case_count": sum(result["classification"] == "VALID" for result in results),
        "environment_failure_count": sum(
            result["classification"] == "ENVIRONMENT_FAILURE" for result in results
        ),
        "assertion_count": sum(len(result["assertions"]) for result in results),
        "correct_assertion_count": sum(
            assertion["correct"]
            for result in results
            for assertion in result["assertions"]
        ),
        "all_expected_predictions_match": bool(results)
        and all(result["all_assertions_match"] for result in results),
        "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=MATRIX)
    parser.add_argument(
        "--run-root",
        type=Path,
        default=ROOT / "runs" / "oracle_validation" / "live",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "processed" / "oracle_validation" / "live_case_results.json",
    )
    parser.add_argument("--case-pattern")
    args = parser.parse_args()
    summary = run_campaign(
        load_matrix(args.matrix), args.run_root, args.output, args.case_pattern
    )
    print(
        json.dumps(
            {
                "case_count": summary["case_count"],
                "valid_case_count": summary["valid_case_count"],
                "environment_failure_count": summary["environment_failure_count"],
                "all_expected_predictions_match": summary[
                    "all_expected_predictions_match"
                ],
            },
            sort_keys=True,
        )
    )
    return 0 if summary["all_expected_predictions_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
