#!/usr/bin/env python3
"""Generate only complete, closed Family A compact evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = (
    ROOT
    / "data/schemas/family_a_fuzzer_v0_full_compact_evidence.schema.json"
)
ORACLE_IDS = {"ROUTE", "FRESHNESS", "SUCCESSOR", "LINEARIZATION"}


class EvidenceError(RuntimeError):
    """Compact evidence is incomplete or internally inconsistent."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(
    value: dict[str, Any], *, raw_root: Path | None = None
) -> dict[str, Any]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        detail = "; ".join(
            f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
            for error in errors
        )
        raise EvidenceError(detail)

    oracle_records = value["oracles"]
    observed_ids = [item["oracle_id"] for item in oracle_records]
    if set(observed_ids) != ORACLE_IDS or len(observed_ids) != len(ORACLE_IDS):
        raise EvidenceError("all four Oracle applicability records must appear exactly once")
    for oracle in oracle_records:
        if oracle["applicability"] == "REQUIRED":
            if oracle["result"] == "NOT_APPLICABLE" or oracle["sha256"] is None:
                raise EvidenceError(
                    f"required Oracle is incomplete: {oracle['oracle_id']}"
                )
        elif oracle["result"] != "NOT_APPLICABLE" or oracle["sha256"] is not None:
            raise EvidenceError(
                f"NOT_APPLICABLE Oracle was collapsed: {oracle['oracle_id']}"
            )

    if raw_root is not None:
        for record in value["raw_artifacts"]:
            path = raw_root / record["path"]
            if not path.is_file() or sha256(path) != record["sha256"]:
                raise EvidenceError(f"raw artifact hash mismatch: {record['path']}")

    classification = value["classification"]
    oracle_results = {
        record["result"]
        for record in oracle_records
        if record["applicability"] == "REQUIRED"
    }
    if "EXPOSURE" in oracle_results and classification != "EXPOSURE":
        raise EvidenceError("EXPOSURE Oracle result must remain EXPOSURE")
    if "UNKNOWN" in oracle_results and classification not in {
        "UNKNOWN",
        "MEASUREMENT_INSUFFICIENT",
        "OBSERVABILITY_REJECTED",
    }:
        raise EvidenceError("UNKNOWN Oracle result cannot be collapsed to ACCEPTED")
    if value["safety"]["result"] != "PASS" and classification == "ACCEPTED":
        raise EvidenceError("non-PASS safety cannot produce ACCEPTED")
    if value["cleanup"]["result"] != "CLEAN" and classification == "ACCEPTED":
        raise EvidenceError("non-CLEAN cleanup cannot produce ACCEPTED")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    check.add_argument("--input", type=Path, required=True)
    check.add_argument("--raw-root", type=Path)
    build = sub.add_parser("build")
    build.add_argument("--input", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--raw-root", type=Path)
    args = parser.parse_args()
    try:
        value = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise EvidenceError("compact evidence root must be an object")
        validate(value, raw_root=args.raw_root)
        if args.command == "build":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except (EvidenceError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "classification": value["classification"],
                "runtime_started": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
