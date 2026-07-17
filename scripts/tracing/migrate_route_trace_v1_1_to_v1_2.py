#!/usr/bin/env python3
"""Migrate canonical route traces from 1.1 to 1.2 without inventing identities."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "data" / "schemas" / "route_trace.schema.json").read_text(encoding="utf-8")
)
IDENTITY_FIELDS = (
    "route_epoch_id",
    "route_activation_id",
    "producer_session_id",
    "registration_instance_id",
    "route_change_source",
)


def migrate_event(event: dict[str, Any]) -> dict[str, Any]:
    if event.get("schema_version") != "1.1":
        raise ValueError("input event must use route trace schema 1.1")
    migrated = dict(event)
    migrated["schema_version"] = "1.2"
    for field in IDENTITY_FIELDS:
        migrated[field] = None
    return migrated


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migrate(source: Path, output: Path) -> dict[str, Any]:
    validator = Draft202012Validator(SCHEMA)
    source_sha256 = _sha256(source)
    events = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = migrate_event(json.loads(line))
        validator.validate(event)
        events.append(event)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n" for event in events),
        encoding="utf-8",
    )
    return {
        "schema_version": "1.0",
        "migration": "route_trace_1.1_to_1.2",
        "source": str(source),
        "source_sha256": source_sha256,
        "output": str(output),
        "output_sha256": _sha256(output),
        "event_count": len(events),
        "identity_policy": "all new identity fields are null because schema 1.1 cannot establish them",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = migrate(args.input, args.output)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
