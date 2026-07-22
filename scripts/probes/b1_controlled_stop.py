#!/usr/bin/env python3
"""Stop the B1 reference process through its public process lifecycle boundary."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    deadline = time.monotonic() + args.timeout
    while not args.ready.exists():
        if time.monotonic() >= deadline:
            raise SystemExit("B1 release-ready marker timeout")
        time.sleep(0.02)
    ready_observed = time.monotonic_ns()
    ros_time_ns = time.time_ns()
    monotonic_ns = time.monotonic_ns()
    os.kill(args.pid, signal.SIGKILL)
    record = {
        "schema_version": "1.0",
        "event_type": "b1_controlled_process_stop",
        "marker_id": f"b1-controlled-stop-{monotonic_ns}",
        "action": "SIGKILL",
        "lifecycle_boundary": "locally_owned_reference_process",
        "target_pid": args.pid,
        "ros_time_ns": ros_time_ns,
        "monotonic_ns": monotonic_ns,
        "ready_observed_monotonic_ns": ready_observed,
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
