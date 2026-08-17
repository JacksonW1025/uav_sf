#!/usr/bin/env python3
"""Compute digest-bound physical and paired results for the Stage A2 study."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any

from scripts.accounting.study import verify_study_ledger
from scripts.runtime.moving_workload import straight_line_target
from scripts.runtime.run_campaign import read_matrix, validate_matrix


class StageA2PhysicalError(RuntimeError):
    """The retained study cannot support the registered physical analysis."""


METRICS = (
    "along_track_lag_m",
    "cross_track_error_m",
    "integrated_absolute_along_track_error_m_s",
    "exposure_duration_s",
    "exposure_distance_m",
    "peak_horizontal_speed_m_s",
    "recovery_distance_m",
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StageA2PhysicalError(f"JSON root is not an object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise StageA2PhysicalError(f"non-object JSON at {path}:{number}")
        values.append(value)
    if not values:
        raise StageA2PhysicalError(f"empty JSONL input: {path}")
    return values


def _digest(path: Path, *, prefix: bool = True) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    return "sha256:" + value if prefix else value


def _round(value: float) -> float:
    return round(float(value), 9)


def _event_after(
    events: list[dict[str, Any]], kind: str, route: str, after_ns: int
) -> dict[str, Any]:
    candidates = [
        event
        for event in events
        if event.get("kind") == kind
        and event.get("route") == route
        and isinstance(event.get("timestamp_ns"), int)
        and int(event["timestamp_ns"]) >= after_ns
    ]
    if not candidates:
        raise StageA2PhysicalError(f"missing {kind} for {route} after {after_ns}")
    return min(candidates, key=lambda event: int(event["timestamp_ns"]))


def _positions(telemetry: list[dict[str, Any]]) -> list[dict[str, float | int]]:
    selected: list[dict[str, float | int]] = []
    for event in telemetry:
        if event.get("kind") != "vehicle_local_position":
            continue
        if not bool(event.get("xy_valid")) or not bool(event.get("z_valid")):
            continue
        values = [event.get(key) for key in ("x", "y", "z", "vx", "vy")]
        timestamp = event.get("received_monotonic_ns")
        if not isinstance(timestamp, int) or not all(
            isinstance(value, (int, float)) and math.isfinite(float(value))
            for value in values
        ):
            continue
        selected.append(
            {
                "timestamp_ns": timestamp,
                "x": float(values[0]),
                "y": float(values[1]),
                "z": float(values[2]),
                "vx": float(values[3]),
                "vy": float(values[4]),
            }
        )
    selected.sort(key=lambda value: int(value["timestamp_ns"]))
    return selected


def _nearest(values: list[dict[str, float | int]], timestamp_ns: int) -> dict[str, float | int]:
    if not values:
        raise StageA2PhysicalError("no valid local-position samples")
    return min(values, key=lambda value: abs(int(value["timestamp_ns"]) - timestamp_ns))


def _path_length(values: list[dict[str, float | int]], *, dimensions: int) -> float:
    total = 0.0
    for previous, current in zip(values, values[1:]):
        terms = [
            float(current[axis]) - float(previous[axis])
            for axis in ("x", "y", "z")[:dimensions]
        ]
        total += math.sqrt(sum(term * term for term in terms))
    return total


def compute_metrics(
    *,
    positions: list[dict[str, float | int]],
    activation_ns: int,
    completion_ns: int,
    successor_ns: int,
    landed_ns: int,
    settle_s: float,
    speed_m_s: float,
    distance_m: float,
    stall_after_s: float,
    fault_mode: str,
) -> dict[str, float | int | None]:
    """Compute the seven registered metrics and explicit descriptive endpoints."""

    active = [
        value
        for value in positions
        if activation_ns <= int(value["timestamp_ns"]) <= completion_ns
    ]
    recovery = [
        value
        for value in positions
        if successor_ns <= int(value["timestamp_ns"]) <= landed_ns
    ]
    if len(active) < 2 or len(recovery) < 2:
        raise StageA2PhysicalError("physical metric window lacks position coverage")
    scheduled_fault_ns = (
        activation_ns + int(stall_after_s * 1_000_000_000)
        if fault_mode == "setpoint_stall"
        else None
    )

    samples: list[tuple[int, float]] = []
    cross_track = 0.0
    peak_speed = 0.0
    for value in active:
        timestamp = int(value["timestamp_ns"])
        elapsed_s = max(0.0, (timestamp - activation_ns) / 1_000_000_000)
        reference_elapsed = (
            min(elapsed_s, stall_after_s)
            if scheduled_fault_ns is not None
            else elapsed_s
        )
        target_x = straight_line_target(
            reference_elapsed,
            settle_s=settle_s,
            speed_m_s=speed_m_s,
            distance_m=distance_m,
        )
        samples.append((timestamp, abs(target_x - float(value["x"]))))
        cross_track = max(cross_track, abs(float(value["y"])))
        peak_speed = max(
            peak_speed, math.hypot(float(value["vx"]), float(value["vy"]))
        )

    integrated = 0.0
    for (previous_ns, previous_error), (current_ns, current_error) in zip(
        samples, samples[1:]
    ):
        integrated += (
            (current_ns - previous_ns)
            / 1_000_000_000
            * (previous_error + current_error)
            / 2.0
        )

    completion_position = _nearest(active, completion_ns)
    completion_elapsed = max(0.0, (completion_ns - activation_ns) / 1_000_000_000)
    reference_elapsed = (
        min(completion_elapsed, stall_after_s)
        if scheduled_fault_ns is not None
        else completion_elapsed
    )
    completion_target = straight_line_target(
        reference_elapsed,
        settle_s=settle_s,
        speed_m_s=speed_m_s,
        distance_m=distance_m,
    )
    exposure = (
        [
            value
            for value in positions
            if scheduled_fault_ns is not None
            and scheduled_fault_ns <= int(value["timestamp_ns"]) <= completion_ns
        ]
        if scheduled_fault_ns is not None
        else []
    )
    return {
        "along_track_lag_m": _round(completion_target - float(completion_position["x"])),
        "cross_track_error_m": _round(cross_track),
        "integrated_absolute_along_track_error_m_s": _round(integrated),
        "exposure_duration_s": _round(
            max(0.0, (completion_ns - scheduled_fault_ns) / 1_000_000_000)
            if scheduled_fault_ns is not None
            else 0.0
        ),
        "exposure_distance_m": _round(_path_length(exposure, dimensions=2)) if len(exposure) >= 2 else 0.0,
        "peak_horizontal_speed_m_s": _round(peak_speed),
        "recovery_distance_m": _round(_path_length(recovery, dimensions=3)),
        "activation_ns": activation_ns,
        "scheduled_fault_ns": scheduled_fault_ns,
        "completion_ns": completion_ns,
        "successor_ns": successor_ns,
        "landed_ns": landed_ns,
        "completion_target_x_m": _round(completion_target),
        "completion_actual_x_m": _round(float(completion_position["x"])),
        "planned_profile_shortfall_m": _round(distance_m - float(completion_position["x"])),
        "active_position_sample_count": len(active),
        "exposure_position_sample_count": len(exposure),
        "recovery_position_sample_count": len(recovery),
    }


def _accepted_attempts(matrix: dict[str, Any], study_root: Path) -> list[tuple[str, dict[str, Any]]]:
    ledger = verify_study_ledger(study_root / "attempt-ledger.jsonl")
    cells = {str(cell["cell_id"]): cell for cell in matrix["cells"]}
    accepted = [
        (attempt_id, cells[str(value["cell_id"])])
        for attempt_id, value in ledger["attempts"].items()
        if value["outcome"] == "ACCEPTED"
    ]
    for cell_id, cell in cells.items():
        count = sum(candidate["cell_id"] == cell_id for _, candidate in accepted)
        if count != int(cell["accepted_target"]):
            raise StageA2PhysicalError(f"cell {cell_id} is not closed at its accepted target")
    return sorted(accepted)


def _attempt_record(
    *, attempt_id: str, cell: dict[str, Any], study_root: Path, run_root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    compact = study_root / "results" / attempt_id
    run = run_root / attempt_id
    closure = _read_object(compact / "closure.json")
    evaluation = _read_object(compact / "evaluation.json")
    processing = _read_object(compact / "processing-result.json")
    plan_path = run_root / "plans" / f"{attempt_id}.json"
    trace_path = run / "derived" / "closed.trace.jsonl"
    lifecycle_path = run / "raw" / "workload.lifecycle.jsonl"
    telemetry_path = run / "raw" / "telemetry.sidecar.jsonl"
    raw_manifest_path = compact / "raw-manifest.json"
    paths = (plan_path, trace_path, lifecycle_path, telemetry_path, raw_manifest_path)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise StageA2PhysicalError("missing retained Stage A2 input: " + ", ".join(missing))
    if closure.get("outcome") != "ACCEPTED":
        raise StageA2PhysicalError(f"attempt is not accepted: {attempt_id}")
    if evaluation.get("evidence_gate", {}).get("status") != "ADMISSIBLE":
        raise StageA2PhysicalError(f"attempt is not admissible: {attempt_id}")
    if processing.get("physical_execution", {}).get("status") != "PASS":
        raise StageA2PhysicalError(f"attempt lacks physical validity: {attempt_id}")
    if closure.get("plan_digest") != _digest(plan_path):
        raise StageA2PhysicalError(f"plan digest differs: {attempt_id}")

    raw_manifest = _read_object(raw_manifest_path)
    raw_files = {str(item["path"]): item for item in raw_manifest.get("files", [])}
    for relative, path in (
        ("workload.lifecycle.jsonl", lifecycle_path),
        ("telemetry.sidecar.jsonl", telemetry_path),
    ):
        item = raw_files.get(relative)
        if item is None or item.get("sha256") != _digest(path, prefix=False):
            raise StageA2PhysicalError(f"raw manifest differs for {attempt_id}/{relative}")

    plan = _read_object(plan_path)
    trace = _read_jsonl(trace_path)
    telemetry = _read_jsonl(telemetry_path)
    target_route = str(plan["transition"]["target_route"])
    successor_route = str(plan["transition"]["expected_successor"])
    requests = [
        event
        for event in trace
        if event.get("kind") == "transition_requested"
        and isinstance(event.get("timestamp_ns"), int)
    ]
    if not requests:
        raise StageA2PhysicalError(f"missing tested transition request: {attempt_id}")
    request_ns = min(int(event["timestamp_ns"]) for event in requests)
    activation = _event_after(trace, "activation", target_route, request_ns)
    completion = _event_after(trace, "completion", target_route, int(activation["timestamp_ns"]))
    successor = _event_after(trace, "activation", successor_route, int(completion["timestamp_ns"]))
    landed = [
        event
        for event in telemetry
        if event.get("kind") == "vehicle_land_detected"
        and event.get("landed") is True
        and isinstance(event.get("received_monotonic_ns"), int)
        and int(event["received_monotonic_ns"]) >= int(successor["timestamp_ns"])
    ]
    if not landed:
        raise StageA2PhysicalError(f"missing landed endpoint: {attempt_id}")
    landed_ns = min(int(event["received_monotonic_ns"]) for event in landed)
    runtime = cell["runtime"]
    metrics = compute_metrics(
        positions=_positions(telemetry),
        activation_ns=int(activation["timestamp_ns"]),
        completion_ns=int(completion["timestamp_ns"]),
        successor_ns=int(successor["timestamp_ns"]),
        landed_ns=landed_ns,
        settle_s=float(runtime["motion_settle_s"]),
        speed_m_s=float(runtime["motion_speed_m_s"]),
        distance_m=float(runtime["motion_distance_m"]),
        stall_after_s=float(runtime["stall_after_s"]),
        fault_mode=str(runtime["fault_mode"]),
    )
    ordinal = int(attempt_id.rsplit("-", 1)[1])
    record = {
        "schema_version": "1.0",
        "attempt_id": attempt_id,
        "cell_id": cell["cell_id"],
        "mechanism": runtime["mechanism"],
        "fault_mode": runtime["fault_mode"],
        "simulation_seed": int(runtime["simulation_seed_base"]) + ordinal,
        "ordinal": ordinal,
        "evidence_gate": "ADMISSIBLE",
        "oracle_status": evaluation["status"],
        "violation_clauses": sorted(
            str(finding["clause"])
            for finding in evaluation.get("findings", [])
            if finding.get("clause_status") == "VIOLATION"
        ),
        "physical_execution": "PASS",
        "metrics": metrics,
    }
    manifest = {
        "attempt_id": attempt_id,
        "inputs": {
            "plan": {"path": str(plan_path), "digest": _digest(plan_path)},
            "closed_trace": {"path": str(trace_path), "digest": _digest(trace_path)},
            "workload_lifecycle": {"path": str(lifecycle_path), "digest": _digest(lifecycle_path)},
            "telemetry": {"path": str(telemetry_path), "digest": _digest(telemetry_path)},
            "raw_manifest": {"path": str(raw_manifest_path), "digest": _digest(raw_manifest_path)},
            "evaluation": {"path": str(compact / "evaluation.json"), "digest": _digest(compact / "evaluation.json")},
        },
    }
    return record, manifest


def _distribution(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "minimum": _round(min(values)),
        "median": _round(statistics.median(values)),
        "maximum": _round(max(values)),
    }


def analyze(
    *, matrix_path: Path, study_root: Path, run_root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    matrix = read_matrix(matrix_path)
    validate_matrix(matrix)
    if matrix.get("study_id") != "motivation-stage-a2-thor-remediation-v1":
        raise StageA2PhysicalError("analysis accepts only the frozen remediation study")
    records: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    for attempt_id, cell in _accepted_attempts(matrix, study_root):
        record, manifest = _attempt_record(
            attempt_id=attempt_id, cell=cell, study_root=study_root, run_root=run_root
        )
        records.append(record)
        inputs.append(manifest)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(str(record["fault_mode"]), str(record["mechanism"]))].append(record)
    strata = {}
    for key, values in sorted(grouped.items()):
        strata["/".join(key)] = {
            "oracle_statuses": dict(sorted(Counter(value["oracle_status"] for value in values).items())),
            "metrics": {
                metric: _distribution([float(value["metrics"][metric]) for value in values])
                for metric in METRICS
            },
            "completion_actual_x_m": _distribution(
                [float(value["metrics"]["completion_actual_x_m"]) for value in values]
            ),
            "planned_profile_shortfall_m": _distribution(
                [float(value["metrics"]["planned_profile_shortfall_m"]) for value in values]
            ),
        }

    pairs = []
    for fault_mode in ("normal", "setpoint_stall"):
        by_key = {
            (str(record["fault_mode"]), int(record["simulation_seed"])): record
            for record in records
            if record["fault_mode"] == fault_mode
            and record["mechanism"] == "legacy_offboard"
        }
        dynamic = {
            (str(record["fault_mode"]), int(record["simulation_seed"])): record
            for record in records
            if record["fault_mode"] == fault_mode
            and record["mechanism"] == "dynamic_external_mode"
        }
        if set(by_key) != set(dynamic):
            raise StageA2PhysicalError(f"incomplete matched pairs for {fault_mode}")
        for key in sorted(by_key):
            offboard = by_key[key]
            other = dynamic[key]
            pairs.append(
                {
                    "schema_version": "1.0",
                    "fault_mode": fault_mode,
                    "simulation_seed": key[1],
                    "paired_unit": "shared simulation seed and workload profile",
                    "legacy_offboard_attempt": offboard["attempt_id"],
                    "dynamic_external_mode_attempt": other["attempt_id"],
                    "oracle_status_equal": offboard["oracle_status"] == other["oracle_status"],
                    "dynamic_minus_offboard": {
                        metric: _round(float(other["metrics"][metric]) - float(offboard["metrics"][metric]))
                        for metric in METRICS
                    },
                }
            )
    pair_summary = {}
    for fault_mode in ("normal", "setpoint_stall"):
        selected = [pair for pair in pairs if pair["fault_mode"] == fault_mode]
        pair_summary[fault_mode] = {
            "pair_count": len(selected),
            "oracle_status_equal_count": sum(bool(pair["oracle_status_equal"]) for pair in selected),
            "dynamic_minus_offboard": {
                metric: _distribution(
                    [float(pair["dynamic_minus_offboard"][metric]) for pair in selected]
                )
                for metric in METRICS
            },
        }

    summary = {
        "schema_version": "1.0",
        "analysis_id": "stage-a2-physical-consequence-v1",
        "study_id": matrix["study_id"],
        "attempt_count": len(records),
        "pair_count": len(pairs),
        "evidence_gate_counts": dict(sorted(Counter(record["evidence_gate"] for record in records).items())),
        "oracle_status_counts": dict(sorted(Counter(record["oracle_status"] for record in records).items())),
        "violation_clause_counts": dict(
            sorted(Counter(clause for record in records for clause in record["violation_clauses"]).items())
        ),
        "strata": strata,
        "matched_pairs": pair_summary,
        "operationalization": {
            "along_track_lag_m": "scheduled reference x minus observed x at route completion",
            "cross_track_error_m": "maximum absolute local-NED y while the tested route is active",
            "integrated_absolute_along_track_error_m_s": "trapezoidal integral over the active route",
            "exposure_duration_s": "scheduled stall to route completion; zero for nominal arms",
            "exposure_distance_m": "sampled horizontal path length from scheduled stall to completion",
            "peak_horizontal_speed_m_s": "maximum local horizontal speed while the tested route is active",
            "recovery_distance_m": "sampled three-dimensional path from Land activation to landed observation",
            "stall_reference": "position reference freezes at the registered stall offset",
        },
        "claim_boundary": "bounded Thor SITL consequence; descriptive paired differences, not a real-flight risk estimate",
    }
    input_manifest = {
        "schema_version": "1.0",
        "analysis_id": summary["analysis_id"],
        "matrix": {"path": str(matrix_path), "digest": _digest(matrix_path)},
        "ledger": {
            "path": str(study_root / "attempt-ledger.jsonl"),
            "digest": _digest(study_root / "attempt-ledger.jsonl"),
        },
        "attempts": inputs,
    }
    return records, pairs, summary, input_manifest


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise StageA2PhysicalError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--study-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        records, pairs, summary, input_manifest = analyze(
            matrix_path=args.matrix,
            study_root=args.study_root,
            run_root=args.run_root,
        )
        outputs = {
            "physical-results.jsonl": "".join(json.dumps(value, sort_keys=True) + "\n" for value in records),
            "matched-pairs.jsonl": "".join(json.dumps(value, sort_keys=True) + "\n" for value in pairs),
            "physical-summary.json": json.dumps(summary, indent=2, sort_keys=True) + "\n",
            "physical-input-manifest.json": json.dumps(input_manifest, indent=2, sort_keys=True) + "\n",
        }
        for name, content in outputs.items():
            _write_new(args.output_dir / name, content)
    except (OSError, ValueError, KeyError, StageA2PhysicalError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "PASS", "output_dir": str(args.output_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
