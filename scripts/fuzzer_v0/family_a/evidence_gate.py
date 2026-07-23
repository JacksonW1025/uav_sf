#!/usr/bin/env python3
"""Evidence Gate 1.0 for Family A result classification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class EvidenceGateError(RuntimeError):
    """Evidence inputs cannot support a classification."""


ORACLE_RESULTS = {"PASS", "EXPOSURE", "VIOLATION", "UNKNOWN", "NOT_APPLICABLE"}


def classify(record: dict[str, Any]) -> dict[str, Any]:
    oracles = record.get("oracles")
    if not isinstance(oracles, list) or len(oracles) != 4:
        raise EvidenceGateError("exactly four Oracle applicability records are required")
    seen: set[str] = set()
    required_results: list[str] = []
    for oracle in oracles:
        oracle_id = oracle.get("oracle_id")
        if oracle_id in seen:
            raise EvidenceGateError(f"duplicate Oracle: {oracle_id}")
        seen.add(str(oracle_id))
        applicability = oracle.get("applicability")
        result = oracle.get("result")
        if result not in ORACLE_RESULTS:
            raise EvidenceGateError(f"invalid Oracle result: {oracle_id}")
        if applicability == "NOT_APPLICABLE":
            if result != "NOT_APPLICABLE":
                raise EvidenceGateError(f"NOT_APPLICABLE collapsed: {oracle_id}")
        elif applicability == "REQUIRED":
            if result == "NOT_APPLICABLE":
                raise EvidenceGateError(f"required Oracle missing: {oracle_id}")
            required_results.append(str(result))
        else:
            raise EvidenceGateError(f"invalid Oracle applicability: {oracle_id}")
    if seen != {"ROUTE", "FRESHNESS", "SUCCESSOR", "LINEARIZATION"}:
        raise EvidenceGateError("Oracle identity set is incomplete")

    safety = record.get("safety_result")
    cleanup = record.get("cleanup_result")
    if safety != "PASS":
        classification = (
            str(safety)
            if safety
            in {
                "FORMAL_SAFETY_STOP",
                "MEASUREMENT_INSUFFICIENT",
                "ENVIRONMENT_FAILURE",
                "CAMPAIGN_CONFIGURATION_FAILURE",
            }
            else "MEASUREMENT_INSUFFICIENT"
        )
    elif cleanup != "CLEAN":
        classification = "OBSERVABILITY_REJECTED"
    elif any(result in {"EXPOSURE", "VIOLATION"} for result in required_results):
        classification = "EXPOSURE"
    elif "UNKNOWN" in required_results:
        classification = "MEASUREMENT_INSUFFICIENT"
    elif not required_results or any(result != "PASS" for result in required_results):
        classification = "OBSERVABILITY_REJECTED"
    else:
        classification = "ACCEPTED"
    return {
        "schema_version": "1.0",
        "gate_id": "EVIDENCE_GATE_1_0",
        "classification": classification,
        "oracle_results": oracles,
        "safety_result": safety,
        "cleanup_result": cleanup,
        "default_pass_used": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        value = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise EvidenceGateError("evidence gate input must be an object")
        result = classify(value)
    except (EvidenceGateError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
