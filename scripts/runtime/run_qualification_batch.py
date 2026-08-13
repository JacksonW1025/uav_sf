#!/usr/bin/env python3
"""Run one non-formal qualification batch across a live/processing barrier."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from scripts.runtime.isolation import (
    allocate_isolation,
    verify_disjoint_cpu_sets,
    verify_unique,
)
from scripts.runtime.qualification_attempt import run as run_attempt


class QualificationBatchError(RuntimeError):
    """The non-formal batch cannot preserve its declared isolation contract."""


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QualificationBatchError(f"JSON root is not an object: {path}")
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _time() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _active_containers(study_id: str) -> list[str]:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            f"name=family-a-{study_id}-",
            "--format",
            "{{.Names}}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise QualificationBatchError("cannot verify the live-container barrier")
    return sorted(line for line in result.stdout.splitlines() if line.strip())


def _namespace(
    *,
    spec: dict[str, Any],
    attempt: dict[str, Any],
    run_root: Path,
    cpu_set: str,
    phase: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        image=str(spec["image"]),
        attestation=Path(spec["attestation"]),
        run_root=run_root,
        study_id=str(spec["study_id"]),
        run_id=str(attempt["run_id"]),
        phase=phase,
        mechanism=str(attempt["mechanism"]),
        source_route=str(attempt.get("source_route", "internal_hold")),
        successor_route=str(attempt.get("successor_route", "internal_land")),
        expected_fallback=str(attempt.get("expected_fallback", "internal_land")),
        setpoint_kind=str(attempt.get("setpoint_kind", "trajectory")),
        fault_mode=str(attempt.get("fault_mode", "normal")),
        health_loss=bool(attempt.get("health_loss", False)),
        duplicate_registration=bool(attempt.get("duplicate_registration", False)),
        repeat_count=int(attempt.get("repeat_count", 1)),
        target_activation_count=attempt.get("target_activation_count"),
        manual_land_offset_s=attempt.get("manual_land_offset_s"),
        target_activation_expected=bool(
            attempt.get("target_activation_expected", True)
        ),
        registration_rejection_expected=bool(
            attempt.get("registration_rejection_expected", False)
        ),
        activation_rejection_expected=bool(
            attempt.get("activation_rejection_expected", False)
        ),
        completion_expected=bool(attempt.get("completion_expected", True)),
        fault_expected=bool(attempt.get("fault_expected", False)),
        fallback_expected=bool(attempt.get("fallback_expected", False)),
        slot=int(attempt["slot"]),
        cpu_set=cpu_set,
        memory=str(spec["resources"]["memory_per_attempt"]),
        active_s=float(attempt.get("active_s", 8.0)),
        simulation_seed=int(attempt["simulation_seed"]),
        attempt_timeout_s=float(attempt.get("attempt_timeout_s", 90.0)),
        outer_timeout_s=float(attempt.get("outer_timeout_s", 160.0)),
        thresholds=Path(spec.get("thresholds", "config/method.defaults.json")),
        maximum_clock_uncertainty_ns=int(spec["maximum_clock_uncertainty_ns"]),
    )


def _parallel(
    arguments: list[SimpleNamespace], *, concurrency: int
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    results: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(run_attempt, value): value.run_id for value in arguments}
        for future in as_completed(futures):
            run_id = futures[future]
            try:
                results[run_id] = future.result()
            except Exception as exc:  # noqa: BLE001 - retain qualification failure verbatim
                errors[run_id] = f"{type(exc).__name__}: {exc}"
    return results, errors


def qualification_gate(
    spec: dict[str, Any],
    *,
    barrier_passed: bool,
    live_errors: dict[str, str],
    process_errors: dict[str, str],
    process_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    gate = spec.get("qualification_gate", {})
    concurrency = int(spec["concurrency"])
    values = list(process_results.values())
    accepted = sum(value.get("outcome") == "ACCEPTED" for value in values)
    ulog_pass = sum(value.get("ulog", {}).get("status") == "PASS" for value in values)
    maximum_clock = int(gate["maximum_clock_uncertainty_ns"])
    minimum_rtf = float(gate["minimum_central_real_time_factor"])
    clock_values = [
        value.get("clock_bridge", {}).get("uncertainty_ns")
        for value in values
        if isinstance(value.get("clock_bridge"), dict)
    ]
    rtf_values = [
        value.get("gazebo", {}).get("central_minimum")
        for value in values
        if value.get("gazebo", {}).get("central_minimum") is not None
    ]
    checks = {
        "barrier": barrier_passed,
        "no_driver_errors": not live_errors and not process_errors,
        "all_results_present": len(values) == concurrency,
        "admissible_fraction": (
            accepted / concurrency >= float(gate["required_admissible_fraction"])
        ),
        "ulog_integrity_fraction": (
            ulog_pass / concurrency
            >= float(gate["required_ulog_integrity_fraction"])
        ),
        "clock_uncertainty": (
            len(clock_values) == concurrency
            and all(int(value) <= maximum_clock for value in clock_values)
        ),
        "central_real_time_factor": (
            len(rtf_values) == concurrency
            and all(float(value) >= minimum_rtf for value in rtf_values)
        ),
        "isolation_and_cleanup": (
            not gate.get("require_zero_isolation_or_cleanup_failures", False)
            or all(value.get("runtime_outcome") == "ACCEPTED" for value in values)
        ),
    }
    failures = sorted(key for key, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failures": failures,
    }


def validate_spec(spec: dict[str, Any], *, run_root: Path) -> None:
    if spec.get("schema_version") != "1.0":
        raise QualificationBatchError("unsupported qualification spec")
    attempts = spec.get("attempts")
    resources = spec.get("resources", {})
    cpu_sets = resources.get("cpu_sets")
    concurrency = int(spec.get("concurrency", 0))
    if not isinstance(attempts, list) or len(attempts) != concurrency:
        raise QualificationBatchError("attempt count must equal concurrency")
    if not isinstance(cpu_sets, list) or len(cpu_sets) != concurrency:
        raise QualificationBatchError("one CPU set is required per attempt")
    if not str(resources.get("memory_per_attempt", "")):
        raise QualificationBatchError("per-attempt memory limit is required")
    try:
        verify_disjoint_cpu_sets(cpu_sets)
        allocations = [
            allocate_isolation(
                study_id=str(spec["study_id"]),
                attempt_id=str(attempt["run_id"]),
                slot=int(attempt["slot"]),
                run_root=run_root,
                cpu_sets=cpu_sets,
            )
            for attempt in attempts
        ]
        verify_unique(allocations)
    except (KeyError, TypeError, ValueError) as exc:
        raise QualificationBatchError(str(exc)) from exc
    if sorted(int(value["slot"]) for value in attempts) != list(range(concurrency)):
        raise QualificationBatchError("qualification slots must be contiguous and unique")
    run_ids = [str(value["run_id"]) for value in attempts]
    if len(run_ids) != len(set(run_ids)):
        raise QualificationBatchError("qualification run IDs must be unique")


def run(spec_path: Path, *, run_root: Path, output: Path) -> dict[str, Any]:
    spec = _read(spec_path)
    validate_spec(spec, run_root=run_root)
    if output.exists():
        raise QualificationBatchError(f"refusing to overwrite: {output}")
    study_root = run_root / str(spec["study_id"])
    if study_root.exists():
        raise QualificationBatchError(f"qualification study already exists: {study_root}")
    attestation = Path(spec["attestation"])
    if not attestation.is_file():
        raise QualificationBatchError(f"attestation is missing: {attestation}")
    study_root.mkdir(parents=True)
    shutil.copyfile(attestation, study_root / "environment.json")
    concurrency = int(spec["concurrency"])
    cpu_sets = spec["resources"]["cpu_sets"]
    live_arguments = [
        _namespace(
            spec=spec,
            attempt=attempt,
            run_root=run_root,
            cpu_set=cpu_sets[int(attempt["slot"])],
            phase="live",
        )
        for attempt in spec["attempts"]
    ]
    live_started = _time()
    live_results, live_errors = _parallel(
        live_arguments, concurrency=concurrency
    )
    live_completed = _time()
    active = _active_containers(str(spec["study_id"]))
    if active:
        raise QualificationBatchError(
            "live containers remain at the processing barrier: " + ", ".join(active)
        )

    process_started = _time()
    process_arguments = [
        _namespace(
            spec=spec,
            attempt=attempt,
            run_root=run_root,
            cpu_set=cpu_sets[int(attempt["slot"])],
            phase="process",
        )
        for attempt in spec["attempts"]
        if str(attempt["run_id"]) in live_results
    ]
    process_results, process_errors = _parallel(
        process_arguments, concurrency=concurrency
    )
    process_completed = _time()
    outcomes = Counter(str(value.get("outcome")) for value in process_results.values())
    result = {
        "schema_version": "1.0",
        "study_id": spec["study_id"],
        "spec_digest": _sha256(spec_path),
        "execution_model": "two_phase_barrier",
        "concurrency": concurrency,
        "live_phase": {
            "started_at": live_started,
            "completed_at": live_completed,
            "results": live_results,
            "errors": live_errors,
        },
        "processing_phase": {
            "started_at": process_started,
            "completed_at": process_completed,
            "results": process_results,
            "errors": process_errors,
        },
        "barrier": {
            "active_live_containers_before_processing": active,
            "passed": not active and len(live_results) == concurrency,
        },
        "outcomes": dict(sorted(outcomes.items())),
    }
    result["qualification_gate"] = qualification_gate(
        spec,
        barrier_passed=result["barrier"]["passed"],
        live_errors=live_errors,
        process_errors=process_errors,
        process_results=process_results,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, default=Path("runs"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.spec, run_root=args.run_root, output=args.output)
    except (OSError, ValueError, KeyError, QualificationBatchError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["qualification_gate"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
