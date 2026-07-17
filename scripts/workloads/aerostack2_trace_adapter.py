#!/usr/bin/env python3
"""Merge observed Aerostack2 runtime events with a PX4 route trace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tracing.route_trace_collector import RouteState, RouteTraceWriter


AS2_BEHAVIOR_EVENTS = {
    "as2_action_goal",
    "as2_action_activated",
    "as2_action_modified",
    "as2_action_cancelled",
    "as2_action_completed",
}


def _as2_event(record: dict[str, Any], run_id: str) -> dict[str, Any]:
    if "timestamp_ns" not in record or "event_type" not in record:
        raise ValueError("Aerostack2 events require timestamp_ns and event_type")
    event_type = str(record["event_type"])
    state = RouteState(run_id=run_id)
    state.producer_identity = str(record.get("node", "aerostack2"))
    session = record.get("producer_session_id")
    state.producer_session_id = str(session) if session is not None else None
    phase = record.get("behavior_phase") or record.get("action")
    state.behavior_phase = str(phase) if phase is not None else None
    state.route_change_source = "aerostack2_runtime"
    state.setpoint_topic = (
        str(record.get("topic", "motion_reference/trajectory"))
        if event_type == "as2_motion_reference"
        else None
    )
    state.setpoint_level = str(record.get("setpoint_level", "unknown"))
    if event_type == "as2_offboard_request":
        state.declared_mode = 14
        state.authority_source = "ros2_offboard_request"
    elif event_type == "as2_emergency_land_request":
        state.declared_mode = 18
        state.fallback_target = 18
        state.authority_source = "px4_internal_request"
    canonical_type = (
        "producer_still_publishing"
        if event_type == "as2_motion_reference"
        else "aerostack2_behavior_event"
        if event_type in AS2_BEHAVIOR_EVENTS
        else event_type
    )
    return state.event(
        float(record["timestamp_ns"]),
        "ros_node_ns",
        canonical_type,
        str(record.get("evidence_source", "aerostack2_runtime_monitor")),
        "HIGH",
    )


def classify(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    events = list(events)
    modes: list[Any] = []
    for event in events:
        if event.get("event_type") != "vehicle_status":
            continue
        mode = event.get("declared_mode")
        if not modes or modes[-1] != mode:
            modes.append(mode)
    transitions = list(zip(modes, modes[1:]))
    true_handoffs = [
        [source, target]
        for source, target in transitions
        if (source == 14 or target == 14 or 23 <= int(source or -1) <= 30 or 23 <= int(target or -1) <= 30)
    ]
    behavior_events = sum(
        event.get("event_type") == "aerostack2_behavior_event" for event in events
    )
    classification = (
        "TRUE_ROUTE_HANDOFF"
        if true_handoffs
        else "NON_HANDOFF_TASK_TRANSITION"
        if behavior_events
        else "NO_CLASSIFIABLE_TRANSITION"
    )
    return {
        "classification": classification,
        "px4_mode_sequence": modes,
        "true_handoffs": true_handoffs,
        "behavior_event_count": behavior_events,
    }


def adapt(
    as2_events_path: Path,
    px4_trace_path: Path,
    output: Path,
    summary_path: Path,
    run_id: str,
) -> dict[str, Any]:
    px4_events = [
        json.loads(line)
        for line in px4_trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for event in px4_events:
        event["run_id"] = run_id
    as2_events = [
        _as2_event(json.loads(line), run_id)
        for line in as2_events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    merged = [*px4_events, *as2_events]
    event_count = RouteTraceWriter(output).write(merged)
    summary = {
        "schema_version": "1.0",
        "route_trace_schema_version": "1.2",
        "run_id": run_id,
        "event_count": event_count,
        "px4_event_count": len(px4_events),
        "aerostack2_event_count": len(as2_events),
        **classify(merged),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as2-events", type=Path, required=True)
    parser.add_argument("--px4-trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    result = adapt(args.as2_events, args.px4_trace, args.output, args.summary, args.run_id)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
