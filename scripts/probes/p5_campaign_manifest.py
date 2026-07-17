#!/usr/bin/env python3
"""Reconstruct durable P5 campaign state without rerunning or rewriting attempts."""

from __future__ import annotations

import argparse
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.probes.p5_runner import execution_plan, load_disposition, load_matrix


ATTEMPT_SUFFIX = re.compile(r"(?:__)?attempt_(\d+)$")


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def _attempt_id(run_id: str, number: int) -> str:
    return f"{run_id}::attempt_{number}"


def _attempt_number(path: Path) -> int | None:
    match = ATTEMPT_SUFFIX.search(path.name)
    return int(match.group(1)) if match else None


def _runtime_classification(attempt_root: Path, record: dict[str, Any] | None) -> str:
    px4_log = attempt_root / "raw/px4.log"
    runner_result = attempt_root / "raw/runner_result.json"
    px4_text = px4_log.read_text(encoding="utf-8", errors="replace") if px4_log.exists() else ""
    if "stack smashing detected" in px4_text or " Aborted " in px4_text:
        return "ENVIRONMENT_FAILURE"
    if runner_result.exists():
        reason = str(_json(runner_result).get("reason", ""))
        if reason == "timeout in REQUEST_HOLD_AFTER_COMPLETION":
            return "CAMPAIGN_CONFIGURATION_FAILURE"
    if record is None:
        return "PARTIAL_INTERRUPTED_ATTEMPT"
    return str(record.get("validity", "UNKNOWN"))


def _diagnostics(attempt_root: Path, record: dict[str, Any] | None) -> dict[str, Any]:
    px4_log = attempt_root / "raw/px4.log"
    runner_result = attempt_root / "raw/runner_result.json"
    clock_path = attempt_root / "clock_bridge.json"
    trace_path = attempt_root / "route_trace.jsonl"
    px4_text = px4_log.read_text(encoding="utf-8", errors="replace") if px4_log.exists() else ""
    px4_aborted = "stack smashing detected" in px4_text or " Aborted " in px4_text
    runner = _json(runner_result) if runner_result.exists() else {}
    last_trace_event: dict[str, Any] | None = None
    if trace_path.exists():
        lines = trace_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if lines:
            try:
                event = json.loads(lines[-1])
                last_trace_event = {
                    key: event.get(key)
                    for key in ("event_type", "timestamp_us", "route_epoch_id")
                    if key in event
                }
            except json.JSONDecodeError:
                last_trace_event = {"status": "INVALID_FINAL_JSON_LINE"}
    if px4_aborted:
        watchdog = "PX4_ABORT_DETECTED"
        simulator_status = "PX4_ABORT_SIGABRT; Gazebo cleaned up by run wrapper"
    elif runner.get("reason") == "timeout in REQUEST_HOLD_AFTER_COMPLETION":
        watchdog = "RUNNER_TIMEOUT_REQUEST_HOLD"
        simulator_status = "PX4 remained live until normal wrapper cleanup"
    else:
        watchdog = "NO_TERMINAL_CLASSIFICATION_RECORDED"
        simulator_status = "UNKNOWN_AFTER_INTERRUPTION"
    return {
        "process_exit_codes": {
            "campaign_command": None if record is None else record.get("return_code"),
            "px4": "SIGABRT" if px4_aborted else None,
        },
        "watchdog_classification": watchdog,
        "last_valid_trace_event": last_trace_event,
        "clock_bridge_status": _json(clock_path).get("status") if clock_path.exists() else "MISSING",
        "simulator_status": simulator_status,
        "runner_status": runner.get("status"),
        "runner_reason": runner.get("reason"),
    }


