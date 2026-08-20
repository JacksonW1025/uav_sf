#!/usr/bin/env python3
"""Replay core-action preconditions against retained evidence.

This is the offline half of the Stage 2 selection.  For every accepted attempt
it derives the semantic-state trajectory, finds each moment where a proposed
core action actually fired, and evaluates that action's precondition on the
state that existed immediately before the firing event.

A precondition that is false where the action demonstrably fired is a defect in
the model, not in the flight: the flight already happened and was admissible.
An action with no retained instance is reported as unvalidated rather than as
passing, because a predicate no evidence exercises has not been checked.

The check is read-only.  It never edits retained evidence and creates no
denominator.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

from scripts.analysis.semantic_state_replay import (
    ReplayError,
    _accepted_attempts,
    _attempt_inputs,
    discover_studies,
)
from scripts.corpus.core_actions import (
    CORE_ACTIONS,
    CoreActionError,
    core_action,
    core_action_records,
    validate_declarations,
)
from scripts.model.runtime_route import read_trace
from scripts.state.semantic_state import (
    SemanticState,
    SemanticStateError,
    derive_trajectory,
    maximum_command_age_from_plan,
)


class PreconditionCheckError(RuntimeError):
    """The retained corpus cannot support the precondition replay."""


CHECK_ID = "stage2-core-action-precondition-check-v1"


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise PreconditionCheckError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def timed_decision_times(root: Path, study_id: str, attempt_id: str) -> dict[str, int]:
    """When the executor issued each timed action, in the trace's own clock.

    A timed action's precondition is what the generator evaluated before
    deciding, so it is read at that moment.  A launch configuration has no such
    moment — its record is written during setup, before the episode has done
    anything — so its precondition, which describes the state its effect is
    legal in, is read at that effect instead.

    Host-side sidecars keep their monotonic timestamp through trace closure, so
    the executor's record is directly comparable to a trace timestamp.
    """

    path = root / "runs" / study_id / attempt_id / "raw" / "strategy.lifecycle.jsonl"
    if not path.is_file():
        return {}
    times: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict) or record.get("kind") != "action_requested":
            continue
        moment = record.get("requested_monotonic_ns", record.get("received_monotonic_ns"))
        action_id = str(record.get("action", ""))
        known = {item.action_id for item in CORE_ACTIONS}
        if not isinstance(moment, int) or action_id not in known:
            # A single-action decision records the runtime fault mode rather
            # than a core action identity, and is judged at its effect.
            continue
        profile = core_action(action_id).live_profile
        if profile is not None and profile.application == "launch":
            continue
        times.setdefault(action_id, moment)
    return times


def check_attempt(
    root: Path, study_id: str, attempt_id: str, cell_id: str
) -> list[dict[str, Any]]:
    """Every core-action firing observed in one retained attempt."""

    plan_path, trace_path = _attempt_inputs(root, study_id, attempt_id)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    events = read_trace(trace_path)
    trajectory = derive_trajectory(
        events, maximum_command_age_ns=maximum_command_age_from_plan(plan)
    )
    if len(trajectory.steps) != len(events):
        raise PreconditionCheckError(
            f"{attempt_id}: the trajectory does not align with its trace"
        )

    decided = timed_decision_times(root, study_id, attempt_id)
    decision_states: dict[str, SemanticState] = {}
    if decided:
        for event, step in zip(events, trajectory.steps):
            for action_id, moment in decided.items():
                if int(event["timestamp_ns"]) <= moment:
                    decision_states[action_id] = step.state

    instances: list[dict[str, Any]] = []
    # One tester action can be recorded by more than one observer.  A genuine
    # repeat of an action always follows a new activation, so an instance that
    # shares its predecessor's activation identity is a duplicate observation
    # rather than a second action.
    last_authority: dict[str, str | None] = {}
    satisfied_once: set[str] = set()
    previous_state = SemanticState()
    for event, step in zip(events, trajectory.steps):
        if int(step.sequence) != int(event["sequence"]):
            raise PreconditionCheckError(
                f"{attempt_id}: step and event sequence differ at {event['sequence']}"
            )
        for action in CORE_ACTIONS:
            if not action.marker(event, previous_state, step.state):
                continue
            authority = previous_state.activation_id
            judged = decision_states.get(action.action_id, previous_state)
            satisfied = bool(action.precondition(judged))
            # Two observers can record one action, and a supervisory observer
            # can record it late.  A firing that shares its predecessor's
            # authority is the first case.  A firing whose precondition is
            # false after the action already fired legally is the second: a
            # genuine repeat would satisfy the precondition again.
            repeated = (
                action.action_id in last_authority
                and last_authority[action.action_id] == authority
            ) or (not satisfied and action.action_id in satisfied_once)
            last_authority[action.action_id] = authority
            if satisfied:
                satisfied_once.add(action.action_id)
            instances.append(
                {
                    "study_id": study_id,
                    "attempt_id": attempt_id,
                    "cell_id": cell_id,
                    "action_id": action.action_id,
                    "sequence": int(event["sequence"]),
                    "kind": str(event["kind"]),
                    "role": "duplicate_observation" if repeated else "action",
                    "precondition_satisfied": satisfied,
                    "state_before": judged.key(),
                    "judged_at": (
                        "decision" if action.action_id in decision_states else "effect"
                    ),
                    "state_after": step.state.key(),
                }
            )
        previous_state = step.state
    return instances


def qualification_attempts(root: Path, study_id: str) -> list[str]:
    """Attempts of a non-formal study, which has run evidence but no ledger."""

    study = root / "runs" / study_id
    if not study.is_dir():
        raise PreconditionCheckError(f"qualification study is missing: {study}")
    attempts = sorted(
        path.name
        for path in study.iterdir()
        if path.is_dir() and (path / "derived" / "closed.trace.jsonl").is_file()
    )
    if not attempts:
        raise PreconditionCheckError(f"qualification study has no closed trace: {study}")
    return attempts


def run(
    root: Path,
    output_root: Path,
    *,
    selected: list[str] | None = None,
    qualification_studies: list[str] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    output_root = output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise PreconditionCheckError(f"output directory is not empty: {output_root}")
    validate_declarations()

    studies = discover_studies(root)
    if selected:
        known = {study_id for study_id, _ in studies}
        unknown = sorted(set(selected) - known)
        if unknown:
            raise PreconditionCheckError("unknown study identity: " + ", ".join(unknown))
        studies = [item for item in studies if item[0] in set(selected)]

    instances: list[dict[str, Any]] = []
    attempts = 0
    for study_id, directory in studies:
        for event in _accepted_attempts(directory / "attempt-ledger.jsonl"):
            attempts += 1
            instances.extend(
                check_attempt(
                    root,
                    study_id,
                    str(event["attempt_id"]),
                    str(event.get("cell_id", "")),
                )
            )
    for study_id in qualification_studies or []:
        # A qualification opens no ledger, so its attempts come from the
        # retained run evidence directly.  They carry no denominator either.
        for attempt_id in qualification_attempts(root, study_id):
            attempts += 1
            instances.extend(check_attempt(root, study_id, attempt_id, "qualification"))

    per_action: list[dict[str, Any]] = []
    for action in CORE_ACTIONS:
        every_instance = [
            item for item in instances if item["action_id"] == action.action_id
        ]
        duplicates = [item for item in every_instance if item["role"] != "action"]
        selected_instances = [item for item in every_instance if item["role"] == "action"]
        satisfied = [item for item in selected_instances if item["precondition_satisfied"]]
        violations = [
            item for item in selected_instances if not item["precondition_satisfied"]
        ]
        cells = Counter(
            (item["study_id"], item["cell_id"]) for item in selected_instances
        )
        per_action.append(
            {
                "action_id": action.action_id,
                "inventory_action_id": action.inventory_action_id,
                "lifecycle_phase": action.lifecycle_phase,
                "availability": dict(sorted(action.availability.items())),
                "precondition": action.precondition_text,
                "marker": action.marker_text,
                "instances": len(selected_instances),
                "duplicate_observations": len(duplicates),
                "precondition_satisfied": len(satisfied),
                "precondition_violations": len(violations),
                "attempts_with_instance": len(
                    {item["attempt_id"] for item in selected_instances}
                ),
                "cells": [
                    {"study_id": study, "cell_id": cell, "instances": count}
                    for (study, cell), count in sorted(cells.items())
                ],
                "status": (
                    "unvalidated"
                    if not selected_instances
                    else ("consistent" if not violations else "inconsistent")
                ),
                "example_violations": [
                    {
                        "attempt_id": item["attempt_id"],
                        "sequence": item["sequence"],
                        "state_before": item["state_before"],
                    }
                    for item in violations[:5]
                ],
            }
        )

    summary = {
        "schema_version": "1.0",
        "check_id": CHECK_ID,
        "attempts_checked": attempts,
        "total_instances": len(instances),
        "actions": per_action,
        "consistent_actions": sum(
            1 for record in per_action if record["status"] == "consistent"
        ),
        "inconsistent_actions": sorted(
            record["action_id"] for record in per_action if record["status"] == "inconsistent"
        ),
        "unvalidated_actions": sorted(
            record["action_id"] for record in per_action if record["status"] == "unvalidated"
        ),
        "immutability": {
            "modified_frozen_evidence": False,
            "created_formal_denominator": False,
        },
    }
    _write_new(
        output_root / "core-actions.json",
        json.dumps(
            {
                "schema_version": "1.0",
                "check_id": CHECK_ID,
                "frozen": False,
                "actions": core_action_records(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    _write_new(
        output_root / "precondition-check.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    _write_new(
        output_root / "per-instance.jsonl",
        "".join(
            json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
            for item in instances
        ),
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--study", action="append", default=None)
    parser.add_argument("--qualification-study", action="append", default=None)
    args = parser.parse_args()
    try:
        summary = run(
            args.root,
            args.output_root,
            selected=args.study,
            qualification_studies=args.qualification_study,
        )
    except (
        PreconditionCheckError,
        CoreActionError,
        ReplayError,
        SemanticStateError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "PASS", "summary": summary}, sort_keys=True))
    return 0 if not summary["inconsistent_actions"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
