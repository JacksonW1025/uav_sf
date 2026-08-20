#!/usr/bin/env python3
"""Observe, filter, apply, re-observe, select again — in flight.

The single-action executor waits for one preregistered action's markers and
applies it.  This one runs the loop: it folds the in-flight sidecars into the
online state, asks the frozen policy what to apply next, applies it at that
action's own anchor, and goes back to observing.

Four things it does not do, each for a reason the rest of the study depends on:

* It never widens its own options.  The admissible set is recomputed by the
  policy from the observed state; the executor only reports the state.
* It never invents a decision moment.  A step is decided when some unapplied
  action's own anchor is first observed, or when the episode reaches a terminal
  state.  Deciding on a fixed clock would make the choice depend on the poll
  rate rather than on what the flight did.
* It never treats running out of time as a choice.  Stopping is selected by the
  policy and recorded as a step; a timeout is a refusal.
* It never spends CPU it does not have to.  The fold is incremental and the
  telemetry sidecar is read on its own slower cadence, because competing for
  the pinned cores is what the clock uncertainty bound measures.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from scripts.corpus.core_actions import core_action
from scripts.runtime.closed_loop_policy import (
    POLICY_SCHEMA,
    STOP,
    policy_digest,
    select_step,
    validate_policy,
)
from scripts.state.online_state import OnlineProjection, OnlineStateError


class ClosedLoopError(RuntimeError):
    """The closed loop cannot proceed from admissible observed state."""


# How often the loop re-reads each source.  The lifecycle sidecars are small
# and carry the events a decision turns on; telemetry is orders of magnitude
# larger and only moves the authority family and the land detector.
LIFECYCLE_POLL_S = 0.02
TELEMETRY_POLL_S = 0.5


class TailReader:
    """Read one appended sidecar incrementally, keeping a partial line back.

    A live writer can be mid-line when the reader arrives, and the supervisor
    can stop it at any moment.  Anything short of a complete line is held until
    the rest of it lands rather than being parsed or discarded.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._offset = 0
        self._pending = ""

    def read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        size = self.path.stat().st_size
        if size < self._offset:
            raise ClosedLoopError(f"in-flight sidecar was truncated: {self.path}")
        if size == self._offset:
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            handle.seek(self._offset)
            chunk = handle.read()
            self._offset = handle.tell()
        text = self._pending + chunk
        lines = text.split("\n")
        self._pending = lines.pop()
        records = []
        for line in lines:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ClosedLoopError(f"corrupt in-flight record in {self.path}") from exc
            if not isinstance(value, dict):
                raise ClosedLoopError(f"in-flight record is not an object: {self.path}")
            records.append(value)
        return records


class Jsonl:
    def __init__(self, path: Path, run_id: str) -> None:
        if path.exists():
            raise ClosedLoopError(f"refusing to overwrite: {path}")
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


def request_path(directory: Path, action_id: str) -> Path:
    """Where one action's request is written.

    Each action has its own path because each is consumed by a different node.
    One shared path worked while an episode applied one action; an episode that
    applies two would have the second overwrite the first, or the wrong
    consumer act on it.
    """

    return directory / f"{action_id}.request.json"


def decision_is_due(
    projection: OnlineProjection,
    policy: dict[str, Any],
    applied: list[str],
) -> tuple[bool, str | None]:
    """Whether a decision point has arrived, and which anchor opened it.

    A step is decided when some unapplied action in the class has become
    admissible and has had every live marker it declares observed, its timing
    anchor among them.

    Both conditions are needed and they are not the same.  The gate is the
    in-flight weakening of the action's precondition, which says the state is
    one the action is legal in.  The live markers say the flight has seen the
    things the action's placement depends on.  A termination's gate asks for
    external authority without a fault, but the action also declares that
    motion has been entered, because it is aimed at the straight translation.
    Deciding on the gate alone would let a slow motion entry put the action
    before the phase it is supposed to land in.
    """

    state = projection.state
    for action_id in policy["corpus"]:
        if action_id in applied:
            continue
        action = core_action(action_id)
        if action.online_gate is None or not action.online_gate(state):
            continue
        profile = action.live_profile
        anchor = profile.timing_anchor if profile is not None else None
        if anchor is None:
            continue
        if any(
            projection.marker_time_ns(marker) is None
            for marker in action.live_markers
        ):
            continue
        if projection.marker_time_ns(anchor) is not None:
            return True, anchor
    if state.terminal and applied:
        # The episode is over and something was applied, so the policy still
        # gets to record that it stops rather than the loop ending silently.
        return True, None
    return False, None


