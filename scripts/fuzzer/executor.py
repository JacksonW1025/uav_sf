"""Allowlisted SITL compiler and executor for Fuzzer v0 cases."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from .case_model import (
    ROOT,
    case_digest,
    duplicate_fingerprint,
    validate_case,
    validate_result,
    write_case,
)
from .fitness import calculate_fitness
from .validity import REQUIRED_CHECKS, classify_with_oracle
from scripts.probes.p5_runner import (
    classify_attempt,
    command_for,
    environment_for,
)


DEFAULT_RUN_ROOT = ROOT / "runs/fuzzer_v0/evaluations"
DEPENDENCY_LOCK = ROOT / "config/dependencies.lock.yaml"
PX4_DIR = ROOT / "external/PX4-Autopilot-oracle-validation-control"


class UnsupportedCase(ValueError):
    """A valid grammar case is outside the executable v0 probe subset."""


def _mechanism(case: dict[str, Any]) -> str:
    routes = {case["source_route"], case["target_route"]}
    if "dynamic_external_mode" in routes:
        return "dynamic_external_mode"
    if "legacy_offboard" in routes:
        return "legacy_offboard"
    raise UnsupportedCase("case contains no external route mechanism")


def transition_class(case: dict[str, Any]) -> str:
    kinds = {event["kind"] for event in case["transition_events"]}
    if "process_sigterm" in kinds:
        return "T4"
    if "process_sigkill" in kinds:
        return "T5"
    if "process_pause" in kinds:
        return "T6"
    states = case["channel_states"]
    if any(state["liveness"] == "on" and state["setpoint"] == "off" for state in states):
        return "T7"
    if any(state["liveness"] == "off" and state["setpoint"] == "on" for state in states):
        return "T8"
    if "activate" in kinds and case["source_route"] == "internal_takeoff":
        return "T1"
    if "complete" in kinds and case["target_route"] == "internal_hold":
        return "T2"
    raise UnsupportedCase("case does not compile to an allowlisted v0 probe")


def compile_row(case: dict[str, Any], evaluation_id: str) -> dict[str, Any]:
    transition = transition_class(case)
    mechanism = _mechanism(case)
    return {
        "run_id": evaluation_id,
        "pair_id": evaluation_id,
        "cell_id": f"fuzz_{transition.lower()}",
        "transition_class": transition,
        "context": case["behavior_context"],
        "action": transition.lower(),
        "mechanism": mechanism,
        "simulation_seed": int(case["repetition"]["simulation_seed"]),
        "repeat": 1,
        "fault_offset_s": float(case["timing"]["fault_offset_s"]),
        "fallback_mode": case["fallback_route"],
        "status": "PLANNED",
    }


def _revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PX4_DIR, check=True, text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _checks_for(validity: str, reasons: list[str]) -> dict[str, str]:
    checks = {name: "PASS" for name in REQUIRED_CHECKS}
    checks["fault_delivered"] = "PASS"
    checks["target_or_fallback_observed"] = "PASS"
    joined = " ".join(reasons)
    if validity == "ENVIRONMENT_FAILURE":
        for key in ("px4_alive", "gazebo_alive", "ulog_produced"):
            checks[key] = "FAIL"
    elif validity == "MEASUREMENT_UNKNOWN":
        if "clock_bridge" in joined:
            checks["clock_bridge"] = "FAIL"
        if "critical_window" in joined or "selected_oracle" in joined:
            checks["critical_window"] = "FAIL"
    return checks


def _base_result(
    case: dict[str, Any], evaluation_id: str, classification: str, checks: dict[str, str],
    *, run_root: Path, oracle: dict[str, Any] | None, reason: str | None,
    strategy: str, rng_seed: int,
) -> dict[str, Any]:
    target_clauses = sorted(
        clause
        for clause, value in (oracle or {}).get("clauses", {}).items()
        if isinstance(value, dict) and value.get("status") == "VIOLATION"
    )
    oracle_status = (oracle or {}).get("status", "NOT_RUN")
    duplicate = duplicate_fingerprint(case)
    fitness = calculate_fitness(
        classification,
        clause_metrics=[
            {"status": "VIOLATION", "value": 1, "threshold": 0, "uncertainty": 0}
            for _ in target_clauses
        ],
    )
    artifact_root = run_root / evaluation_id
    result = {
        "schema_version": "1.0",
        "evaluation_id": evaluation_id,
        "case_id": case["case_id"],
        "case_digest": case_digest(case),
        "classification": classification,
        "validity_checks": checks,
        "oracle": {
            "version": "0.3",
            "status": oracle_status,
            "target_clauses": target_clauses,
            "result_path": str((artifact_root / "fuzz_route_oracle.json").relative_to(ROOT))
            if oracle is not None else None,
        },
        "fitness": fitness,
        "novelty": {"route_state": 0.0, "transition_sequence": 0.0},
        "duplicate_fingerprint": duplicate,
        "replay": {"status": "NOT_RUN", "attempts": 0, "matching_clause_count": 0},
        "provenance": {
            "strategy": strategy,
            "rng_seed": rng_seed,
            "simulation_seed": int(case["repetition"]["simulation_seed"]),
            "px4_revision": _revision(),
            "dependency_lock_digest": hashlib.sha256(DEPENDENCY_LOCK.read_bytes()).hexdigest(),
            "mutant_profile": (
                case["environment"]["profile"]
                if case["environment"]["profile"] != "canonical" else None
            ),
        },
        "artifacts": {
            "root": str(artifact_root.relative_to(ROOT)),
            "case": str((artifact_root / "case.json").relative_to(ROOT)),
            "trace": str((artifact_root / "route_trace.jsonl").relative_to(ROOT))
            if (artifact_root / "route_trace.jsonl").exists() else None,
            "oracle": str((artifact_root / "fuzz_route_oracle.json").relative_to(ROOT))
            if oracle is not None else None,
            "console": str((artifact_root / "console.log").relative_to(ROOT))
            if (artifact_root / "console.log").exists() else None,
        },
        "reason": reason,
    }
    return validate_result(result)


def execute_case(
    case: dict[str, Any],
    evaluation_id: str,
    *,
    run_root: Path = DEFAULT_RUN_ROOT,
    strategy: str = "seed_replay",
    rng_seed: int = 0,
) -> dict[str, Any]:
    validate_case(case, discovery_profile=True)
    run_root = run_root.resolve()
    artifact_root = run_root / evaluation_id
    artifact_root.mkdir(parents=True, exist_ok=True)
    write_case(case, artifact_root / "case.json")
    try:
        row = compile_row(case, evaluation_id)
    except UnsupportedCase as exc:
        checks = {name: "NOT_APPLICABLE" for name in REQUIRED_CHECKS}
        checks["armed"] = "FAIL"
        result = _base_result(
            case, evaluation_id, "INVALID_SETUP", checks, run_root=run_root,
            oracle=None, reason=str(exc), strategy=strategy, rng_seed=rng_seed,
        )
        (artifact_root / "result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return result

    command = command_for(row)
    if command is None:
        raise UnsupportedCase(f"no executable probe for {row['transition_class']}")
    environment = environment_for(row, run_root, artifact_root)
    if row["transition_class"] in {"T1", "T2"}:
        environment["P0_RUN_ROOT"] = str(run_root)
        environment["P0_PROCESSED_ROOT"] = str(run_root)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=float(case["timing"]["maximum_duration_s"]) + 30.0,
    )
    (artifact_root / "console.log").write_text(completed.stdout, encoding="utf-8")
    validity, reasons, oracle = classify_attempt(row, artifact_root, completed.returncode)
    if oracle is not None:
        (artifact_root / "fuzz_route_oracle.json").write_text(
            json.dumps(oracle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    checks = _checks_for(validity, reasons)
    classification, reason = classify_with_oracle(checks, oracle)
    if validity == "ENVIRONMENT_FAILURE":
        classification = "ENVIRONMENT_FAILURE"
        reason = "; ".join(reasons)
    elif validity == "MEASUREMENT_UNKNOWN":
        classification = "MEASUREMENT_UNKNOWN"
        reason = "; ".join(reasons)
    result = _base_result(
        case, evaluation_id, classification, checks, run_root=run_root,
        oracle=oracle, reason=reason, strategy=strategy, rng_seed=rng_seed,
    )
    (artifact_root / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result
