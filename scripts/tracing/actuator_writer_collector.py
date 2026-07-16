#!/usr/bin/env python3
"""Summarize explicit allocator and actuator-writer events from a route trace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def summarize(path: Path) -> dict[str, object]:
    writers: set[str] = set()
    allocator_writers: set[str] = set()
    output_events = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            event = json.loads(line)
            if event.get("actuator_writer"):
                writers.add(str(event["actuator_writer"]))
            allocator = event.get("allocator_input")
            if isinstance(allocator, dict) and allocator.get("writer"):
                allocator_writers.add(str(allocator["writer"]))
            if event.get("event_type") == "actuator_output_published":
                output_events += 1
    return {
        "status": "ATTRIBUTED" if output_events and writers else "INSUFFICIENT_EVIDENCE",
        "actuator_writers": sorted(writers),
        "allocator_input_writers": sorted(allocator_writers),
        "actuator_output_events": output_events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route_trace", type=Path)
    args = parser.parse_args()
    result = summarize(args.route_trace)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "ATTRIBUTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
