#!/usr/bin/env python3
"""Inject one bounded freshness fault and emit an exact defensive-test marker."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fault-type", choices=("TOTAL_PROCESS_STOP", "SETPOINT_ONLY_STALL"), required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    if args.delay_seconds < 0:
        parser.error("fault delay must be non-negative")
    deadline = time.monotonic() + args.timeout
    while not args.ready.exists():
        if time.monotonic() >= deadline:
            raise SystemExit("fault-ready marker timeout")
        time.sleep(0.02)

    ready_observed_monotonic_ns = time.monotonic_ns()
    time.sleep(args.delay_seconds)
    ros_time_ns = time.time_ns()
    monotonic_ns = time.monotonic_ns()
    marker_id = f"freshness-{args.fault_type.lower()}-{monotonic_ns}"
    action: str
    if args.fault_type == "TOTAL_PROCESS_STOP":
        os.kill(args.pid, signal.SIGKILL)
        action = "SIGKILL"
    else:
        args.control_dir.mkdir(parents=True, exist_ok=True)
        (args.control_dir / "setpoint.off").touch(exist_ok=False)
        action = "SETPOINT_CHANNEL_DISABLED"

    record = {
        "schema_version": "1.0",
        "event_type": "freshness_fault_injected",
        "fault_marker_id": marker_id,
        "fault_type": args.fault_type,
        "action": action,
        "target_pid": args.pid,
        "ros_time_ns": ros_time_ns,
        "monotonic_ns": monotonic_ns,
        "ready_observed_monotonic_ns": ready_observed_monotonic_ns,
        "requested_delay_seconds": args.delay_seconds,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.event_log.write_text(
        f"[{ros_time_ns // 1_000_000_000}.{ros_time_ns % 1_000_000_000:09d}] "
        + json.dumps(record, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
