#!/usr/bin/env python3
"""Terminate the local N1 producer at a preregistered health-cycle phase."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path


PHASE_OFFSETS_SECONDS = {
    "A": 0.03,
    "B": 0.15,
    "C": 0.26,
}


def next_health_reply(
    health_log: Path, start_offset: int, deadline: float
) -> tuple[dict[str, object], int, int]:
    """Return the first complete health-reply record appended after start_offset."""

    pending = ""
    offset = start_offset
    while time.monotonic() < deadline:
        if health_log.exists():
            with health_log.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                pending += handle.read()
                offset = handle.tell()
            lines = pending.splitlines(keepends=True)
            pending = "" if not lines else ("" if lines[-1].endswith("\n") else lines.pop())
            for line in lines:
                marker = line.find("{")
                if marker < 0:
                    continue
                try:
                    record = json.loads(line[marker:])
                except json.JSONDecodeError:
                    continue
                if record.get("event_type") == "freshness_health_reply":
                    return record, time.monotonic_ns(), offset
        time.sleep(0.005)
    raise TimeoutError("post-ready health reply timeout")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--phase-bucket", choices=("A", "B", "C"), required=True)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--health-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    while not args.ready.exists():
        if time.monotonic() >= deadline:
            raise SystemExit("fault-ready marker timeout")
        time.sleep(0.02)

    ready_observed_monotonic_ns = time.monotonic_ns()
    initial_offset = args.health_log.stat().st_size if args.health_log.exists() else 0
    try:
        phase_anchor, anchor_observed_ns, _ = next_health_reply(
            args.health_log, initial_offset, deadline
        )
    except TimeoutError as exc:
        raise SystemExit(str(exc)) from exc

    requested_offset_seconds = PHASE_OFFSETS_SECONDS[args.phase_bucket]
    target_ns = anchor_observed_ns + int(requested_offset_seconds * 1_000_000_000)
    while time.monotonic_ns() < target_ns:
        time.sleep(0.001)

    ros_time_ns = time.time_ns()
    monotonic_ns = time.monotonic_ns()
    os.kill(args.pid, signal.SIGKILL)
    record = {
        "schema_version": "1.0",
        "event_type": "freshness_fault_injected",
        "fault_marker_id": f"n1-total_process_stop-{monotonic_ns}",
        "fault_type": "TOTAL_PROCESS_STOP",
        "action": "SIGKILL",
        "target_pid": args.pid,
        "ros_time_ns": ros_time_ns,
        "monotonic_ns": monotonic_ns,
        "ready_observed_monotonic_ns": ready_observed_monotonic_ns,
        "requested_delay_seconds": 0.0,
        "health_phase_bucket": args.phase_bucket,
        "phase_anchor_health_reply": phase_anchor,
        "phase_anchor_observed_monotonic_ns": anchor_observed_ns,
        "requested_phase_offset_seconds": requested_offset_seconds,
        "observed_phase_offset_ms": (monotonic_ns - anchor_observed_ns) / 1_000_000,
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
