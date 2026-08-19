#!/usr/bin/env python3
"""Apply one scheduled owned-process fault after observed live preconditions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from scripts.runtime.live_strategy_backend import validate_live_decision


class ActionExecutorError(RuntimeError):
    """The live action cannot be executed from admissible observed state."""


ACTIVE_KINDS = {"offboard_observed_active", "dynamic_mode_observed_active"}
# Live markers the executor can observe, and the workload lifecycle records
# that establish them.  A decision requiring anything else is refused rather
# than applied on an unchecked assumption.
MARKER_SOURCES = {
    "route_active": ACTIVE_KINDS,
    "motion_entered": {"motion_phase_entered"},
    "successor_installed": {"successor_observed_active"},
    # A lost producer stops writing, so the fallback it triggered is only
    # visible in the runner's own lifecycle record.
    "fallback_installed": {"fallback_triggered"},
}


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    records = []
    for index, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            if index == len(text.splitlines()) - 1 and not text.endswith("\n"):
                break
            raise
        if not isinstance(value, dict):
            raise ActionExecutorError("workload lifecycle contains a non-object")
        records.append(value)
    return records


def observed_markers(
    records: list[dict[str, Any]], required: list[str]
) -> dict[str, int | None]:
    """First observation time of each required live marker."""

    unsupported = sorted(set(required) - set(MARKER_SOURCES))
    if unsupported:
        raise ActionExecutorError(
            "the decision requires markers this executor cannot observe: "
            + ", ".join(unsupported)
        )
    observed: dict[str, int | None] = {}
    for marker in required:
        kinds = MARKER_SOURCES[marker]
        times = [
            int(value["received_monotonic_ns"])
            for value in records
            if value.get("kind") in kinds
            and isinstance(value.get("received_monotonic_ns"), int)
        ]
        observed[marker] = min(times) if times else None
    return observed


def observed_preconditions(records: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    activations = [
        int(value["received_monotonic_ns"])
        for value in records
        if value.get("kind") in ACTIVE_KINDS
        and isinstance(value.get("received_monotonic_ns"), int)
    ]
    motion = [
        int(value["received_monotonic_ns"])
        for value in records
        if value.get("kind") == "motion_phase_entered"
        and isinstance(value.get("received_monotonic_ns"), int)
    ]
    return (min(activations) if activations else None, min(motion) if motion else None)


class Jsonl:
    def __init__(self, path: Path, run_id: str) -> None:
        if path.exists():
            raise ActionExecutorError(f"refusing to overwrite: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.run_id = run_id
        self.sequence = 0

    def append(self, kind: str, **payload: Any) -> None:
        value = {
            "schema_version": "1.0",
            "sequence": self.sequence,
            "run_id": self.run_id,
            "kind": kind,
            "received_monotonic_ns": time.monotonic_ns(),
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.sequence += 1


def execute(args: argparse.Namespace) -> None:
    decision = json.loads(args.decision.read_text(encoding="utf-8"))
    if not isinstance(decision, dict):
        raise ActionExecutorError("strategy decision is not an object")
    validate_live_decision(decision)
    log = Jsonl(args.output, args.run_id)
    log.append(
        "strategy_decision",
        strategy=decision["strategy"],
        seed=decision["seed"],
        candidates=decision["candidates"],
        # A corpus decision carries coverage over (action, timing) units; the
        # earlier single-action decision carries it over timing boundaries.
        covered_boundaries=decision.get(
            "covered_units_before_decision",
            decision.get("covered_boundaries_before_decision"),
        ),
        selected_boundary=decision["selected_boundary"],
        selected_unit=decision.get("selected_unit"),
    )
    log.append(
        "action_scheduled",
        action=decision["action"],
        planned_offset_ns=decision["planned_offset_ns"],
        required_state=decision["required_state"],
    )
    required = list(decision.get("required_state") or [])
    if isinstance(decision.get("required_state"), dict):
        required = sorted(decision["required_state"])
    anchor = str(decision.get("timing_anchor", "route_active"))
    if anchor not in required:
        raise ActionExecutorError("the timing anchor is not a required live marker")
    deadline = time.monotonic() + args.precondition_timeout_s
    while time.monotonic() < deadline:
        records = _read_records(args.lifecycle) + _read_records(args.runner_lifecycle)
        markers = observed_markers(records, required)
        activation_ns = markers.get("route_active")
        motion_ns = markers.get("motion_entered")
        anchor_ns = markers.get(anchor)
        if all(value is not None for value in markers.values()) and anchor_ns is not None:
            due_ns = anchor_ns + int(decision["planned_offset_ns"])
            if time.monotonic_ns() >= due_ns:
                request = {
                    "schema_version": "1.0",
                    "run_id": args.run_id,
                    "action": decision["action"],
                    "selected_boundary": decision["selected_boundary"],
                    "planned_offset_ns": decision["planned_offset_ns"],
                    "activation_observed_ns": activation_ns,
                    "motion_entry_observed_ns": motion_ns,
                    "timing_anchor": anchor,
                    "anchor_observed_ns": anchor_ns,
                    "requested_monotonic_ns": time.monotonic_ns(),
                }
                if args.request.exists():
                    raise ActionExecutorError("action request already exists")
                args.request.write_text(
                    json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                log.append(
                    "action_requested",
                    action=decision["action"],
                    selected_boundary=decision["selected_boundary"],
                    planned_offset_ns=decision["planned_offset_ns"],
                    actual_offset_ns=request["requested_monotonic_ns"] - anchor_ns,
                    preconditions={marker: True for marker in markers},
                )
                while True:
                    time.sleep(0.2)
        time.sleep(0.02)
    raise ActionExecutorError(
        "live action preconditions did not become executable: "
        + ", ".join(sorted(required))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--lifecycle", type=Path, required=True)
    parser.add_argument("--runner-lifecycle", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--precondition-timeout-s", type=float, default=45.0)
    args = parser.parse_args()
    try:
        execute(args)
    except (OSError, ValueError, KeyError, ActionExecutorError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
