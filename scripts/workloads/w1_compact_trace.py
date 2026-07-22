#!/usr/bin/env python3
"""Merge W1 mission and sidecar JSONL into a bounded compact source trace."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ALWAYS_KEEP = {
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
    "platform_info",
    "controller_info",
    "vehicle_command",
    "mission_finished",
}
SAMPLED = {"motion_reference", "setpoint_sample", "clock_bridge_sample", "physical_state"}


def load(path: Path, source: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for sequence, line in enumerate(handle, 1):
            if line.strip():
                record = json.loads(line)
                record["source_stream"] = source
                record["source_sequence"] = sequence
                records.append(record)
    return records


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission-events", type=Path, required=True)
    parser.add_argument("--sidecar-events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--stride", type=int, default=20)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.stride < 1:
        parser.error("stride must be positive")

    merged = load(args.mission_events, "mission") + load(args.sidecar_events, "sidecar")
    merged.sort(
        key=lambda item: (
            int(item.get("monotonic_ns", 0)),
            str(item["source_stream"]),
            int(item["source_sequence"]),
        )
    )
    sampled_counts: dict[str, int] = {}
    kept: list[dict[str, Any]] = []
    for record in merged:
        event_type = str(record.get("event_type", ""))
        if event_type in ALWAYS_KEEP:
            kept.append(record)
        elif event_type in SAMPLED:
            sampled_counts[event_type] = sampled_counts.get(event_type, 0) + 1
            if sampled_counts[event_type] == 1 or sampled_counts[event_type] % args.stride == 0:
                kept.append(record)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in kept:
            handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    summary = {
        "schema_version": "1.0",
        "run_id": args.run_id,
        "input_records": len(merged),
        "output_records": len(kept),
        "stride": args.stride,
        "mission_events_sha256": sha256(args.mission_events),
        "sidecar_events_sha256": sha256(args.sidecar_events),
        "compact_trace_sha256": sha256(args.output),
        "event_counts": {
            event_type: sum(1 for record in merged if record.get("event_type") == event_type)
            for event_type in sorted({str(item.get("event_type")) for item in merged})
        },
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
