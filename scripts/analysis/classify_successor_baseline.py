#!/usr/bin/env python3
"""Classify one preregistered legal successor-baseline attempt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
P5_GATE = ROOT / "experiments/probes/p5/p5_v6_differential_gate.json"
P5_MANIFEST = ROOT / "experiments/probes/p5/campaign_seeded_v6_manifest.json"
P5_GATE_SHA256 = "9542eb7c98dfd4df1ab50026c149f21fb719fc6a2a09d040a9db4df647f132bc"
P5_MANIFEST_SHA256 = "02d857f555623c10dc44998cd202c2da6226ec5c40a94a75020d75df87f02518"


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def git_output(directory: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def attempt_classification(accepted: bool, infrastructure_abort: bool) -> str:
    if infrastructure_abort:
        return "ENVIRONMENT_FAILURE"
    return "ACCEPTED_BASELINE" if accepted else "EVIDENCE_OR_ORACLE_FAILURE"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--monitor", type=Path, required=True)
    parser.add_argument("--clock-bridge", type=Path, required=True)
    parser.add_argument("--route-oracle", type=Path, required=True)
    parser.add_argument("--successor-oracle", type=Path, required=True)
    parser.add_argument("--lifecycle-events", type=Path, required=True)
    parser.add_argument("--executor-log", type=Path, required=True)
    parser.add_argument("--route-trace", type=Path, required=True)
    parser.add_argument("--flight-log", type=Path, required=True)
    parser.add_argument("--executor-binary", type=Path, required=True)
    parser.add_argument("--library-binary", type=Path, required=True)
    parser.add_argument("--px4-dir", type=Path, required=True)
    parser.add_argument("--monitor-exit-code", type=int, default=0)
    parser.add_argument("--px4-exit-code", type=int, default=0)
    parser.add_argument("--px4-early-exit", type=int, choices=(0, 1), default=0)
    parser.add_argument("--executor-early-exit", type=int, choices=(0, 1), default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    monitor = load_json(args.monitor)
    clock = load_json(args.clock_bridge)
    route = load_json(args.route_oracle)
    successor = load_json(args.successor_oracle)
    route_clause_statuses = (
        {name: value.get("status") for name, value in route.get("clauses", {}).items()}
        if route
        else {}
    )
    successor_clause_statuses = (
        {
            name: value.get("status")
            for name, value in successor.get("clauses", {}).items()
        }
        if successor
        else {}
    )
    protected_hashes = {
        "p5_v6_differential_gate": sha256(P5_GATE),
        "p5_v6_manifest": sha256(P5_MANIFEST),
    }
    tracked_status = git_output(ROOT, "status", "--porcelain=v1", "--untracked-files=no")
    px4_commit = git_output(args.px4_dir, "rev-parse", "HEAD")
    library_commit = git_output(
        ROOT / "ros2_ws/src/px4_ros2_interface_lib", "rev-parse", "HEAD"
    )
    px4_binary_sha256 = sha256(args.px4_dir / "build/px4_sitl_default/bin/px4")
    library_binary_sha256 = sha256(args.library_binary)
    executor_binary_sha256 = sha256(args.executor_binary)
    monitor_reason = str(monitor.get("reason", "")) if monitor else ""
    infrastructure_abort = bool(
        args.px4_early_exit
        or args.executor_early_exit
        or "infrastructure process exited" in monitor_reason
    )
    checks = {
        "monitor_pass": monitor is not None and monitor.get("status") == "PASS",
        "clock_bridge_valid": clock is not None and clock.get("status") == "VALID",
        "route_oracle_pass": route is not None and route.get("status") == "PASS",
        "route_clauses_pass": bool(route_clause_statuses)
        and all(status == "PASS" for status in route_clause_statuses.values()),
        "successor_oracle_pass": successor is not None
        and successor.get("status") == "PASS",
        "successor_clauses_pass": bool(successor_clause_statuses)
        and all(status == "PASS" for status in successor_clause_statuses.values()),
        "raw_evidence_present": all(
            path.is_file()
            for path in (args.lifecycle_events, args.executor_log, args.flight_log)
        ),
        "canonical_route_trace_present": args.route_trace.is_file(),
        "p5_v6_gate_unchanged": protected_hashes["p5_v6_differential_gate"]
        == P5_GATE_SHA256,
        "p5_v6_manifest_unchanged": protected_hashes["p5_v6_manifest"]
        == P5_MANIFEST_SHA256,
        "tracked_worktree_clean": tracked_status == "",
        "px4_identity_exact": px4_commit
        == "4ae21a5e569d3d89c2f6366688cbacb3e93437c9"
        and px4_binary_sha256
        == "931320a07585dabf36ca9c8ba994756b93ee7d154cd9c8930b2171548d978993",
        "library_identity_exact": library_commit
        == "c3e410f035806e8c56246708432ded09c976434b"
        and library_binary_sha256
        == "dddfa0698c27617ce5a368dc7d0d5272bc510f3cb780c5ef3f48c77d098380e6",
        "executor_binary_present": executor_binary_sha256 is not None,
        "no_infrastructure_process_abort": not infrastructure_abort,
    }
    accepted = all(checks.values())
    artifacts = {
        "monitor_result": sha256(args.monitor),
        "clock_bridge": sha256(args.clock_bridge),
        "route_oracle": sha256(args.route_oracle),
        "successor_oracle": sha256(args.successor_oracle),
        "lifecycle_events": sha256(args.lifecycle_events),
        "executor_log": sha256(args.executor_log),
        "route_trace": sha256(args.route_trace),
        "flight_log": sha256(args.flight_log),
    }
    result = {
        "schema_version": "1.0",
        "study_id": "external_rtl_successor_issue_162",
        "attempt_kind": "legal_non_replacement_executor_successor_baseline",
        "run_id": args.run_id,
        "status": "ACCEPTED" if accepted else "REJECTED",
        "classification": attempt_classification(accepted, infrastructure_abort),
        "acceptance_checks": checks,
        "monitor_status": monitor.get("status") if monitor else None,
        "clock_bridge_status": clock.get("status") if clock else None,
        "route_oracle_status": route.get("status") if route else None,
        "route_clause_statuses": route_clause_statuses,
        "successor_oracle_status": successor.get("status") if successor else None,
        "successor_clause_statuses": successor_clause_statuses,
        "runtime": {
            "monitor_exit_code": args.monitor_exit_code,
            "px4_exit_code": args.px4_exit_code,
            "px4_early_exit": bool(args.px4_early_exit),
            "executor_early_exit": bool(args.executor_early_exit),
            "monitor_reason": monitor_reason or None,
        },
        "identity": {
            "repository_commit": git_output(ROOT, "rev-parse", "HEAD"),
            "tracked_worktree_clean_at_classification": tracked_status == "",
            "tracked_worktree_status": tracked_status.splitlines(),
            "px4_commit": px4_commit,
            "px4_binary_sha256": px4_binary_sha256,
            "px4_ros2_interface_lib_commit": library_commit,
            "px4_ros2_interface_lib_binary_sha256": library_binary_sha256,
            "executor_binary_sha256": executor_binary_sha256,
            "executor_source_sha256": sha256(
                ROOT
                / "scripts/adapters/external_mode_adapter/src/successor_baseline.cpp"
            ),
            "monitor_source_sha256": sha256(
                ROOT / "scripts/tracing/successor_lifecycle_monitor.py"
            ),
            "successor_oracle_source_sha256": sha256(
                ROOT / "scripts/oracles/successor_progression_oracle.py"
            ),
            "baseline_profile_sha256": sha256(
                ROOT
                / "experiments/motivation/successor/baseline_lifecycle_profile.yaml"
            ),
            "primary_preregistration_sha256": sha256(
                ROOT
                / "experiments/motivation/successor/primary_reproduction_preregistration.yaml"
            ),
        },
        "p5_v6_isolation": {
            "status": "PASS" if checks["p5_v6_gate_unchanged"] and checks["p5_v6_manifest_unchanged"] else "FAIL",
            "protected_hashes": protected_hashes,
        },
        "artifact_sha256": artifacts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
