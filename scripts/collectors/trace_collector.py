#!/usr/bin/env python3
"""Append normalized Family A events to a contiguous hash-chained trace."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO

from scripts.adapters.family_a import FamilyAAdapter
from scripts.model.runtime_route import ZERO_HASH, event_digest, validate_event


class CollectorError(RuntimeError):
    """Trace collection cannot preserve its evidence contract."""


class TraceCollector:
    def __init__(self, path: Path, run_id: str) -> None:
        if path.exists():
            raise CollectorError(f"refusing to overwrite trace: {path}")
        if not run_id.strip():
            raise CollectorError("run_id is required")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.run_id = run_id
        self.sequence = 0
        self.previous_hash = ZERO_HASH
        self._handle = path.open("x", encoding="utf-8")

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        if self._handle.closed:
            raise CollectorError("collector is closed")
        value = dict(event)
        value["schema_version"] = "1.0"
        value["run_id"] = self.run_id
        value["sequence"] = self.sequence
        value["previous_hash"] = self.previous_hash
        value.pop("event_hash", None)
        value["event_hash"] = event_digest(value)
        validate_event(value)
        self._handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self.sequence += 1
        self.previous_hash = value["event_hash"]
        return value

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.flush()
            os.fsync(self._handle.fileno())
            self._handle.close()

    def __enter__(self) -> "TraceCollector":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def collect_stream(
    source: TextIO, *, output: Path, run_id: str, mechanism: str
) -> int:
    adapter = FamilyAAdapter(mechanism)
    with TraceCollector(output, run_id) as collector:
        collector.append(
            {
                "kind": "collection_started",
                "timestamp_ns": 0,
                "source_domain": "collector_monotonic",
                "clock_bridge_id": "collector-origin",
            }
        )
        last_timestamp = 0
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise CollectorError(f"input line {line_number} must be an object")
            event = adapter.adapt(raw, run_id=run_id)
            last_timestamp = max(last_timestamp, int(event["timestamp_ns"]))
            collector.append(event)
        collector.append(
            {
                "kind": "collection_stopped",
                "timestamp_ns": last_timestamp + 1,
                "source_domain": "collector_monotonic",
                "clock_bridge_id": "collector-origin",
            }
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mechanism", required=True)
    args = parser.parse_args()
    try:
        return collect_stream(
            sys.stdin, output=args.output, run_id=args.run_id, mechanism=args.mechanism
        )
    except (CollectorError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
