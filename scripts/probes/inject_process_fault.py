#!/usr/bin/env python3
"""Inject one preregistered process signal and write an exact timestamp record."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path


SIGNALS = {
    "sigterm": signal.SIGTERM,
    "sigkill": signal.SIGKILL,
    "sigstop_sigcont": signal.SIGSTOP,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--fault", choices=tuple(SIGNALS), required=True)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--pause-seconds", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    while not args.ready.exists():
        if time.monotonic() >= deadline:
            raise SystemExit("fault-ready marker timeout")
        time.sleep(0.05)

    ros_time_ns = time.time_ns()
    monotonic_ns = time.monotonic_ns()
    delivered = SIGNALS[args.fault]
    os.kill(args.pid, delivered)
    record: dict[str, object] = {
        "schema_version": "1.0",
        "event_type": "process_fault_injected",
        "fault_class": args.fault,
        "target_pid": args.pid,
        "signal": signal.Signals(delivered).name,
        "ros_time_ns": ros_time_ns,
        "monotonic_ns": monotonic_ns,
        "pause_seconds": args.pause_seconds if args.fault == "sigstop_sigcont" else None,
    }
    if args.fault == "sigstop_sigcont":
        time.sleep(args.pause_seconds)
        resume_ros_time_ns = time.time_ns()
        resume_monotonic_ns = time.monotonic_ns()
        os.kill(args.pid, signal.SIGCONT)
        record.update(
            {
                "resume_signal": "SIGCONT",
                "resume_ros_time_ns": resume_ros_time_ns,
                "resume_monotonic_ns": resume_monotonic_ns,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.event_log.write_text(
        f"[{ros_time_ns / 1_000_000_000:.9f}] "
        + json.dumps(record, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