def reconstruct(campaign_root: Path) -> dict[str, Any]:
    matrix = load_matrix()
    matched = set(load_disposition()["matched_cells"])
    rows = [row for row in execution_plan(matrix) if row["cell_id"] in matched]
    accepted_attempts: list[dict[str, Any]] = []
    excluded_attempts: list[dict[str, Any]] = []
    environment_failures: list[dict[str, Any]] = []
    configuration_failures: list[dict[str, Any]] = []
    partial_attempts: list[dict[str, Any]] = []
    side_states: dict[str, str] = {}

    for row in rows:
        run_id = str(row["run_id"])
        logical_root = campaign_root / run_id
        accepted_path = logical_root / "accepted_result.json"
        if accepted_path.exists():
            accepted = _json(accepted_path)
            number = int(accepted["accepted_attempt"])
            accepted_attempts.append(
                {
                    "cell_id": row["cell_id"],
                    "pair_id": row["pair_id"],
                    "run_id": run_id,
                    "attempt_id": _attempt_id(run_id, number),
                    "attempt": number,
                    "mechanism": row["mechanism"],
                    "simulation_seed": row["simulation_seed"],
                    "artifact_root": accepted["artifact_root"],
                }
            )
            side_states[run_id] = "COMPLETE_VALID_SIDE"
        else:
            side_states[run_id] = "PENDING"

        seen_attempt_roots: set[Path] = set()
        seen_attempt_numbers: set[int] = set()
        for result_path in sorted(logical_root.glob("**/attempt_result.json")):
            attempt_root = result_path.parent
            seen_attempt_roots.add(attempt_root)
            record = _json(result_path)
            number = int(record.get("attempt", _attempt_number(attempt_root) or 0))
            seen_attempt_numbers.add(number)
            if accepted_path.exists() and number == int(_json(accepted_path)["accepted_attempt"]):
                continue
            classification = _runtime_classification(attempt_root, record)
            summary = {
                "cell_id": row["cell_id"],
                "pair_id": row["pair_id"],
                "run_id": run_id,
                "attempt_id": _attempt_id(run_id, number),
                "attempt": number,
                "mechanism": row["mechanism"],
                "artifact_root": _relative(attempt_root),
                "recorded_validity": record.get("validity"),
                "recovery_classification": classification,
                "return_code": record.get("return_code"),
                "reasons": record.get("reasons", []),
                **_diagnostics(attempt_root, record),
            }
            if classification == "ENVIRONMENT_FAILURE":
                environment_failures.append(summary)
            elif classification == "CAMPAIGN_CONFIGURATION_FAILURE":
                configuration_failures.append(summary)
            else:
                excluded_attempts.append(summary)
            if side_states[run_id] == "PENDING":
                side_states[run_id] = classification

        if logical_root.exists():
            for candidate in sorted(logical_root.glob("**/*attempt_*")):
                if not candidate.is_dir() or candidate in seen_attempt_roots:
                    continue
                number = _attempt_number(candidate)
                if number is None or number in seen_attempt_numbers:
                    continue
                # T1/T2 first create a generic attempt_N directory, then their
                # P0 runner writes to run_id__attempt_N. Ignore the empty
                # allocation placeholder; it is not an interrupted attempt.
                if not any(path.is_file() for path in candidate.rglob("*")):
                    continue
                seen_attempt_numbers.add(number)
                classification = _runtime_classification(candidate, None)
                summary = {
                    "cell_id": row["cell_id"],
                    "pair_id": row["pair_id"],
                    "run_id": run_id,
                    "attempt_id": _attempt_id(run_id, number),
                    "attempt": number,
                    "mechanism": row["mechanism"],
                    "artifact_root": _relative(candidate),
                    "recovery_classification": classification,
                    "reason": "attempt directory has no attempt_result.json",
                    **_diagnostics(candidate, None),
                }
                partial_attempts.append(summary)
                if classification == "ENVIRONMENT_FAILURE":
                    environment_failures.append(summary)
                if side_states[run_id] == "PENDING":
                    side_states[run_id] = "PARTIAL_INTERRUPTED_SIDE"

    pairs: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        pairs.setdefault(str(row["pair_id"]), []).append(row)
    complete_cells: list[str] = []
    partially_completed_cells: list[dict[str, Any]] = []
    pending_cells: list[str] = []
    for pair_id, pair_rows in pairs.items():
        states = {str(row["mechanism"]): side_states[str(row["run_id"])] for row in pair_rows}
        if all(state == "COMPLETE_VALID_SIDE" for state in states.values()):
            complete_cells.append(pair_id)
        elif any(state != "PENDING" for state in states.values()):
            classification = "PARTIAL_PAIR"
            if any(state == "CAMPAIGN_CONFIGURATION_FAILURE" for state in states.values()):
                classification = "INVALID_PAIR_CAMPAIGN_CONFIGURATION"
            partially_completed_cells.append(
                {"pair_id": pair_id, "classification": classification, "sides": states}
            )
        else:
            pending_cells.append(pair_id)

    seed_mapping = {
        str(row["pair_id"]): row["simulation_seed"]
        for row in rows
        if row["mechanism"] == matrix["mechanisms"][0]
    }
    return {
        "planned_applicable_sides": len(rows),
        "planned_applicable_pairs": len(pairs),
        "completed_cells": complete_cells,
        "partially_completed_cells": partially_completed_cells,
        "pending_cells": pending_cells,
        "accepted_attempts": accepted_attempts,
        "excluded_attempts": excluded_attempts,
        "environment_failures": environment_failures,
        "campaign_configuration_failures": configuration_failures,
        "partial_attempts": partial_attempts,
        "side_states": side_states,
        "simulation_seed_mapping": seed_mapping,
    }


