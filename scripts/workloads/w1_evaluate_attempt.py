#!/usr/bin/env python3
"""Evaluate W1 runtime evidence against the preregistered acceptance contract."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


REQUIRED_PHASES = [
    "internal_ground",
    "arm",
    "internal_takeoff",
    "Aerostack2_Offboard",
    "go_to",
    "follow_path",
    "cancel_to_hover",
    "explicit_aircraft_Land",
    "disarm",
]


def jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--phase", choices=("W1-B", "W1-D"), required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cleanup", type=Path, required=True)
    args = parser.parse_args()

    reasons: list[str] = []
    mission_result_path = args.raw / "mission_result.json"
    mission = json.loads(mission_result_path.read_text()) if mission_result_path.is_file() else {}
    mission_events = jsonl(args.raw / "mission_events.jsonl")
    sidecar = jsonl(args.raw / "sidecar_events.jsonl")
    route = jsonl(args.processed / "route_trace.jsonl")
    clock_path = args.processed / "clock_bridge.json"
    clock = json.loads(clock_path.read_text()) if clock_path.is_file() else {}
    cleanup = json.loads(args.cleanup.read_text()) if args.cleanup.is_file() else {}
    artifacts_path = args.processed / "raw_artifact_manifest.json"
    artifacts = json.loads(artifacts_path.read_text()) if artifacts_path.is_file() else {}

    phases = [record.get("phase") for record in mission_events if record.get("event_type") == "mission_phase"]
    if phases != REQUIRED_PHASES:
        reasons.append("preregistered mission phase sequence is incomplete or out of order")
    if mission.get("status") != "PASS":
        reasons.append(f"mission driver status is {mission.get('status', 'MISSING')}")
    if not mission.get("terminal_landed") or not mission.get("terminal_disarmed"):
        reasons.append("terminal Land and Disarm evidence is incomplete")
    if mission.get("formal_safety_stop"):
        reasons.append("mission driver declared a formal safety stop")

    event_types = Counter(record.get("event_type") for record in mission_events)
    for required in (
        "service_request",
        "service_result",
        "action_goal_request",
        "action_goal_accepted",
        "action_feedback",
        "action_result",
        "action_cancel_request",
        "action_cancel_ack",
    ):
        if event_types[required] == 0:
            reasons.append(f"missing lifecycle evidence: {required}")

    if clock.get("status") != "VALID":
        reasons.append(f"clock bridge status is {clock.get('status', 'MISSING')}")
    if not (args.raw / "flight.ulg").is_file():
        reasons.append("ULog is missing")
    if not (args.raw / "rosbag" / "metadata.yaml").is_file():
        reasons.append("rosbag metadata is missing")
    if not artifacts.get("artifact_set_sha256"):
        reasons.append("raw artifact hashes are incomplete")

    sidecar_types = Counter(record.get("event_type") for record in sidecar)
    for required in ("motion_reference", "setpoint_sample", "platform_info", "controller_info"):
        if sidecar_types[required] == 0:
            reasons.append(f"sidecar evidence is missing: {required}")
    for record in sidecar:
        if record.get("event_type") not in {"motion_reference", "setpoint_sample"}:
            continue
        for values in record.get("values", {}).values():
            sequence = values if isinstance(values, list) else [values]
            for value in sequence:
                if isinstance(value, list):
                    sequence.extend(value)
                elif value is not None and isinstance(value, (int, float)) and not math.isfinite(float(value)):
                    reasons.append("non-finite sidecar command value")

    route_types = Counter(record.get("event_type") for record in route)
    for required in (
        "route_epoch_changed",
        "px4_setpoint_consumed",
        "allocator_input_published",
        "actuator_output_published",
    ):
        if route_types[required] == 0:
            reasons.append(f"route lineage evidence is missing: {required}")
    writers = {record.get("actuator_writer") for record in route if record.get("actuator_writer")}
    allocator_inputs = {
        json.dumps(record.get("allocator_input"), sort_keys=True)
        for record in route
        if record.get("allocator_input")
    }
    if writers != {"control_allocator"}:
        reasons.append(f"final writer lineage is incomplete or inconsistent: {sorted(writers)}")
    if not allocator_inputs:
        reasons.append("allocator input lineage is absent")
    if not cleanup.get("clean"):
        reasons.append("post-attempt local process or port cleanup is incomplete")

    if mission.get("formal_safety_stop"):
        classification = "FORMAL_SAFETY_STOP"
    elif mission and mission.get("status") != "PASS":
        classification = "CAMPAIGN_CONFIGURATION_FAILURE"
    elif not clock or not route or sidecar_types["motion_reference"] == 0:
        classification = "OBSERVABILITY_REJECTED"
    elif not cleanup.get("clean"):
        classification = "ENVIRONMENT_FAILURE"
    elif reasons:
        classification = "MEASUREMENT_INSUFFICIENT"
    else:
        classification = "ACCEPTED"

    result = {
        "schema_version": "1.0",
        "run_id": args.run_id,
        "phase": args.phase,
        "classification": classification,
        "accepted": classification == "ACCEPTED",
        "reasons": sorted(set(reasons)),
        "mission_status": mission.get("status"),
        "mission_phases": phases,
        "clock_bridge_status": clock.get("status"),
        "route_event_counts": dict(sorted(route_types.items())),
        "sidecar_event_counts": dict(sorted(sidecar_types.items())),
        "final_writers": sorted(writers),
        "allocator_inputs": sorted(allocator_inputs),
        "terminal_landed": mission.get("terminal_landed", False),
        "terminal_disarmed": mission.get("terminal_disarmed", False),
        "cleanup_clean": cleanup.get("clean", False),
        "artifact_set_sha256": artifacts.get("artifact_set_sha256"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": args.run_id, "classification": classification, "reasons": result["reasons"]}))
    return 0 if classification == "ACCEPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
