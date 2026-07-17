#!/usr/bin/env python3
"""Compact high-rate route data events after full-trace analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


HIGH_RATE_EVENTS = {
    "actuator_motors",
    "actuator_output_published",
    "allocator_input_published",
    "px4_setpoint_consumed",
    "px4_setpoint_received",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compact(source: Path, output: Path, stride: int) -> dict[str, Any]:
    if stride < 1:
        raise ValueError("stride must be positive")
    events = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line]
    source_sha256 = _sha256(source)
    grouped: dict[tuple[str, object, str], list[int]] = defaultdict(list)
    for index, event in enumerate(events):
        if event.get("event_type") in HIGH_RATE_EVENTS:
            grouped[
                (
                    str(event.get("event_type")),
                    event.get("route_epoch_id"),
                    str(event.get("timestamp_domain")),
                )
            ].append(index)
    retained_high_rate: set[int] = set()
    for indices in grouped.values():
        retained_high_rate.update(indices[::stride])
        retained_high_rate.add(indices[-1])
    compacted = [
        event
        for index, event in enumerate(events)
        if event.get("event_type") not in HIGH_RATE_EVENTS or index in retained_high_rate
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n" for event in compacted),
        encoding="utf-8",
    )
    return {
        "schema_version": "1.0",
        "policy": "retain all control/lifecycle events; retain first, every Nth, and last high-rate event per epoch/domain",
        "high_rate_event_types": sorted(HIGH_RATE_EVENTS),
        "stride": stride,
        "source_sha256": source_sha256,
        "output_sha256": _sha256(output),
        "full_event_count": len(events),
        "compact_event_count": len(compacted),
        "full_event_type_counts": dict(sorted(Counter(event["event_type"] for event in events).items())),
        "compact_event_type_counts": dict(
            sorted(Counter(event["event_type"] for event in compacted).items())
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stride", type=int, default=5)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    report = compact(args.input, args.output, args.stride)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.summary is not None:
        summary = json.loads(args.summary.read_text(encoding="utf-8"))
        summary["full_trace_event_count"] = report["full_event_count"]
        summary["trace_event_count"] = report["compact_event_count"]
        summary["processed_trace_policy"] = {
            **summary.get("processed_trace_policy", {}),
            "post_analysis_compaction_stride": args.stride,
            "full_trace_sha256": report["source_sha256"],
            "compact_trace_sha256": report["output_sha256"],
        }
        args.summary.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
