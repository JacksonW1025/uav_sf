#!/usr/bin/env python3
"""Validate and deterministically replay a W1 trace without ROS publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


REQUIRED_PHASES = (
    "internal_ground",
    "arm",
    "internal_takeoff",
    "Aerostack2_Offboard",
    "go_to",
    "follow_path",
    "cancel_to_hover",
    "explicit_aircraft_Land",
    "disarm",
)

KEEP_EVENTS = {
    "mission_started",
    "mission_phase",
    "service_request",
    "service_result",
    "action_goal_request",
    "action_goal_accepted",
    "action_feedback",
    "action_result",
    "action_cancel_request",
    "action_cancel_ack",
    "nav_state_transition",
    "motion_reference",
    "platform_info",
    "controller_info",
    "setpoint_sample",
    "clock_bridge_sample",
    "vehicle_command",
    "mission_finished",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: record must be an object")
            value.setdefault("sequence", line_number)
            records.append(value)
    return records


def _finite_values(value: Any, prefix: str = "") -> Iterable[tuple[str, float]]:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        yield prefix, float(value)
        return
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _finite_values(child, f"{prefix}.{key}" if prefix else str(key))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _finite_values(child, f"{prefix}[{index}]")


def canonicalize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [record for record in records if record.get("event_type") in KEEP_EVENTS]
    selected.sort(key=lambda item: (int(item.get("monotonic_ns", 0)), int(item["sequence"])))
    output: list[dict[str, Any]] = []
    for record in selected:
        output.append(
            {
                key: record[key]
                for key in sorted(record)
                if key not in {"source_file", "sequence"}
            }
        )
    return output


def validate(records: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    phases = [
        str(record.get("phase"))
        for record in records
        if record.get("event_type") == "mission_phase"
    ]
    phase_cursor = 0
    for phase in phases:
        if phase_cursor < len(REQUIRED_PHASES) and phase == REQUIRED_PHASES[phase_cursor]:
            phase_cursor += 1
    if phase_cursor != len(REQUIRED_PHASES):
        errors.append(f"mission phase sequence incomplete at {REQUIRED_PHASES[phase_cursor]}")

    goal_ids: set[str] = set()
    cancel_ids: set[str] = set()
    cancel_acks: set[str] = set()
    results: set[str] = set()
    feedback_count = 0
    for record in records:
        event_type = record.get("event_type")
        goal_id = str(record.get("goal_id", ""))
        if event_type == "action_goal_accepted" and goal_id:
            goal_ids.add(goal_id)
        elif event_type == "action_feedback":
            feedback_count += 1
        elif event_type == "action_cancel_request" and goal_id:
            cancel_ids.add(goal_id)
        elif event_type == "action_cancel_ack" and goal_id:
            cancel_acks.add(goal_id)
        elif event_type == "action_result" and goal_id:
            results.add(goal_id)
        if event_type in {"motion_reference", "setpoint_sample", "vehicle_command"}:
            for name, number in _finite_values(record.get("values", record.get("params", {}))):
                if not math.isfinite(number):
                    errors.append(f"non-finite command value at {event_type}.{name}")

    if len(goal_ids) < 2:
        errors.append("go-to and follow-path accepted goal IDs are required")
    if not cancel_ids or not cancel_ids.issubset(cancel_acks):
        errors.append("cancel request and acknowledgement correlation is incomplete")
    if not goal_ids.issubset(results):
        errors.append("accepted action result correlation is incomplete")
    if feedback_count == 0:
        errors.append("action feedback is absent")

    nav_states = [
        record.get("current")
        for record in records
        if record.get("event_type") == "nav_state_transition"
    ]
    classifications = [
        {
            "edge": "internal_to_Offboard",
            "classification": "EXPECTED_ROUTE_REPLACEMENT",
        },
        {
            "edge": "go_to_to_follow_path",
            "classification": "EXPECTED_TASK_TRANSITION",
        },
        {
            "edge": "cancel_to_hover",
            "classification": "EXPECTED_TASK_TRANSITION",
        },
        {
            "edge": "Offboard_to_aircraft_Land",
            "classification": "EXPECTED_ROUTE_REPLACEMENT",
        },
    ]
    return {
        "valid": not errors,
        "errors": errors,
        "phase_sequence": phases,
        "accepted_goal_ids": sorted(goal_ids),
        "cancel_goal_ids": sorted(cancel_ids),
        "result_goal_ids": sorted(results),
        "feedback_count": feedback_count,
        "nav_state_sequence": nav_states,
        "route_classifications": classifications,
    }


def replay(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    canonical = canonicalize(read_jsonl(path))
    validation = validate(canonical)
    return canonical, validation


def digest(records: list[dict[str, Any]]) -> str:
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events-output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    first, validation = replay(args.input)
    second, second_validation = replay(args.input)
    first_digest = digest(first)
    second_digest = digest(second)
    deterministic = first == second and validation == second_validation
    result = {
        "schema_version": "1.0",
        "run_id": args.run_id,
        "adapter": "W1_TRACE_ONLY",
        "status": "ACCEPTED" if deterministic and validation["valid"] else "REJECTED",
        "input": args.input.name,
        "input_records": len(read_jsonl(args.input)),
        "canonical_records": len(first),
        "first_sha256": first_digest,
        "second_sha256": second_digest,
        "deterministic": deterministic,
        "command_publication_enabled": False,
        "command_publication_count": 0,
        "flight_started": False,
        "validation": validation,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.events_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with args.events_output.open("w", encoding="utf-8") as handle:
        for record in first:
            handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    return 0 if result["status"] == "ACCEPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
