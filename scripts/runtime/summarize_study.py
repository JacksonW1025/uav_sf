#!/usr/bin/env python3
"""Verify a closed formal ledger and emit a compact study summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from scripts.accounting.study import verify_study_ledger
from scripts.runtime.run_campaign import read_matrix, validate_matrix


class SummaryError(RuntimeError):
    """The retained compact study evidence is incomplete or inconsistent."""


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SummaryError(f"JSON root is not an object: {path}")
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(matrix_path: Path, study_root: Path) -> dict[str, Any]:
    matrix = read_matrix(matrix_path)
    validate_matrix(matrix)
    ledger_path = study_root / "attempt-ledger.jsonl"
    ledger = verify_study_ledger(ledger_path)
    if ledger["study_id"] not in {None, matrix["study_id"]}:
        raise SummaryError("ledger and matrix study identities differ")
    cells: dict[str, dict[str, Any]] = {}
    oracle_counts: dict[str, Counter[str]] = defaultdict(Counter)
    evidence_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    evaluation_counts: Counter[str] = Counter()
    manifests: dict[str, str] = {}
    for cell in matrix["cells"]:
        attempts = {
            key: value
            for key, value in ledger["attempts"].items()
            if value["cell_id"] == cell["cell_id"]
        }
        accepted = sum(value["outcome"] == "ACCEPTED" for value in attempts.values())
        cell_status = "COMPLETE" if accepted >= cell["accepted_target"] else (
            "MEASUREMENT_INSUFFICIENT" if len(attempts) >= cell["launch_cap"] else "INCOMPLETE"
        )
        cell_outcomes = Counter(str(value["outcome"]) for value in attempts.values())
        outcome_counts.update(cell_outcomes)
        cells[cell["cell_id"]] = {
            "category": cell["category"],
            "accepted": accepted,
            "accepted_target": cell["accepted_target"],
            "launches": len(attempts),
            "launch_cap": cell["launch_cap"],
            "outcomes": dict(sorted(cell_outcomes.items())),
            "status": cell_status,
        }
        for attempt_id, attempt in attempts.items():
            if attempt["state"] != "CLOSED":
                raise SummaryError(f"attempt is not closed: {attempt_id}")
            root = study_root / "results" / attempt_id
            closure = _read(root / "closure.json")
            if closure.get("outcome") != attempt["outcome"]:
                raise SummaryError(f"closure outcome differs from ledger: {attempt_id}")
            for label, digest in closure.get("compact_evidence", {}).items():
                path = root / f"{label.replace('_', '-')}.json"
                if not path.is_file() or _sha256(path) != digest:
                    raise SummaryError(f"compact evidence digest differs: {attempt_id}/{label}")
            raw_manifest = root / "raw-manifest.json"
            if raw_manifest.is_file():
                manifests[attempt_id] = _sha256(raw_manifest)
            evaluation_path = root / "evaluation.json"
            if not evaluation_path.is_file():
                continue
            evaluation = _read(evaluation_path)
            evaluation_counts[str(evaluation.get("status"))] += 1
            evidence_counts[str(evaluation.get("evidence_gate", {}).get("status"))] += 1
            for oracle in evaluation.get("oracles", []):
                oracle_name = str(oracle.get("oracle"))
                for clause in oracle.get("clauses", {}).values():
                    oracle_counts[oracle_name][str(clause.get("status"))] += 1
    statuses = Counter(value["status"] for value in cells.values())
    return {
        "schema_version": "1.0",
        "study_id": matrix["study_id"],
        "repository_revision": matrix["repository_revision"],
        "environment_id": matrix["environment_id"],
        "formal_concurrency": matrix["formal_concurrency"],
        "ledger": {
            "digest": _sha256(ledger_path),
            "event_count": ledger["event_count"],
            "chain_head": ledger["chain_head"],
            "launched_count": ledger["launched_count"],
            "closed_count": ledger["closed_count"],
            "accepted_count": ledger["accepted_count"],
        },
        "study_status": "COMPLETE" if statuses == {"COMPLETE": len(cells)} else (
            "MEASUREMENT_INSUFFICIENT" if statuses.get("MEASUREMENT_INSUFFICIENT") else "INCOMPLETE"
        ),
        "cell_status_counts": dict(sorted(statuses.items())),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "evidence_gate_counts": dict(sorted(evidence_counts.items())),
        "evaluation_counts": dict(sorted(evaluation_counts.items())),
        "oracle_clause_counts": {
            key: dict(sorted(value.items())) for key, value in sorted(oracle_counts.items())
        },
        "cells": cells,
        "raw_evidence_manifests": manifests,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--study-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise SummaryError(f"refusing to overwrite: {args.output}")
        value = summarize(args.matrix, args.study_root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, SummaryError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "PASS", "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
