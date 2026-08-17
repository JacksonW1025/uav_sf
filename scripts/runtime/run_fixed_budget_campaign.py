#!/usr/bin/env python3
"""Run the three live strategies round-by-round under one fixed launch budget."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from scripts.accounting.study import verify_study_ledger
from scripts.runtime.run_campaign import (
    CampaignError,
    _run_phase,
    read_matrix,
    validate_matrix,
)
from scripts.runtime.live_strategy_backend import CONTRACTS


STRATEGIES = ("official_sequence", "bounded_random_timing", "state_aware")
MECHANISMS = ("legacy_offboard", "dynamic_external_mode")


def _records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def observed_coverage(run_root: Path, study_id: str, cell: dict[str, Any]) -> set[str]:
    boundaries: set[str] = set()
    prefix = str(cell["attempt_id_prefix"])
    decision_root = run_root / study_id / "strategy-decisions"
    for decision_path in sorted(decision_root.glob(prefix + "-*.json")):
        attempt_id = decision_path.stem
        lifecycle = run_root / study_id / attempt_id / "raw" / "strategy.lifecycle.jsonl"
        if any(value.get("kind") == "action_requested" for value in _records(lifecycle)):
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            boundaries.add(str(decision["selected_boundary"]))
    return boundaries


def _cell_key(cell: dict[str, Any]) -> tuple[str, str]:
    return str(cell["runtime"]["mechanism"]), str(cell["plan"]["strategy"])


def validate_fixed_matrix(matrix: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    validate_matrix(matrix)
    if matrix.get("live_strategy_backend") not in CONTRACTS:
        raise CampaignError("fixed-budget matrix lacks the shared live backend")
    cells = {_cell_key(cell): cell for cell in matrix["cells"]}
    expected = {(mechanism, strategy) for mechanism in MECHANISMS for strategy in STRATEGIES}
    if set(cells) != expected or len(matrix["cells"]) != len(expected):
        raise CampaignError("fixed-budget matrix must cross two mechanisms and three strategies")
    if any(cell.get("category") != "fixed_budget" for cell in cells.values()):
        raise CampaignError("fixed-budget cells must use the fixed launch tier")
    return cells


def _base_command(args: argparse.Namespace, matrix: dict[str, Any], cell: dict[str, Any], ordinal: int, slot: int) -> list[str]:
    attempt_id = f"{cell['attempt_id_prefix']}-{ordinal:03d}"
    covered = sorted(observed_coverage(args.run_root, matrix["study_id"], cell))
    command = [
        sys.executable,
        "-m",
        "scripts.runtime.formal_attempt",
        "--matrix",
        str(args.matrix),
        "--attestation",
        str(args.attestation),
        "--study-root",
        str(args.study_root),
        "--run-root",
        str(args.run_root),
        "--image",
        args.image,
        "--attempt-id",
        attempt_id,
        "--slot",
        str(slot),
        "--cpu-set",
        str(matrix["resources"]["cpu_sets"][slot]),
        "--memory",
        str(matrix["resources"]["memory_per_attempt"]),
    ]
    for boundary in covered:
        command.extend(["--covered-boundary", boundary])
    return command


def run(args: argparse.Namespace) -> dict[str, Any]:
    matrix = read_matrix(args.matrix)
    cells = validate_fixed_matrix(matrix)
    ledger_path = args.study_root / "attempt-ledger.jsonl"
    ledger = verify_study_ledger(ledger_path)
    open_attempts = [key for key, value in ledger["attempts"].items() if value["state"] != "CLOSED"]
    if open_attempts:
        raise CampaignError("open attempts require explicit closure: " + ", ".join(open_attempts))
    completed = 0
    budget = 3
    for ordinal in range(1, budget + 1):
        for mechanism_index, mechanism in enumerate(MECHANISMS):
            ledger = verify_study_ledger(ledger_path)
            commands = []
            for strategy_index, strategy in enumerate(STRATEGIES):
                cell = cells[(mechanism, strategy)]
                attempt_id = f"{cell['attempt_id_prefix']}-{ordinal:03d}"
                existing = ledger["attempts"].get(attempt_id)
                if existing is not None:
                    if existing["state"] != "CLOSED":
                        raise CampaignError(f"attempt is not closed: {attempt_id}")
                    continue
                slot = (strategy_index + ordinal + mechanism_index) % 4
                commands.append(
                    (attempt_id, _base_command(args, matrix, cell, ordinal, slot))
                )
            if not commands:
                continue
            live = [(attempt_id, [*command, "--phase", "live"]) for attempt_id, command in commands]
            failures = _run_phase(live, phase="live", concurrency=len(live))
            ledger = verify_study_ledger(ledger_path)
            finalize = [
                (attempt_id, [*command, "--phase", "finalize"])
                for attempt_id, command in commands
                if ledger["attempts"].get(attempt_id, {}).get("state") == "LAUNCHED"
            ]
            failures.extend(_run_phase(finalize, phase="finalize", concurrency=len(finalize)))
            completed += len(commands)
            if failures:
                raise CampaignError(
                    "fixed-budget attempt drivers failed after fail-closed accounting: "
                    + ", ".join(sorted(set(failures)))
                )
    ledger = verify_study_ledger(ledger_path)
    if ledger["launched_count"] != 18 or ledger["closed_count"] != 18:
        raise CampaignError("fixed-budget denominator did not close at 18 launches")
    return {
        "schema_version": "1.0",
        "study_id": matrix["study_id"],
        "completed_this_run": completed,
        "launch_budget_per_cell": budget,
        "launched_count": ledger["launched_count"],
        "closed_count": ledger["closed_count"],
        "accepted_count": ledger["accepted_count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--study-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, default=Path("runs"))
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    try:
        value = run(args)
    except (OSError, ValueError, KeyError, CampaignError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
