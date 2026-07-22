#!/usr/bin/env python3
"""Select direct PX4 TimesyncStatus samples for the W1 clock bridge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def select(input_path: Path) -> list[dict]:
    records = [
        json.loads(line)
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [
        record
        for record in records
        if record.get("event_type") == "clock_bridge_sample"
        and record.get("sample_source") == "timesync_status"
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    selected = select(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in selected:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return 0 if len(selected) >= 20 else 1


if __name__ == "__main__":
    raise SystemExit(main())
