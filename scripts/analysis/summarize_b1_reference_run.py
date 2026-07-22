#!/usr/bin/env python3
"""Adjudicate one bounded B1 reference run from complete compact evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


STRUCTURED_EVENT = re.compile(r"\{\"event_type\".*\}")


def reference_lifecycle_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = STRUCTURED_EVENT.search(line)
        if match:
            records.append(json.loads(match.group(0)))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--monitor", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--clock-bridge", type=Path, required=True)
    parser.add_argument("--installation-oracle", type=Path, required=True)
    parser.add_argument("--restoration-oracle", type=Path, required=True)
    parser.add_argument("--reference-log", type=Path, required=True)
    parser.add_argument("--interruption-record", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    monitor = _load(args.monitor)
    bridge = _load(args.clock_bridge)
    installation = _load(args.installation_oracle)
    restoration = _load(args.restoration_oracle)
    events = [
        json.loads(line)
        for line in args.trace.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lifecycle = reference_lifecycle_records(args.reference_log)
    reference_mode = monitor.get("external_mode_id")
    classic_mode = monitor.get("classic_mode_id")
    reference_events = [event for event in events if event.get("declared_mode") == reference_mode]
    restored_events = [event for event in events if event.get("declared_mode") == classic_mode]
    reference_consumptions = [
        event
        for event in reference_events
        if event.get("event_type") == "px4_setpoint_consumed"
        and event.get("setpoint_topic") == "vehicle_attitude_setpoint"
    ]
    reference_allocator = [
        event for event in reference_events if event.get("event_type") == "allocator_input_published"
    ]
    reference_writers = [
        event for event in reference_events if event.get("event_type") == "actuator_output_published"
    ]
    controller_outputs = [
        event for event in lifecycle if event.get("event_type") == "b1_reference_output"
    ]
    reference_graph = [
        event
        for event in reference_events
        if "mc_att_control" in event.get("enabled_modules", [])
        and "mc_rate_control" in event.get("enabled_modules", [])
        and "control_allocator" in event.get("enabled_modules", [])
        and "mc_pos_control" in event.get("bypassed_modules", [])
    ]
    restored_graph = [
        event
        for event in restored_events
        if {
            "mc_pos_control",
            "mc_att_control",
            "mc_rate_control",
            "control_allocator",
        } <= set(event.get("enabled_modules", []))
    ]
    restored_trajectory = [
        event
        for event in restored_events
        if event.get("event_type") == "px4_setpoint_consumed"
        and event.get("setpoint_topic") == "trajectory_setpoint"
    ]
    interruption = _load(args.interruption_record) if args.interruption_record else None

    checks = {
        "monitor_pass": monitor.get("status") == "PASS",
        "no_safety_stop": monitor.get("safety_stop_reason") is None,
        "clock_bridge_valid": bridge.get("status") == "VALID",
        "registration_identity_available": isinstance(reference_mode, int),
        "process_controller_output_observed": bool(controller_outputs),
        "reference_attitude_consumption_observed": bool(reference_consumptions),
        "position_controller_bypassed": bool(reference_graph),
        "attitude_rate_allocator_retained": bool(reference_graph),
        "allocator_input_observed": bool(reference_allocator),
        "single_final_writer_identity": {event.get("actuator_writer") for event in reference_writers} == {"control_allocator"},
        "installation_oracle_pass": installation.get("status") == "PASS",
        "restoration_oracle_pass": restoration.get("status") == "PASS",
        "classic_graph_restored": bool(restored_graph),
        "classic_trajectory_consumption_restored": bool(restored_trajectory),
        "terminal_land_disarm": bool(monitor.get("landed")) and not bool(monitor.get("armed_at_finish")),
        "controlled_stop_marker_complete": (
            interruption is not None and interruption.get("action") == "SIGKILL"
            if monitor.get("release_kind") == "CONTROLLED_STOP"
            else interruption is None
        ),
    }
    missing = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "1.0",
        "run_id": args.run_id,
        "release_kind": monitor.get("release_kind"),
        "status": "ACCEPTED" if not missing else "MEASUREMENT_INSUFFICIENT",
        "checks": checks,
        "missing_or_failed_checks": missing,
        "reference_mode_id": reference_mode,
        "classic_mode_id": classic_mode,
        "counts": {
            "controller_output_events": len(controller_outputs),
            "reference_consumption_events": len(reference_consumptions),
            "reference_allocator_events": len(reference_allocator),
            "reference_writer_events": len(reference_writers),
            "restored_graph_events": len(restored_graph),
            "restored_trajectory_consumptions": len(restored_trajectory),
        },
        "maxima": monitor.get("maxima"),
        "installation_oracle_status": installation.get("status"),
        "restoration_oracle_status": restoration.get("status"),
        "limitations": [
            "process-side controller identity is joined to PX4 attitude consumption through the valid clock bridge and exclusive test configuration",
            "the final actuator writer remains control_allocator across route epochs; route epoch and upstream consumption establish lineage",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "missing": missing}, sort_keys=True))
    return 0 if result["status"] == "ACCEPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
