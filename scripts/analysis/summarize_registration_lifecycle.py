#!/usr/bin/env python3
"""Evaluate the disarmed P0-D1 registration/removal/re-registration contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


STRUCTURED = re.compile(r"\{\"event_type\".*\}")


def _lifecycle(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = STRUCTURED.search(line)
        if match:
            records.append(json.loads(match.group(0)))
    return records


def summarize(
    trace: Path,
    lifecycle_logs: list[Path],
    normal_graceful_exit: bool,
    immediate_exit: bool,
) -> dict[str, Any]:
    events = [
        json.loads(line)
        for line in trace.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lifecycle = [record for path in lifecycle_logs for record in _lifecycle(path)]
    processes = {
        "normal_graceful_exit": normal_graceful_exit,
        "normal_signal": "SIGINT",
        "immediate_exit": immediate_exit,
        "immediate_signal": "SIGTERM",
    }
    registrations = [
        event
        for event in events
        if event.get("event_type") == "register_ext_component_reply"
        and isinstance(event.get("registration_state"), dict)
        and event["registration_state"].get("registered") is True
    ]
    processed = [
        event for event in events if event.get("event_type") == "unregister_request_processed"
    ]
    mode_removed = [
        event for event in events if event.get("event_type") == "external_mode_slot_removed"
    ]
    arming_removed = [
        event for event in events if event.get("event_type") == "arming_check_slot_removed"
    ]
    executor_removed = [
        event for event in events if event.get("event_type") == "executor_slot_removed"
    ]
    registration_instances = [
        int(record["registration_instance_id"])
        for record in lifecycle
        if record.get("event_type") == "external_mode_registered"
        and record.get("registration_instance_id") is not None
    ]

    def successful(records: list[dict[str, Any]]) -> bool:
        return len(records) >= 2 and all(
            isinstance(record.get("registration_state"), dict)
            and record["registration_state"].get("processing_result") == "SUCCESS"
            for record in records
        )

    executor_ids = [
        int(event["registration_state"].get("mode_executor_id", -1))
        for event in processed
        if isinstance(event.get("registration_state"), dict)
    ]
    checks = {
        "two_registration_successes": len(registrations) >= 2,
        "fresh_registration_instances": len(set(registration_instances)) >= 2,
        "two_unregister_requests_processed": successful(processed),
        "mode_slots_removed": successful(mode_removed),
        "arming_check_slots_removed": successful(arming_removed),
        "executor_slot_status_explicit": (
            len(executor_removed) >= 2 or (len(executor_ids) >= 2 and set(executor_ids) == {-1})
        ),
        "normal_graceful_shutdown_completed": processes.get("normal_graceful_exit") is True,
        "immediate_post_publish_exit_completed": processes.get("immediate_exit") is True,
        "no_active_registration_at_end": successful(processed[-2:]) and successful(mode_removed[-2:]),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": "1.0",
        "scenario": "p0d1_registration_lifecycle",
        "status": status,
        "reason": (
            "registration resources were removed and the component re-registered cleanly"
            if status == "PASS"
            else "one or more registration lifecycle contracts lacked successful evidence"
        ),
        "checks": checks,
        "registration_count": len(registrations),
        "registration_mode_ids": [
            event["registration_state"].get("mode_id") for event in registrations
        ],
        "registration_instance_ids": registration_instances,
        "unregister_processed_count": len(processed),
        "mode_slot_removed_count": len(mode_removed),
        "arming_check_slot_removed_count": len(arming_removed),
        "executor_slot_removed_count": len(executor_removed),
        "executor_registration_ids": executor_ids,
        "process_results": processes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--lifecycle-log", action="append", type=Path, required=True)
    parser.add_argument("--normal-graceful-exit", action="store_true")
    parser.add_argument("--immediate-exit", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(
        args.trace,
        args.lifecycle_log,
        args.normal_graceful_exit,
        args.immediate_exit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
