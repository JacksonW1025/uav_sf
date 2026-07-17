#!/usr/bin/env python3
"""Classify P0-D2 using runner, registry-removal, epoch, and re-entry evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def summarize(runner_result: Path, trace: Path) -> dict[str, Any]:
    runner = json.loads(runner_result.read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in trace.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    processed = [event for event in events if event.get("event_type") == "unregister_request_processed"]
    mode_removed = [event for event in events if event.get("event_type") == "external_mode_slot_removed"]
    arming_removed = [event for event in events if event.get("event_type") == "arming_check_slot_removed"]

    def success(records: list[dict[str, Any]]) -> bool:
        return bool(records) and any(
            isinstance(record.get("registration_state"), dict)
            and record["registration_state"].get("processing_result") == "SUCCESS"
            for record in records
        )

    old_epochs = {
        int(event["route_epoch_id"])
        for event in events
        if event.get("declared_mode") in range(23, 31)
        and event.get("route_epoch_id") is not None
    }
    removal_times = [
        float(event["timestamp"])
        for event in processed
        if event.get("timestamp_domain") == "ulog_us"
    ]
    last_removal = max(removal_times, default=None)
    post_removal_old_epoch_events = [
        event
        for event in events
        if last_removal is not None
        and event.get("timestamp_domain") == "ulog_us"
        and float(event["timestamp"]) > last_removal
        and event.get("route_epoch_id") in old_epochs
        and event.get("event_type")
        in {"px4_setpoint_consumed", "allocator_input_published", "actuator_output_published"}
    ]
    checks = {
        "flight_and_internal_reentry_completed": runner.get("status") == "PASS",
        "unregister_request_observed": int(runner.get("unregister_request_count", 0)) >= 1,
        "unregister_processed_success": success(processed),
        "mode_slot_removed_success": success(mode_removed),
        "arming_check_slot_removed_success": success(arming_removed),
        "internal_rearm_observed": runner.get("rearm_initial_nav_state") in {2, 4},
        "no_automatic_external_reentry": runner.get("automatic_external_after_rearm") is False,
        "no_old_epoch_data_plane_residue": not post_removal_old_epoch_events,
    }
    if all(checks.values()):
        conclusion = "clean_reentry"
        status = "PASS"
    elif post_removal_old_epoch_events:
        conclusion = "data_plane_residue"
        status = "FAIL"
    elif not success(processed) or not success(mode_removed) or not success(arming_removed):
        conclusion = "control_plane_residue"
        status = "FAIL"
    elif "rearm" in str(runner.get("reason", "")).lower():
        conclusion = "environmental_rearm_failure"
        status = "FAIL"
    else:
        conclusion = "insufficient_evidence"
        status = "FAIL"
    return {
        **runner,
        "scenario": "p0d2_full_external_reentry",
        "status": status,
        "reason": conclusion,
        "conclusion": conclusion,
        "checks": checks,
        "mode_slot_removal_evidence": success(mode_removed),
        "unregister_processed_count": len(processed),
        "mode_slot_removed_count": len(mode_removed),
        "arming_check_slot_removed_count": len(arming_removed),
        "old_external_epoch_ids": sorted(old_epochs),
        "post_removal_old_epoch_event_count": len(post_removal_old_epoch_events),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-result", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.runner_result, args.trace)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "conclusion": result["conclusion"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
