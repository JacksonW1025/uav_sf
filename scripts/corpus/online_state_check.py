#!/usr/bin/env python3
"""Measure what the in-flight state projection costs, against retained evidence.

A closed-loop generator has to choose its next action while the aircraft is
flying, from the online projection in `scripts/state/online_state.py`.  That
projection cannot see the command lineage and cannot classify a producer loss
in time, so each action's online gate is a weakening of the offline
precondition the signed corpus declares.

A weakening can hold where the precondition does not.  This replay reports
where and for how long, over evidence that already exists:

* it folds the retained in-flight sidecars of an attempt into the online
  trajectory the executor would have seen, and
* it folds the same attempt's closed trace into the offline semantic
  trajectory, and
* it reports, per action, the interval where the online gate held while the
  offline precondition did not.

That interval is the whole finding.  Zero means the gate is an adequate
in-flight stand-in for the precondition on this evidence.  Nonzero is a window
in which a closed loop would act on a state the signed corpus does not admit,
and it is reported with its size rather than tuned away.

The replay is read-only.  It never edits retained evidence and creates no
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
    _accepted_attempts,
    _attempt_inputs,
    discover_studies,
)
from scripts.corpus.core_actions import (
    CORE_ACTIONS,
    CoreAction,
    CoreActionError,
    validate_declarations,
)
from scripts.corpus.precondition_check import qualification_attempts
from scripts.model.runtime_route import read_trace
from scripts.state.online_state import (
    OnlineState,
    OnlineStateError,
    OnlineStep,
    derive_online_trajectory,
    merge_records,
    state_at,
    validate_vocabularies,
)
from scripts.state.semantic_state import (
    SemanticState,
    SemanticStateError,
    derive_trajectory,
    maximum_command_age_from_plan,
)


class OnlineStateCheckError(RuntimeError):
    """The retained corpus cannot support the online projection replay."""


CHECK_ID = "step-f-online-state-agreement-v1"
# The three in-flight sources an executor reads while the aircraft is flying.
LIFECYCLE_SIDECARS = ("workload.lifecycle.jsonl", "runner.lifecycle.jsonl")
TELEMETRY_SIDECAR = "telemetry.sidecar.jsonl"


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise OnlineStateCheckError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _records(path: Path) -> list[dict[str, Any]]:
    """Read one appended sidecar, tolerating an unterminated final line.

    A sidecar is appended by a live process that a supervisor may stop at any
    moment, so its last line can be a fragment.  Everything before it is
    complete and is kept.
    """

    if not path.is_file():
        return []
    values: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                break
            raise OnlineStateCheckError(f"corrupt in-flight record at {path}:{index + 1}")
        if not isinstance(value, dict):
            raise OnlineStateCheckError(f"in-flight record is not an object at {path}")
        values.append(value)
    return values


def in_flight_records(root: Path, study_id: str, attempt_id: str) -> list[dict[str, Any]]:
    raw = root / "runs" / study_id / attempt_id / "raw"
    lifecycle = [_records(raw / name) for name in LIFECYCLE_SIDECARS]
    telemetry = _records(raw / TELEMETRY_SIDECAR)
    if not any(lifecycle) and not telemetry:
        raise OnlineStateCheckError(
            f"{study_id}/{attempt_id} retains no in-flight sidecar to replay"
        )
    return merge_records(*lifecycle, telemetry)


def fired_moments(root: Path, study_id: str, attempt_id: str) -> dict[str, int]:
    """When the executor issued each timed action, in the shared monotonic clock."""

    path = root / "runs" / study_id / attempt_id / "raw" / "strategy.lifecycle.jsonl"
    known = {action.action_id for action in CORE_ACTIONS}
    moments: dict[str, int] = {}
    for record in _records(path):
        if record.get("kind") != "action_requested":
            continue
        action_id = str(record.get("action", ""))
        moment = record.get("requested_monotonic_ns", record.get("received_monotonic_ns"))
        if action_id in known and isinstance(moment, int):
            moments.setdefault(action_id, moment)
    return moments


def _offline_timeline(
    events: list[dict[str, Any]], trajectory: Any, action: CoreAction
) -> list[tuple[int, bool]]:
    """When the offline precondition changed truth value, in trace time."""

    points: list[tuple[int, bool]] = []
    for event, step in zip(events, trajectory.steps):
        moment = int(event["timestamp_ns"])
        if moment <= 0:
            # Meta events carry no time of their own; they cannot bound an
            # interval and are left out rather than pinned to the origin.
            continue
        value = bool(action.precondition(step.state))
        if not points or points[-1][1] != value:
            points.append((moment, value))
    return points


def _online_timeline(steps: list[OnlineStep], action: CoreAction) -> list[tuple[int, bool]]:
    """When the online gate changed truth value, in the same monotonic clock."""

    if action.online_gate is None:
        return []
    points: list[tuple[int, bool]] = []
    for step in steps:
        value = bool(action.online_gate(step.state))
        if not points or points[-1][1] != value:
            points.append((step.monotonic_ns, value))
    return points


def _semantic_state_at(
    events: list[dict[str, Any]], trajectory: Any, moment: int
) -> SemanticState:
    """The offline semantic state as of a moment in the shared clock."""

    selected = SemanticState()
    for event, step in zip(events, trajectory.steps):
        timestamp = int(event["timestamp_ns"])
        if timestamp <= 0:
            continue
        if timestamp > moment:
            break
        selected = step.state
    return selected


def _value_at(points: list[tuple[int, bool]], moment: int) -> bool:
    value = False
    for point_ns, point_value in points:
        if point_ns > moment:
            break
        value = point_value
    return value


def _disagreement(
    online: list[tuple[int, bool]], offline: list[tuple[int, bool]], *, horizon_ns: int
) -> dict[str, Any]:
    """How long the online gate held while the offline precondition did not."""

    changes = sorted({moment for moment, _ in online} | {moment for moment, _ in offline})
    changes = [moment for moment in changes if moment <= horizon_ns]
    if not changes:
        return {
            "online_true_from_ns": None,
            "offline_true_from_ns": None,
            "online_only_ns": 0,
            "offline_only_ns": 0,
            "online_only_intervals": 0,
        }
    bounds = changes + [horizon_ns]
    online_only = 0
    offline_only = 0
    intervals = 0
    previous_online_only = False
    for index, start in enumerate(bounds[:-1]):
        span = bounds[index + 1] - start
        if span <= 0:
            continue
        is_online = _value_at(online, start)
        is_offline = _value_at(offline, start)
        if is_online and not is_offline:
            online_only += span
            if not previous_online_only:
                intervals += 1
            previous_online_only = True
        else:
            previous_online_only = False
            if is_offline and not is_online:
                offline_only += span
    return {
        "online_true_from_ns": next((m for m, v in online if v), None),
        "offline_true_from_ns": next((m for m, v in offline if v), None),
        "online_only_ns": online_only,
        "offline_only_ns": offline_only,
        "online_only_intervals": intervals,
    }


def check_attempt(
    root: Path, study_id: str, attempt_id: str, cell_id: str
) -> list[dict[str, Any]]:
    """Compare both projections of one retained attempt, action by action."""

    plan_path, trace_path = _attempt_inputs(root, study_id, attempt_id)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    mechanism = str(plan.get("transition", {}).get("target_route", ""))
    events = read_trace(trace_path)
    trajectory = derive_trajectory(
        events, maximum_command_age_ns=maximum_command_age_from_plan(plan)
    )
    if len(trajectory.steps) != len(events):
        raise OnlineStateCheckError(
            f"{attempt_id}: the trajectory does not align with its trace"
        )
    steps = derive_online_trajectory(
        in_flight_records(root, study_id, attempt_id), mechanism=mechanism
    )
    if not steps:
        raise OnlineStateCheckError(f"{attempt_id}: no in-flight record could be folded")

    trace_times = [int(event["timestamp_ns"]) for event in events if int(event["timestamp_ns"]) > 0]
    # Both projections are compared over the interval both observed.  Beyond
    # the last shared moment one side has no evidence, and a disagreement there
    # would measure the recording window rather than the gate.
    horizon_ns = min(max(trace_times), steps[-1].monotonic_ns) if trace_times else steps[-1].monotonic_ns
    fired = fired_moments(root, study_id, attempt_id)

    results: list[dict[str, Any]] = []
    for action in CORE_ACTIONS:
        if action.online_gate is None:
            continue
        online = _online_timeline(steps, action)
        offline = _offline_timeline(events, trajectory, action)
        measurement = _disagreement(online, offline, horizon_ns=horizon_ns)
        record: dict[str, Any] = {
            "study_id": study_id,
            "attempt_id": attempt_id,
            "cell_id": cell_id,
            "mechanism": mechanism,
            "action_id": action.action_id,
            "horizon_ns": horizon_ns,
            **measurement,
        }
        moment = fired.get(action.action_id)
        if moment is not None:
            record["fired_at_ns"] = moment
            record["online_gate_at_firing"] = _value_at(online, moment)
            record["precondition_at_firing"] = _value_at(offline, moment)
            record["online_state_at_firing"] = state_at(steps, moment).key()
            record["semantic_state_at_firing"] = _semantic_state_at(
                events, trajectory, moment
            ).key()
        results.append(record)
    return results


def _action_summary(action: CoreAction, records: list[dict[str, Any]]) -> dict[str, Any]:
    mine = [record for record in records if record["action_id"] == action.action_id]
    disagreeing = [record for record in mine if record["online_only_ns"] > 0]
    fired = [record for record in mine if "fired_at_ns" in record]
    blocked = [record for record in fired if not record["online_gate_at_firing"]]
    # A gate that refuses a firing the offline precondition also refuses is
    # agreeing with the signed corpus rather than defeating it.  Only a gate
    # that refuses an action the corpus admits is a defect in the gate.
    against_precondition = [
        record for record in blocked if record["precondition_at_firing"]
    ]
    widest = max((record["online_only_ns"] for record in mine), default=0)
    return {
        "action_id": action.action_id,
        "precondition": action.precondition_text,
        "online_gate": action.online_gate_text,
        "attempts_checked": len(mine),
        "attempts_with_online_only_window": len(disagreeing),
        "widest_online_only_ns": widest,
        "median_online_only_ns": (
            sorted(record["online_only_ns"] for record in mine)[len(mine) // 2]
            if mine
            else 0
        ),
        "firings_observed": len(fired),
        # A gate false where the action fired and its precondition held would
        # have stopped a flight the corpus admits, which is a defect in the
        # gate.  One where the precondition was false too is the divergence the
        # signed corpus already records, restated in the in-flight projection.
        "firings_the_gate_would_have_blocked": len(against_precondition),
        "firings_blocked_where_the_precondition_also_failed": len(blocked)
        - len(against_precondition),
        "example_blocked_firings": [
            {
                "attempt_id": record["attempt_id"],
                "precondition_at_firing": record["precondition_at_firing"],
                "online_state": record["online_state_at_firing"],
                "semantic_state": record["semantic_state_at_firing"],
            }
            for record in blocked[:5]
        ],
        "example_online_only_windows": [
            {
                "attempt_id": record["attempt_id"],
                "online_only_ns": record["online_only_ns"],
                "online_true_from_ns": record["online_true_from_ns"],
                "offline_true_from_ns": record["offline_true_from_ns"],
            }
            for record in sorted(
                disagreeing, key=lambda item: -item["online_only_ns"]
            )[:5]
        ],
        "status": (
            "unchecked"
            if not mine
            else (
                "blocking"
                if against_precondition
                else ("adequate" if not disagreeing else "weaker_than_precondition")
            )
        ),
    }


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
        raise OnlineStateCheckError(f"output directory is not empty: {output_root}")
    validate_declarations()
    validate_vocabularies()

    studies = discover_studies(root)
    if selected:
        known = {study_id for study_id, _ in studies}
        unknown = sorted(set(selected) - known)
        if unknown:
            raise OnlineStateCheckError("unknown study identity: " + ", ".join(unknown))
        studies = [item for item in studies if item[0] in set(selected)]

    records: list[dict[str, Any]] = []
    attempts = 0
    skipped: list[dict[str, str]] = []
    for study_id, directory in studies:
        for event in _accepted_attempts(directory / "attempt-ledger.jsonl"):
            attempt_id = str(event["attempt_id"])
            try:
                found = check_attempt(
                    root, study_id, attempt_id, str(event.get("cell_id", ""))
                )
            except OnlineStateCheckError as exc:
                # A study retained before the in-flight sidecars were kept has
                # nothing to replay.  It is named rather than counted as
                # agreement.
                skipped.append({"study_id": study_id, "attempt_id": attempt_id, "reason": str(exc)})
                continue
            attempts += 1
            records.extend(found)
    for study_id in qualification_studies or []:
        for attempt_id in qualification_attempts(root, study_id):
            try:
                found = check_attempt(root, study_id, attempt_id, "qualification")
            except OnlineStateCheckError as exc:
                skipped.append({"study_id": study_id, "attempt_id": attempt_id, "reason": str(exc)})
                continue
            attempts += 1
            records.extend(found)

    per_action = [
        _action_summary(action, records)
        for action in CORE_ACTIONS
        if action.online_gate is not None
    ]
    summary = {
        "schema_version": "1.0",
        "check_id": CHECK_ID,
        "attempts_checked": attempts,
        "attempts_skipped": len(skipped),
        "studies": sorted({record["study_id"] for record in records}),
        "actions": per_action,
        "adequate_actions": sum(1 for item in per_action if item["status"] == "adequate"),
        "weaker_actions": sum(
            1 for item in per_action if item["status"] == "weaker_than_precondition"
        ),
        "blocking_actions": sum(1 for item in per_action if item["status"] == "blocking"),
        "status_counts": dict(sorted(Counter(item["status"] for item in per_action).items())),
    }
    _write_new(
        output_root / "online-state-agreement.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    _write_new(
        output_root / "per-attempt.jsonl",
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        ),
    )
    if skipped:
        _write_new(
            output_root / "skipped-attempts.jsonl",
            "".join(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                for record in skipped
            ),
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--study", action="append", dest="studies")
    parser.add_argument("--qualification-study", action="append", dest="qualification")
    args = parser.parse_args()
    try:
        summary = run(
            args.root,
            args.output_root,
            selected=args.studies,
            qualification_studies=args.qualification,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        CoreActionError,
        OnlineStateError,
        OnlineStateCheckError,
        SemanticStateError,
    ) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
