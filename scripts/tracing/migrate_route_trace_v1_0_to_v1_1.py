#!/usr/bin/env python3
"""Migrate canonical route traces from schema 1.0 to 1.1 without inventing evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "data" / "schemas" / "route_trace.schema.json").read_text(encoding="utf-8"))
LEVELS = set(SCHEMA["properties"]["setpoint_level"]["enum"])
OLD_PHASE_VALUES = {
    "takeoff_phase_marker",
    "hover",
    "straight_line",
    "low_speed_turn",
    "mission_complete",
    "cancelled",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migrate_event(event: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if event.get("schema_version") != "1.0":
        raise ValueError(f"expected schema 1.0 event, got {event.get('schema_version')!r}")
    migrated = dict(event)
    old_level = migrated.get("setpoint_level")
    moved = isinstance(old_level, str) and old_level in OLD_PHASE_VALUES
    migrated["schema_version"] = "1.1"
    migrated["behavior_phase"] = old_level if moved else None
    migrated["setpoint_level"] = old_level if old_level in LEVELS else "unknown"
    migrated["observation"] = None
    return migrated, moved


def migrate(input_path: Path, output_path: Path, report_path: Path) -> dict[str, Any]:
    source_hash = sha256(input_path)
    validator = Draft202012Validator(SCHEMA)
    count = 0
    moved_count = 0
    unknown_count = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=output_path.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
        with input_path.open(encoding="utf-8") as source:
            for line in source:
                count += 1
                event, moved = migrate_event(json.loads(line))
                moved_count += int(moved)
                unknown_count += int(event["setpoint_level"] == "unknown")
                validator.validate(event)
                temporary.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    temporary_path.replace(output_path)

    report = {
        "schema_version": "1.0",
        "migration": "route_trace_v1_0_to_v1_1",
        "source_artifact": {
            "path": str(input_path),
            "sha256": source_hash,
        },
        "output_artifact": {
            "path": str(output_path),
            "sha256": sha256(output_path),
        },
        "event_count": count,
        "phase_values_moved": moved_count,
        "unknown_setpoint_levels": unknown_count,
        "information_fabricated": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = migrate(args.input, args.output, args.report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
