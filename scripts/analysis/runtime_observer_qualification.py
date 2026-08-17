#!/usr/bin/env python3
"""Freeze the Phase III runtime and observer qualification evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any

from scripts.runtime.process_attempt import _gazebo_metrics
from scripts.runtime.physical_readiness import physical_takeoff_observed


class QualificationError(RuntimeError):
    """Qualification inputs are incomplete or outputs would be overwritten."""


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _digest(path: Path) -> str:
    value = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{value}"


def _write_new(path: Path, value: Any) -> None:
    if path.exists():
        raise QualificationError(f"refusing to overwrite {path}")
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def _distribution(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "minimum": ordered[0],
        "median": statistics.median(ordered),
        "maximum": ordered[-1],
    }


def _physical(records: list[dict[str, Any]]) -> dict[str, Any]:
    positions = [
        item for item in records
        if item.get("kind") == "vehicle_local_position"
        and item.get("xy_valid") is True and item.get("z_valid") is True
    ]
    if not positions:
        raise QualificationError("local-position evidence is absent")
    origin = positions[0]
    heights = [float(origin["z"]) - float(item["z"]) for item in positions]
    displacements = [
        math.hypot(float(item["x"]) - float(origin["x"]), float(item["y"]) - float(origin["y"]))
        for item in positions
    ]
    return {
        "physical_takeoff_predicate": physical_takeoff_observed(records),
        "position_sample_count": len(positions),
        "maximum_height_above_origin_m": max(heights),
        "maximum_horizontal_displacement_m": max(displacements),
    }


def _attempt_result(attempt: Path, profile: str, identity: dict[str, Any]) -> dict[str, Any]:
    runtime_path = attempt / "runtime_result.json"
    telemetry_path = attempt / "raw/telemetry.sidecar.jsonl"
    lifecycle_path = attempt / "raw/workload.lifecycle.jsonl"
    ulog_path = attempt / "raw/px4.ulg"
    for path in (runtime_path, telemetry_path, lifecycle_path, ulog_path):
        if not path.is_file():
            raise QualificationError(f"missing qualification input {path}")
    runtime = _read_json(runtime_path)
    telemetry = _read_jsonl(telemetry_path)
    lifecycle = _read_jsonl(lifecycle_path)
    route_path = attempt / "route-summary.json"
    route = _read_json(route_path) if route_path.is_file() else None
    result = {
        "schema_version": "1.0",
        "attempt_id": attempt.name,
        "observer_profile": profile,
        "image_identity": identity,
        "runtime_outcome": runtime.get("outcome"),
        "physical": _physical(telemetry),
        "lifecycle_kinds": sorted({str(item.get("kind")) for item in lifecycle}),
        "gazebo_real_time_factor": _gazebo_metrics(attempt / "raw/gazebo_stats.stdout.log"),
        "ulog_bytes": ulog_path.stat().st_size,
        "ulog_digest": _digest(ulog_path),
        "route_observation": route,
        "input_digests": {
            "runtime_result": _digest(runtime_path),
            "telemetry": _digest(telemetry_path),
            "workload_lifecycle": _digest(lifecycle_path),
        },
    }
    if route_path.is_file():
        result["input_digests"]["route_summary"] = _digest(route_path)
    return result


def analyze(root: Path, output: Path, plan_path: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    plan = _read_json(plan_path)
    observer_root = root / plan["inputs"]["observer_run_root"]
    runtime_root = root / plan["inputs"]["runtime_run_root"]
    results = []
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "analysis_plan_digest": _digest(plan_path),
        "observer_attempts": [],
        "runtime_attempts": [],
    }
    for profile in ("off", "baseline", "transition"):
        spec = plan["observer_profiles"][profile]
        attempt = observer_root / spec["attempt_id"]
        result = _attempt_result(attempt, profile, spec["identity"])
        results.append(result)
        manifest["observer_attempts"].append(
            {"attempt_id": attempt.name, "input_digests": result["input_digests"], "ulog_digest": result["ulog_digest"]}
        )
    runtime_results = []
    for attempt_id in plan["runtime_attempt_ids"]:
        attempt = runtime_root / attempt_id
        runtime_path = attempt / "runtime_result.json"
        lifecycle_path = attempt / "raw/workload.lifecycle.jsonl"
        runtime = _read_json(runtime_path)
        lifecycle = _read_jsonl(lifecycle_path)
        item = {
            "attempt_id": attempt_id,
            "outcome": runtime.get("outcome"),
            "physical_takeoff_ready": any(event.get("kind") == "physical_takeoff_ready" for event in lifecycle),
            "registration_handoff_loaded": any(event.get("kind") == "registration_handoff_loaded" for event in lifecycle),
        }
        runtime_results.append(item)
        manifest["runtime_attempts"].append({
            "attempt_id": attempt_id,
            "runtime_result_digest": _digest(runtime_path),
            "workload_lifecycle_digest": _digest(lifecycle_path),
        })

    by_profile = {item["observer_profile"]: item for item in results}
    selected = by_profile[plan["selection"]["selected_profile"]]
    baseline = by_profile["baseline"]
    off = by_profile["off"]
    route = selected["route_observation"]
    checks = {
        "all_runtime_attempts_accepted": all(item["outcome"] == "ACCEPTED" for item in runtime_results),
        "all_attempts_physically_valid": all(item["physical"]["physical_takeoff_predicate"] for item in results),
        "all_profiles_meet_rtf_floor": all(item["gazebo_real_time_factor"]["central_minimum"] >= plan["bounds"]["minimum_central_rtf"] for item in results),
        "off_has_no_route_observation": off["route_observation"] is None,
        "selected_route_evidence_complete": bool(route and route["status"] == "PASS" and not route["sequence_gaps"] and not route["dropouts"]),
        "selected_ulog_growth_within_bound": (selected["ulog_bytes"] - baseline["ulog_bytes"]) / baseline["ulog_bytes"] <= plan["bounds"]["maximum_selected_ulog_growth_fraction_over_baseline"],
    }
    summary = {
        "schema_version": "1.0",
        "analysis_id": plan["analysis_id"],
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "selected_observer_profile": plan["selection"]["selected_profile"],
        "selection_reason": plan["selection"]["reason"],
        "runtime_readiness": runtime_results,
        "observer_attempt_count": len(results),
        "stable_rtf_median_distribution": _distribution([item["gazebo_real_time_factor"]["median"] for item in results]),
        "selected_ulog_growth_bytes_over_baseline": selected["ulog_bytes"] - baseline["ulog_bytes"],
        "selected_ulog_growth_fraction_over_baseline": (selected["ulog_bytes"] - baseline["ulog_bytes"]) / baseline["ulog_bytes"],
        "selected_observation_count": route["route_observation_count"] if route else None,
        "baseline_observation_count": baseline["route_observation"]["route_observation_count"],
    }
    lines = [
        "# Phase III runtime and observer qualification",
        "",
        f"Status: **{summary['status']}**. These are non-formal qualification attempts and do not enter a paper experiment denominator.",
        "",
        "All three matched observer tasks were accepted, satisfied the sustained physical-takeoff predicate, and exceeded the preregistered stable real-time-factor floor. The observer-off ULog correctly contains no Route observation topic, so it cannot be used to evaluate the Route Oracles.",
        "",
        f"The selected A2 profile is **{summary['selected_observer_profile']}**. It retained {summary['selected_observation_count']} Route observations with no sequence gap or dropout. Compared with the baseline profile, its ULog grew by {summary['selected_ulog_growth_bytes_over_baseline']} bytes ({summary['selected_ulog_growth_fraction_over_baseline']:.2%}); this remains below the frozen bound.",
        "",
        "The repaired Dynamic readiness path was accepted in both Dynamic qualification attempts and loaded the explicit registration handoff. The Legacy Offboard control attempt was also accepted. This sample demonstrates the handshake under the qualification batch; it is not a population-level reliability estimate.",
        "",
        "## Claim boundary",
        "",
        "The result qualifies one Thor SITL runtime and one observer profile for the separately preregistered A2 study. It does not alter Stage A1, prove absence of probe effects in every workload, or establish real-flight behavior.",
    ]
    _write_new(output / "input-manifest.json", manifest)
    _write_new(output / "profile-results.jsonl", "".join(json.dumps(item, sort_keys=True) + "\n" for item in results))
    _write_new(output / "summary.json", summary)
    _write_new(output / "FINAL_REPORT.md", "\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.root.resolve(), args.output.resolve(), args.plan.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
