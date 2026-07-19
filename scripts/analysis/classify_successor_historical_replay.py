#!/usr/bin/env python3
"""Classify one preregistered Issue #162 affected-version replay."""

from __future__ import annotations

import argparse
from collections import Counter
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
PX4_COMMIT = "6ea3539157ca358c70a515878b77077af7d4611d"
LIBRARY_COMMIT = "a5b9f3cb7cb65d2be80183bad31e9a7ce9f02684"
REQUIRED_DEFECT_CATEGORIES = {
    "EXECUTOR_NOT_IN_CHARGE",
    "COMPLETION_NOT_DELIVERED",
    "EXPECTED_SUCCESSOR_NOT_REQUESTED",
    "EXPECTED_SUCCESSOR_NOT_INSTALLED",
    "LIFECYCLE_DEAD_END",
    "UNEXPECTED_HOVER_AFTER_COMPLETION",
}


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def load_json(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def git_bytes(directory: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(directory), *args], check=True, capture_output=True
    ).stdout


def git_text(directory: Path, *args: str) -> str:
    return git_bytes(directory, *args).decode().strip()


def classify(
    *, infrastructure_abort: bool, observability_insufficient: bool, successor_status: str | None,
    defect_pattern_complete: bool,
) -> str:
    if infrastructure_abort:
        return "ENVIRONMENT_FAILURE"
    if observability_insufficient:
        return "OBSERVABILITY_INSUFFICIENT"
    if successor_status == "VIOLATION" and defect_pattern_complete:
        return "HISTORICAL_DEFECT_REPRODUCED"
    if successor_status == "PASS":
        return "NOT_REPRODUCED_ON_HISTORICAL"
    return "OBSERVABILITY_INSUFFICIENT"


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
    parser.add_argument("--library-source-dir", type=Path, required=True)
    parser.add_argument("--px4-dir", type=Path, required=True)
    parser.add_argument("--build-provenance", type=Path, required=True)
    parser.add_argument("--monitor-exit-code", type=int, default=0)
    parser.add_argument("--px4-exit-code", type=int, default=0)
    parser.add_argument("--executor-exit-code", type=int, default=0)
    parser.add_argument("--px4-early-exit", type=int, choices=(0, 1), default=0)
    parser.add_argument("--executor-early-exit", type=int, choices=(0, 1), default=0)
    parser.add_argument("--trigger-failure", type=int, choices=(0, 1), default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    monitor = load_json(args.monitor)
    clock = load_json(args.clock_bridge)
    route = load_json(args.route_oracle)
    successor = load_json(args.successor_oracle)
    provenance = load_json(args.build_provenance) or {}
    trace = load_jsonl(args.route_trace)
    lifecycle = load_jsonl(args.lifecycle_events)
    monitor_finished = next(
        (
            event
            for event in reversed(lifecycle)
            if event.get("event_type") == "monitor_finished"
        ),
        None,
    )
    final_landed = monitor_finished.get("landed") if monitor_finished else None
    registered_mode = monitor.get("registered_mode_id") if monitor else None
    source_trace = [event for event in trace if event.get("declared_mode") == registered_mode]
    source_counts = Counter(str(event.get("event_type")) for event in source_trace)
    source_chain = {
        "producer": source_counts["producer_still_publishing"],
        "controller_consumption": source_counts["px4_setpoint_consumed"],
        "allocator_input": source_counts["allocator_input_published"],
        "actuator_writer": source_counts["actuator_output_published"],
    }
    source_route_epoch = any(
        event.get("event_type") == "route_epoch_changed" for event in source_trace
    )
    land_route_epoch = any(
        event.get("event_type") == "route_epoch_changed"
        and event.get("declared_mode") == 18
        for event in trace
    )
    categories = set(successor.get("violation_categories", [])) if successor else set()
    completeness = successor.get("evidence_completeness", {}) if successor else {}
    required_completeness = {
        key: bool(completeness.get(key))
        for key in (
            "single_run_id",
            "registration",
            "external_activation",
            "completion_generated",
            "completion_public",
            "route_oracle",
            "clock_bridge_valid",
            "terminal_monitor",
        )
    }
    protected_hashes = {
        "p5_v6_differential_gate": sha256(P5_GATE),
        "p5_v6_manifest": sha256(P5_MANIFEST),
    }
    px4_diff_sha256 = hashlib.sha256(
        git_bytes(args.px4_dir, "diff", "--cached")
    ).hexdigest()
    px4_binary_sha256 = sha256(args.px4_dir / "build/px4_sitl_default/bin/px4")
    library_binary_sha256 = sha256(args.library_binary)
    executor_binary_sha256 = sha256(args.executor_binary)
    tracked_status = git_text(ROOT, "status", "--porcelain=v1", "--untracked-files=no")
    monitor_reason = str(monitor.get("reason", "")) if monitor else ""
    infrastructure_abort = bool(
        args.px4_early_exit
        or args.executor_early_exit
        or args.trigger_failure
        or args.px4_exit_code != 0
        or "infrastructure process exited" in monitor_reason
    )
    checks = {
        "raw_evidence_present": all(
            path.is_file()
            for path in (args.lifecycle_events, args.executor_log, args.flight_log)
        ),
        "canonical_route_trace_present": args.route_trace.is_file(),
        "clock_bridge_valid": clock is not None and clock.get("status") == "VALID",
        "monitor_window_complete": monitor is not None
        and monitor.get("status") in {"PASS", "COMPLETE_WITHOUT_TERMINAL"},
        "successor_oracle_decisive": successor is not None
        and successor.get("status") in {"PASS", "VIOLATION"},
        "route_oracle_decisive": route is not None
        and route.get("status") in {"PASS", "NOT_APPLICABLE"},
        "required_successor_evidence_complete": all(required_completeness.values()),
        "external_source_route_observed": source_route_epoch,
        "producer_controller_writer_observed": all(value > 0 for value in source_chain.values()),
        "tracked_worktree_clean": tracked_status == "",
        "px4_identity_exact": git_text(args.px4_dir, "rev-parse", "HEAD") == PX4_COMMIT
        and px4_binary_sha256
        == provenance.get("historical_px4", {}).get("binary_sha256")
        and px4_diff_sha256
        == provenance.get("historical_px4", {})
        .get("observation_patch", {})
        .get("diff_sha256"),
        "library_identity_exact": git_text(args.library_source_dir, "rev-parse", "HEAD")
        == LIBRARY_COMMIT
        and library_binary_sha256
        == provenance.get("px4_ros2_interface_lib_binary_sha256"),
        "executor_identity_exact": executor_binary_sha256
        == provenance.get("adapter_binary_sha256")
        and sha256(ROOT / "scripts/adapters/external_mode_adapter/src/issue162_replay.cpp")
        == provenance.get("adapter_source_sha256"),
        "p5_v6_gate_unchanged": protected_hashes["p5_v6_differential_gate"]
        == P5_GATE_SHA256,
        "p5_v6_manifest_unchanged": protected_hashes["p5_v6_manifest"]
        == P5_MANIFEST_SHA256,
        "no_infrastructure_process_abort": not infrastructure_abort,
    }
    observability_insufficient = not infrastructure_abort and not all(checks.values())
    defect_pattern_complete = bool(
        successor
        and successor.get("status") == "VIOLATION"
        and REQUIRED_DEFECT_CATEGORIES <= categories
        and monitor
        and monitor.get("status") == "COMPLETE_WITHOUT_TERMINAL"
        and monitor.get("land_selected_seen") is False
        and monitor.get("disarmed_seen") is False
        and final_landed is False
        and route
        and route.get("status") == "NOT_APPLICABLE"
        and route.get("transition") is None
        and not land_route_epoch
    )
    classification = classify(
        infrastructure_abort=infrastructure_abort,
        observability_insufficient=observability_insufficient,
        successor_status=successor.get("status") if successor else None,
        defect_pattern_complete=defect_pattern_complete,
    )
    accepted = classification in {
        "HISTORICAL_DEFECT_REPRODUCED",
        "NOT_REPRODUCED_ON_HISTORICAL",
    }
    artifacts = {
        name: sha256(path)
        for name, path in {
            "monitor_result": args.monitor,
            "clock_bridge": args.clock_bridge,
            "route_oracle": args.route_oracle,
            "successor_oracle": args.successor_oracle,
            "lifecycle_events": args.lifecycle_events,
            "executor_log": args.executor_log,
            "route_trace": args.route_trace,
            "flight_log": args.flight_log,
        }.items()
    }
    result = {
        "schema_version": "1.0",
        "study_id": "external_rtl_successor_issue_162",
        "attempt_kind": "historical_affected_external_rtl_successor_replay",
        "run_id": args.run_id,
        "status": "ACCEPTED" if accepted else "REJECTED",
        "classification": classification,
        "acceptance_checks": checks,
        "defect_pattern_complete": defect_pattern_complete,
        "successor_oracle_status": successor.get("status") if successor else None,
        "successor_clause_statuses": {
            name: value.get("status")
            for name, value in (successor.get("clauses", {}) if successor else {}).items()
        },
        "violation_categories": sorted(categories),
        "required_defect_categories": sorted(REQUIRED_DEFECT_CATEGORIES),
        "evidence_completeness": required_completeness,
        "route_oracle_status": route.get("status") if route else None,
        "route_oracle_interpretation": (
            "NOT_APPLICABLE_NO_SUCCESSOR_TRANSITION"
            if route and route.get("status") == "NOT_APPLICABLE"
            else None
        ),
        "route_chain_evidence": {
            **source_chain,
            "external_source_route_epoch": source_route_epoch,
            "land_route_epoch": land_route_epoch,
        },
        "mission_consequence": {
            "land_selected": bool(monitor and monitor.get("land_selected_seen")),
            "landed": final_landed,
            "disarmed": bool(monitor and monitor.get("disarmed_seen")),
            "hover_after_completion": "UNEXPECTED_HOVER_AFTER_COMPLETION" in categories,
        },
        "runtime": {
            "monitor_exit_code": args.monitor_exit_code,
            "px4_exit_code": args.px4_exit_code,
            "executor_exit_code": args.executor_exit_code,
            "px4_early_exit": bool(args.px4_early_exit),
            "executor_early_exit": bool(args.executor_early_exit),
            "trigger_failure": bool(args.trigger_failure),
            "monitor_status": monitor.get("status") if monitor else None,
            "monitor_reason": monitor_reason or None,
        },
        "identity": {
            "repository_commit": git_text(ROOT, "rev-parse", "HEAD"),
            "px4_commit": git_text(args.px4_dir, "rev-parse", "HEAD"),
            "px4_binary_sha256": px4_binary_sha256,
            "px4_observation_diff_sha256": px4_diff_sha256,
            "px4_ros2_interface_lib_commit": git_text(
                args.library_source_dir, "rev-parse", "HEAD"
            ),
            "px4_ros2_interface_lib_binary_sha256": library_binary_sha256,
            "executor_binary_sha256": executor_binary_sha256,
        },
        "p5_v6_isolation": {
            "status": (
                "PASS"
                if checks["p5_v6_gate_unchanged"] and checks["p5_v6_manifest_unchanged"]
                else "FAIL"
            ),
            "protected_hashes": protected_hashes,
        },
        "artifact_sha256": artifacts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"classification": classification, "output": str(args.output)}))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
