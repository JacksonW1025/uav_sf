#!/usr/bin/env python3
"""Derive a bounded P0-D execution result from durable probe and lifecycle events."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


LIFECYCLE_EVENT = re.compile(r'\{\"event_type\".*\}')


def summarize(events_path: Path, lifecycle_path: Path) -> dict[str, Any]:
    events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lifecycle: list[dict[str, Any]] = []
    for line in lifecycle_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = LIFECYCLE_EVENT.search(line)
        if match:
            lifecycle.append(json.loads(match.group(0)))

    transitions = [event for event in events if event.get("event_type") == "state_transition"]
    statuses = [event for event in events if event.get("event_type") == "vehicle_status_sample"]
    finished = next(
        (event for event in reversed(events) if event.get("event_type") == "runner_finished"),
        None,
    )
    armed_seen = False
    disarm_event: dict[str, Any] | None = None
    for event in statuses:
        if event.get("arming_state") == 2:
            armed_seen = True
        elif armed_seen and event.get("arming_state") == 1:
            disarm_event = event
            break
    post_disarm_statuses = [
        event
        for event in statuses
        if disarm_event is not None
        and event["monotonic_ns"] >= disarm_event["monotonic_ns"]
    ]
    external_mode_ids = [
        int(event["mode_id"])
        for event in events
        if event.get("event_type") == "external_mode_registration_observed"
    ]
    external_mode_id = external_mode_ids[-1] if external_mode_ids else None
    shutdown = next(
        (event for event in events if event.get("event_type") == "graceful_shutdown_requested"),
        None,
    )
    after_shutdown = [
        event
        for event in statuses
        if shutdown is not None and event["monotonic_ns"] > shutdown["monotonic_ns"]
    ]
    rearmed = [event for event in after_shutdown if event.get("arming_state") == 2]
    unregister = [
        event for event in events if event.get("event_type") == "graceful_unregister_request"
    ]

    execution_status = "PASS" if finished and finished.get("status") == "PASS" else "FAIL"
    termination_state = str(events[-1].get("state", "unknown")) if events else "unknown"
    reason = (
        str(finished.get("reason"))
        if finished is not None
        else f"probe ended without runner_finished while in {termination_state}"
    )
    return {
        "schema_version": "1.0",
        "scenario": "p0d_post_disarm_reentry",
        "status": execution_status,
        "reason": reason,
        "termination_state": termination_state,
        "external_mode_id": external_mode_id,
        "disarm_nav_state": int(disarm_event["nav_state"]) if disarm_event else None,
        "post_disarm_nav_states": sorted(
            {
                int(event["nav_state"])
                for event in post_disarm_statuses
                if event.get("arming_state") == 1
            }
        ),
        "on_activate_count": sum(
            event.get("event_type") == "external_mode_activated" for event in lifecycle
        ),
        "on_deactivate_count": sum(
            event.get("event_type") == "external_mode_deactivated" for event in lifecycle
        ),
        "external_setpoint_log_count": sum(
            event.get("event_type") == "external_mode_setpoint" for event in lifecycle
        ),
        "unregister_request_count": len(unregister),
        "mode_slot_removal_evidence": False,
        "rearm_observed": bool(rearmed),
        "rearm_initial_nav_state": int(rearmed[0]["nav_state"]) if rearmed else None,
        "automatic_external_after_rearm": bool(
            rearmed
            and external_mode_id is not None
            and int(rearmed[0]["nav_state"]) == external_mode_id
        ),
        "state_transitions": [str(event.get("current")) for event in transitions],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--lifecycle-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.events, args.lifecycle_log)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