def run(args: argparse.Namespace) -> dict[str, Any]:
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise ClosedLoopError("closed-loop policy is not an object")
    validate_policy(policy)
    log = Jsonl(args.output, args.run_id)
    log.append(
        "closed_loop_started",
        strategy=policy["strategy"],
        seed=policy["seed"],
        class_id=policy["class_id"],
        corpus=policy["corpus"],
        maximum_steps=policy["maximum_steps"],
        covered_units=policy["covered_units_before_episode"],
    )

    projection = OnlineProjection(str(policy["mechanism"]))
    lifecycle = [TailReader(path) for path in (args.lifecycle, args.runner_lifecycle)]
    telemetry = TailReader(args.telemetry)
    telemetry_read_at = 0.0

    applied: list[str] = []
    covered = set(policy["covered_units_before_episode"])
    steps: list[dict[str, Any]] = []
    deadline = time.monotonic() + args.episode_timeout_s

    while len(steps) < int(policy["maximum_steps"]):
        due = False
        anchor_marker: str | None = None
        while time.monotonic() < deadline:
            records: list[dict[str, Any]] = []
            for reader in lifecycle:
                records.extend(reader.read())
            if time.monotonic() - telemetry_read_at >= TELEMETRY_POLL_S:
                records.extend(telemetry.read())
                telemetry_read_at = time.monotonic()
            if records:
                records.sort(key=lambda value: int(value["received_monotonic_ns"]))
                projection.extend(records)
            due, anchor_marker = decision_is_due(projection, policy, applied)
            if due:
                break
            time.sleep(LIFECYCLE_POLL_S)
        if not due:
            raise ClosedLoopError(
                "no decision point was reached before the episode timeout; "
                f"observed state was {projection.state.key()}"
            )

        step = select_step(
            policy=policy,
            step_index=len(steps),
            state=projection.state,
            applied=applied,
            covered_units=covered,
        )
        step["decided_monotonic_ns"] = time.monotonic_ns()
        step["opened_by_marker"] = anchor_marker
        steps.append(step)
        log.append(
            "closed_loop_decision",
            step_index=step["step_index"],
            action=step["action"],
            selected_unit=step["selected_unit"],
            admissible_units=step["admissible_units"],
            observed_state=step["observed_state_key"],
        )
        if step["action"] == STOP:
            break

        anchor = str(step["timing_anchor"])
        anchor_ns = projection.marker_time_ns(anchor)
        if anchor_ns is None:
            raise ClosedLoopError(f"the selected unit anchors on an unobserved {anchor}")
        due_ns = anchor_ns + int(step["planned_offset_ns"])
        while time.monotonic_ns() < due_ns:
            if time.monotonic() >= deadline:
                raise ClosedLoopError("the episode timed out before its scheduled action")
            records = []
            for reader in lifecycle:
                records.extend(reader.read())
            if records:
                records.sort(key=lambda value: int(value["received_monotonic_ns"]))
                projection.extend(records)
            time.sleep(LIFECYCLE_POLL_S)

        target = request_path(args.request_dir, str(step["action"]))
        if target.exists():
            raise ClosedLoopError(f"action request already exists: {target}")
        requested_ns = time.monotonic_ns()
        request = {
            "schema_version": "2.0",
            "run_id": args.run_id,
            "step_index": step["step_index"],
            "action": step["action"],
            "selected_boundary": step["selected_boundary"],
            "planned_offset_ns": step["planned_offset_ns"],
            "timing_anchor": anchor,
            "anchor_observed_ns": anchor_ns,
            "requested_monotonic_ns": requested_ns,
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        step["anchor_observed_ns"] = anchor_ns
        step["requested_monotonic_ns"] = requested_ns
        step["applied_offset_ns"] = requested_ns - anchor_ns
        log.append(
            "closed_loop_applied",
            step_index=step["step_index"],
            action=step["action"],
            selected_unit=step["selected_unit"],
            planned_offset_ns=step["planned_offset_ns"],
            actual_offset_ns=step["applied_offset_ns"],
            timing_anchor=anchor,
        )
        applied.append(str(step["action"]))
        covered.add(str(step["selected_unit"]))

    decisions = {
        "schema_version": POLICY_SCHEMA,
        "policy_digest": policy_digest(policy),
        "run_id": args.run_id,
        "steps": steps,
    }
    if args.decisions.exists():
        raise ClosedLoopError(f"refusing to overwrite: {args.decisions}")
    args.decisions.parent.mkdir(parents=True, exist_ok=True)
    args.decisions.write_text(
        json.dumps(decisions, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    log.append(
        "closed_loop_completed",
        applied_actions=applied,
        steps=len(steps),
        stopped_by_choice=bool(steps) and steps[-1]["action"] == STOP,
    )
    return decisions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--lifecycle", type=Path, required=True)
    parser.add_argument("--runner-lifecycle", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--request-dir", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--episode-timeout-s", type=float, default=90.0)
    args = parser.parse_args()
    try:
        run(args)
    except (OSError, ValueError, KeyError, OnlineStateError, ClosedLoopError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
