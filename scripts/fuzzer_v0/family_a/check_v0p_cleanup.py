#!/usr/bin/env python3
"""Classify V0-P post-attempt cleanup evidence without terminating processes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.fuzzer_v0.family_a.check_v0p_runtime_residue import evaluate as residue


STATUSES = {
    "CLEAN",
    "RESIDUAL_PROCESS",
    "OCCUPIED_PORT",
    "INCOMPLETE_ARTIFACT_CLOSE",
    "MISSING_TERMINAL_STATE",
    "UNKNOWN",
}
REQUIRED_FIELDS = (
    "land_result_present",
    "disarm_result_present",
    "runner_exit_status",
    "collectors_closed",
    "file_flush_complete",
    "expected_artifacts",
    "closed_artifacts",
)


def evaluate(
    record: dict[str, Any],
    *,
    residue_fixture: dict[str, Any] | None = None,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    missing = [
        field for field in REQUIRED_FIELDS if field not in record or record[field] is None
    ]
    audit = residue(
        "post-attempt",
        fixture=residue_fixture,
        run_dir=run_dir,
    )
    reasons: list[str] = []
    if audit["status"] == "RESIDUAL_PROCESS":
        status = "RESIDUAL_PROCESS"
        reasons.append("post-attempt residual process detected")
    elif audit["status"] == "OCCUPIED_PORT":
        status = "OCCUPIED_PORT"
        reasons.append("post-attempt campaign port remains occupied")
    elif missing:
        status = "UNKNOWN"
        reasons.append("cleanup evidence fields are missing")
    else:
        expected = set(str(item) for item in record["expected_artifacts"])
        closed = set(str(item) for item in record["closed_artifacts"])
        if (
            audit["status"] in {"STALE_STATE", "INCOMPLETE_RUN_DIRECTORY"}
            or not expected <= closed
            or int(record["runner_exit_status"]) != 0
            or not bool(record["collectors_closed"])
            or not bool(record["file_flush_complete"])
        ):
            status = "INCOMPLETE_ARTIFACT_CLOSE"
            reasons.append("artifact, runner, collector, or file-flush closure is incomplete")
        elif not bool(record["land_result_present"]) or not bool(
            record["disarm_result_present"]
        ):
            status = "MISSING_TERMINAL_STATE"
            reasons.append("Land/Disarm result presence is incomplete")
        else:
            status = "CLEAN"
    assert status in STATUSES
    return {
        "schema_version": "1.0",
        "status": status,
        "reasons": reasons,
        "residue_audit": audit,
        "missing_fields": missing,
        "accepted_classification_permitted": status == "CLEAN",
        "terminated_processes": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--residue-fixture", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    record = json.loads(args.input.read_text(encoding="utf-8"))
    fixture = (
        json.loads(args.residue_fixture.read_text(encoding="utf-8"))
        if args.residue_fixture
        else None
    )
    if not isinstance(record, dict):
        raise SystemExit("cleanup input must be a JSON object")
    result = evaluate(record, residue_fixture=fixture, run_dir=args.run_dir)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["status"] == "CLEAN" else 1


if __name__ == "__main__":
    sys.exit(main())
