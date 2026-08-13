#!/usr/bin/env python3
"""Run or resume the frozen formal matrix with bounded isolated concurrency."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from scripts.accounting.study import verify_study_ledger


class CampaignError(RuntimeError):
    """The frozen campaign cannot be scheduled without changing its contract."""


OUTCOME_TARGETS = {
    "deterministic": (5, 10),
    "fault": (8, 16),
    "timing": (10, 20),
}
REQUIRED_THRESHOLDS = {
    "revocation_deadline_ns",
    "installation_deadline_ns",
    "maximum_effect_gap_ns",
    "maximum_command_age_ns",
    "successor_deadline_ns",
    "fallback_deadline_ns",
}


def read_matrix(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CampaignError("matrix root is not an object")
    return value


def validate_matrix(matrix: dict[str, Any]) -> None:
    if matrix.get("schema_version") != "1.0":
        raise CampaignError("unsupported matrix schema")
    for field in ("study_id", "environment_id", "repository_revision"):
        if not str(matrix.get(field, "")).strip():
            raise CampaignError(f"matrix lacks {field}")
    if len(str(matrix["repository_revision"])) != 40:
        raise CampaignError("repository revision is not an exact commit")
    if int(matrix.get("formal_concurrency", 0)) != 4:
        raise CampaignError("formal concurrency must equal the qualified value four")
    resources = matrix.get("resources", {})
    cpu_sets = resources.get("cpu_sets")
    if not isinstance(cpu_sets, list) or len(cpu_sets) != 4 or len(set(cpu_sets)) != 4:
        raise CampaignError("four distinct CPU sets are required")
    if not str(resources.get("memory_per_attempt", "")):
        raise CampaignError("per-attempt memory allocation is required")
    thresholds = matrix.get("thresholds", {})
    if set(thresholds) != REQUIRED_THRESHOLDS or any(
        not isinstance(value, int) or value <= 0 for value in thresholds.values()
    ):
        raise CampaignError("threshold contract is incomplete")
    if not isinstance(matrix.get("maximum_clock_uncertainty_ns"), int):
        raise CampaignError("clock uncertainty bound is missing")
    cells = matrix.get("cells")
    if not isinstance(cells, list) or not cells:
        raise CampaignError("matrix has no cells")
    identities: set[str] = set()
    prefixes: set[str] = set()
    for cell in cells:
        cell_id = str(cell.get("cell_id", ""))
        prefix = str(cell.get("attempt_id_prefix", ""))
        category = str(cell.get("category", ""))
        if not cell_id or cell_id in identities:
            raise CampaignError("cell identities must be nonempty and unique")
        if not prefix or prefix in prefixes:
            raise CampaignError("attempt prefixes must be nonempty and unique")
        identities.add(cell_id)
        prefixes.add(prefix)
        expected = OUTCOME_TARGETS.get(category)
        observed = (cell.get("accepted_target"), cell.get("launch_cap"))
        if expected is None or observed != expected:
            raise CampaignError(f"cell {cell_id} violates its tiered sample contract")
        plan = cell.get("plan", {})
        runtime = cell.get("runtime", {})
        for field in (
            "source_route",
            "target_route",
            "expected_successor",
            "expected_fallback",
            "target_activation_expected",
            "registration_rejection_expected",
            "activation_rejection_expected",
            "completion_expected",
            "fault_expected",
            "fallback_expected",
        ):
            if field not in plan:
                raise CampaignError(f"cell {cell_id} plan lacks {field}")
        if "mechanism" not in runtime:
            raise CampaignError(f"cell {cell_id} runtime lacks mechanism")


def attempt_cell(matrix: dict[str, Any], attempt_id: str) -> dict[str, Any]:
    matches = []
    for cell in matrix.get("cells", []):
        explicit = attempt_id in cell.get("attempt_ids", [])
        prefix = str(cell.get("attempt_id_prefix", ""))
        derived = False
        if prefix and attempt_id.startswith(prefix + "-"):
            suffix = attempt_id[len(prefix) + 1 :]
            derived = suffix.isdigit() and 1 <= int(suffix) <= int(cell["launch_cap"])
        if explicit or derived:
            matches.append(cell)
    if len(matches) != 1:
        raise CampaignError("attempt ID is not assigned to exactly one frozen cell")
    return matches[0]


def _cell_state(matrix: dict[str, Any], ledger: dict[str, Any]) -> list[dict[str, Any]]:
    states = []
    for cell in matrix["cells"]:
        attempts = [
            (attempt_id, value)
            for attempt_id, value in ledger["attempts"].items()
            if value["cell_id"] == cell["cell_id"]
        ]
        accepted = sum(value["outcome"] == "ACCEPTED" for _, value in attempts)
        states.append({
            "cell": cell,
            "launches": len(attempts),
            "accepted": accepted,
            "complete": accepted >= cell["accepted_target"],
            "insufficient": len(attempts) >= cell["launch_cap"] and accepted < cell["accepted_target"],
        })
    return states


def _next_attempt(state: dict[str, Any]) -> str:
    cell = state["cell"]
    return f"{cell['attempt_id_prefix']}-{state['launches'] + 1:03d}"


def _launch(command: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    return result.returncode, result.stdout, result.stderr


def run(args: argparse.Namespace) -> dict[str, Any]:
    matrix = read_matrix(args.matrix)
    validate_matrix(matrix)
    cpu_sets = matrix["resources"]["cpu_sets"]
    concurrency = int(matrix["formal_concurrency"])
    memory = str(matrix["resources"]["memory_per_attempt"])
    if args.dry_run:
        ledger = {"attempts": {}}
    else:
        ledger = verify_study_ledger(args.study_root / "attempt-ledger.jsonl")
        open_attempts = [
            key for key, value in ledger["attempts"].items() if value["state"] != "CLOSED"
        ]
        if open_attempts:
            raise CampaignError("open attempts require explicit closure: " + ", ".join(open_attempts))
    completed_this_run = 0
    while True:
        if not args.dry_run:
            ledger = verify_study_ledger(args.study_root / "attempt-ledger.jsonl")
        states = _cell_state(matrix, ledger)
        pending = [state for state in states if not state["complete"] and not state["insufficient"]]
        if not pending or args.dry_run:
            return {
                "schema_version": "1.0",
                "study_id": matrix["study_id"],
                "dry_run": args.dry_run,
                "completed_this_run": completed_this_run,
                "formal_concurrency": concurrency,
                "cells": [
                    {
                        "cell_id": state["cell"]["cell_id"],
                        "next_attempt_id": None if state["complete"] or state["insufficient"] else _next_attempt(state),
                        "launches": state["launches"],
                        "accepted": state["accepted"],
                        "accepted_target": state["cell"]["accepted_target"],
                        "launch_cap": state["cell"]["launch_cap"],
                        "status": "COMPLETE" if state["complete"] else (
                            "MEASUREMENT_INSUFFICIENT" if state["insufficient"] else "PENDING"
                        ),
                    }
                    for state in states
                ],
            }
        batch = pending[:concurrency]
        commands = []
        for slot, state in enumerate(batch):
            attempt_id = _next_attempt(state)
            if attempt_id in ledger["attempts"]:
                raise CampaignError(f"attempt allocation is not append-only: {attempt_id}")
            commands.append((attempt_id, [
                sys.executable,
                "-m",
                "scripts.runtime.formal_attempt",
                "--matrix", str(args.matrix),
                "--attestation", str(args.attestation),
                "--study-root", str(args.study_root),
                "--run-root", str(args.run_root),
                "--image", args.image,
                "--attempt-id", attempt_id,
                "--slot", str(slot),
                "--cpu-set", cpu_sets[slot],
                "--memory", memory,
            ]))
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(_launch, command): attempt_id for attempt_id, command in commands}
            failures = []
            for future in as_completed(futures):
                attempt_id = futures[future]
                returncode, stdout, stderr = future.result()
                completed_this_run += 1
                print(json.dumps({"attempt_id": attempt_id, "returncode": returncode, "stdout": stdout.strip(), "stderr": stderr.strip()}), flush=True)
                if returncode != 0:
                    failures.append(attempt_id)
        if failures:
            raise CampaignError("attempt drivers failed after fail-closed accounting: " + ", ".join(failures))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--study-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, default=Path("runs"))
    parser.add_argument("--image", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, ValueError, KeyError, CampaignError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
