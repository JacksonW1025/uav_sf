#!/usr/bin/env python3
"""Resolve a plan's conditional obligations against the trace, before any Oracle.

An episode that carries a state-dependent sequence cannot preregister one fixed
set of obligations.  Terminating the owning producer and then reclaiming the
route owes a completely installed reclaim and no fallback; terminating it and
stopping there owes a completely installed fallback and no completion.  A plan
that declares neither, by setting both to "not expected", silently switches off
the very contract boundary each action aims at.

So the plan declares both, with the condition that selects between them, and
this module picks the branch.  Three rules keep that honest:

* The condition is preregistered.  It is written into the plan before the
  flight, chosen from a fixed vocabulary, and the branch it selects is fully
  specified there.  Nothing is derived after the fact.
* The condition is decided by trace evidence alone.  It never reads the
  executor's own record of what it did.  A tester that could assert the
  condition would be choosing which obligations to be judged against, which is
  the dual of the rule that a derived state phase is not evidence that the
  tester performed an action.
* The resolution is reported.  The evaluation records which condition was
  evaluated, whether it held, and which obligations were applied, so a reader
  can see the branch rather than infer it.

A plan without a `sequence_obligations` block resolves to itself, so every
retained schema 1.2 and 1.3 plan evaluates exactly as before.
"""

from __future__ import annotations

from typing import Any

from scripts.oracles.common import complete_installation
from scripts.oracles.transition_scope import (
    selected_transition_request,
    transition_window_end_ns,
)


class SequenceObligationError(ValueError):
    """A plan's conditional obligations cannot be resolved."""


# Obligations a branch is allowed to restate.  A branch may only move the
# obligations that differ between the sequences an episode class admits; the
# route identities and the owner expectations are properties of the class, not
# of which sequence ran, so they stay in the transition.
BRANCH_FIELDS = (
    "expected_successor",
    "target_activation_count",
    "completion_expected",
    "fault_expected",
    "fallback_expected",
)
# Every condition an obligation branch may name.  Adding one means adding it
# here, in `data/schemas/experiment_plan.schema.json`, and in `_CONDITIONS`
# below, so a plan can never name a condition nothing can decide.
SEQUENCE_CONDITIONS = ("external_route_reclaimed_after_fault",)
# Event kinds whose presence is required only by the branch that expects them.
# The plan preregisters the union over both branches, so a reader can see what
# either sequence would owe; the resolution narrows it to the branch that ran,
# because the other sequence's evidence is absent by construction rather than
# by a collection failure.
CONDITIONAL_EVENT_KINDS = {
    "completion_expected": "completion",
    "fault_expected": "fault_detected",
    "fallback_expected": "fallback_triggered",
}


def _first_fault_ns(events: list[dict[str, Any]], anchor_ns: int, end_ns: int) -> int | None:
    faults = [
        int(event["timestamp_ns"])
        for event in events
        if event["kind"] == "fault_detected"
        and anchor_ns <= int(event["timestamp_ns"]) <= end_ns
    ]
    return min(faults) if faults else None


def _external_route_reclaimed_after_fault(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    """Did the tested route install completely again after a fault?

    This is the reclaim, read from the trace rather than from the tester.  A
    reclaim is not a repeated observation of the first installation: it is a
    complete installation of the tested route that begins after the fault that
    revoked it.
    """

    transition = plan["transition"]
    request = selected_transition_request(events, plan)
    anchor_ns = int(request["timestamp_ns"]) if request is not None else 0
    window_end_ns = (
        transition_window_end_ns(events, plan, request)
        if request is not None
        else max((int(event["timestamp_ns"]) for event in events), default=0)
    )
    fault_ns = _first_fault_ns(events, anchor_ns, window_end_ns)
    if fault_ns is None:
        return {"holds": False, "reason": "no fault was observed in the transition window"}
    installation = complete_installation(
        events,
        route=transition["target_route"],
        anchor_ns=fault_ns,
        deadline_ns=window_end_ns,
    )
    if not installation.get("complete"):
        return {
            "holds": False,
            "reason": "the tested route did not install completely after the fault",
            "fault_timestamp_ns": fault_ns,
        }
    return {
        "holds": True,
        "reason": "the tested route installed completely after the fault",
        "fault_timestamp_ns": fault_ns,
        "installation": installation,
    }


_CONDITIONS = {
    "external_route_reclaimed_after_fault": _external_route_reclaimed_after_fault,
}


def evaluate_condition(
    events: list[dict[str, Any]], plan: dict[str, Any], condition: str
) -> dict[str, Any]:
    try:
        decide = _CONDITIONS[condition]
    except KeyError as exc:
        raise SequenceObligationError(f"unsupported sequence condition: {condition}") from exc
    return decide(events, plan)


def resolve_obligations(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """The plan the Oracles are run against, and how its branch was chosen.

    Without a `sequence_obligations` block the plan is returned unchanged and
    the resolution is `None`, so every retained plan evaluates as before.
    """

    block = plan.get("sequence_obligations")
    if block is None:
        return plan, None
    if not isinstance(block, dict):
        raise SequenceObligationError("sequence_obligations must be an object")
    condition = block.get("condition")
    if condition not in SEQUENCE_CONDITIONS:
        raise SequenceObligationError("sequence_obligations names an unsupported condition")
    branch = block.get("when_observed")
    if not isinstance(branch, dict) or not set(branch) <= set(BRANCH_FIELDS) or not branch:
        raise SequenceObligationError("sequence_obligations branch fields differ from the schema")

    outcome = evaluate_condition(events, plan, str(condition))
    applied = dict(branch) if outcome["holds"] else {}
    transition = {**plan["transition"], **applied}
    # The Gate must ask for the evidence the branch that ran actually owes.
    # Asking for the union would make every episode inadmissible for missing
    # the other sequence's events, which it never had a way to produce.
    required = [
        kind
        for kind in plan["required_event_kinds"]
        if kind not in CONDITIONAL_EVENT_KINDS.values()
    ]
    required.extend(
        kind
        for field, kind in CONDITIONAL_EVENT_KINDS.items()
        if transition[field] and kind in plan["required_event_kinds"]
    )
    resolved = {
        **plan,
        "transition": transition,
        "required_event_kinds": required,
    }
    resolution = {
        "condition": condition,
        "held": bool(outcome["holds"]),
        "reason": outcome["reason"],
        # Which branch the Oracles were actually run against, named rather than
        # left for a reader to infer from the verdicts.
        "branch": "when_observed" if outcome["holds"] else "when_absent",
        "applied_obligations": dict(sorted(applied.items())),
        "required_event_kinds": sorted(required),
    }
    return resolved, resolution