def render(
    descriptor: dict[str, Any],
    state: dict[str, Any],
    campaign_root: Path,
    current_process_pid: int | None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    existing_path = campaign_root / "campaign_manifest.json"
    existing = _json(existing_path) if existing_path.exists() else {}
    return {
        **copy.deepcopy(descriptor),
        **state,
        "campaign_root": str(campaign_root.resolve()),
        "resume_history": copy.deepcopy(
            existing.get("resume_history", descriptor.get("resume_history", []))
        ),
        "current_process_pid": current_process_pid,
        "last_checkpoint_time": now,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, required=True)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--current-process-pid", type=int)
    parser.add_argument("--resume-event")
    parser.add_argument("--update-descriptor", action="store_true")
    args = parser.parse_args()
    descriptor = _json(args.descriptor)
    state = reconstruct(args.campaign_root)
    output = args.output or args.campaign_root / "campaign_manifest.json"
    manifest = render(descriptor, state, args.campaign_root, args.current_process_pid)
    if args.resume_event:
        manifest["resume_history"].append(
            {
                "time": manifest["last_checkpoint_time"],
                "event": args.resume_event,
                "process_pid": args.current_process_pid,
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.update_descriptor:
        compact = {
            **descriptor,
            "completed_cells": state["completed_cells"],
            "partially_completed_cells": state["partially_completed_cells"],
            "pending_cells": state["pending_cells"],
            "accepted_attempt_count": len(state["accepted_attempts"]),
            "excluded_attempt_count": len(state["excluded_attempts"]),
            "environment_failure_count": len(state["environment_failures"]),
            "campaign_configuration_failure_count": len(
                state["campaign_configuration_failures"]
            ),
            "last_checkpoint_time": manifest["last_checkpoint_time"],
        }
        args.descriptor.write_text(
            json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "campaign_id": descriptor["campaign_id"],
                "status": descriptor["campaign_status"],
                "accepted_attempts": len(state["accepted_attempts"]),
                "complete_pairs": len(state["completed_cells"]),
                "partial_pairs": len(state["partially_completed_cells"]),
                "pending_pairs": len(state["pending_cells"]),
                "manifest": _relative(output) if output.resolve().is_relative_to(ROOT) else str(output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
