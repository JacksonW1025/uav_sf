#!/usr/bin/env python3
"""Successor Progression Oracle for completion and fault paths."""

from __future__ import annotations

from typing import Any

from scripts.oracles.common import clause, complete_installation, installation_clause


def _event_after(
    events: list[dict[str, Any]], kind: str, anchor_ns: int, *, route: str | None = None
) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in sorted(events, key=lambda value: (value["timestamp_ns"], value["sequence"]))
            if event["kind"] == kind
            and int(event["timestamp_ns"]) >= anchor_ns
            and (route is None or event.get("route") == route)
        ),
        None,
    )


def evaluate_successor_progression(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    transition = plan["transition"]
    thresholds = plan["thresholds"]
    request = next(
        (
            event
            for event in events
            if event["kind"] == "transition_requested"
            and event.get("source_route") == transition["source_route"]
            and event.get("target_route") == transition["target_route"]
        ),
        None,
    )
    anchor = int(request["timestamp_ns"]) if request is not None else 0

    completion = _event_after(
        events, "completion", anchor, route=transition["target_route"]
    )
    if not transition["completion_expected"] and completion is None:
        successor = clause("NOT_APPLICABLE", "completion is not part of this plan")
    elif completion is None:
        successor = clause("VIOLATION", "expected completion event is missing")
    else:
        successor_deadline = int(completion["timestamp_ns"]) + int(
            thresholds["successor_deadline_ns"]
        )
        installation = complete_installation(
            events,
            route=transition["expected_successor"],
            anchor_ns=int(completion["timestamp_ns"]),
            deadline_ns=successor_deadline,
        )
        successor = installation_clause(installation, label="expected successor")

    fault = _event_after(events, "fault_detected", anchor)
    if transition["fault_expected"] and fault is not None:
        fault_observation = clause(
            "PASS", evidence={"fault_sequence": fault["sequence"]}
        )
    elif transition["fault_expected"]:
        fault_observation = clause("VIOLATION", "expected fault event is missing")
    elif fault is not None:
        fault_observation = clause(
            "VIOLATION",
            "an unexpected fault was observed",
            evidence={"fault_sequence": fault["sequence"]},
        )
    else:
        fault_observation = clause("NOT_APPLICABLE", "fault is not part of this plan")

    if not transition["fallback_expected"]:
        fallback = clause("NOT_APPLICABLE", "fault is not part of this plan")
    elif fault is None:
        fallback = clause("UNKNOWN", "fallback cannot be anchored without the expected fault")
    else:
        fallback_trigger = _event_after(
            events,
            "fallback_triggered",
            int(fault["timestamp_ns"]),
            route=transition["expected_fallback"],
        )
        fallback_deadline = int(fault["timestamp_ns"]) + int(
            thresholds["fallback_deadline_ns"]
        )
        installation = complete_installation(
            events,
            route=transition["expected_fallback"],
            anchor_ns=int(fault["timestamp_ns"]),
            deadline_ns=fallback_deadline,
        )
        if fallback_trigger is None:
            fallback = clause("VIOLATION", "safe fallback trigger is missing")
        else:
            fallback = installation_clause(installation, label="safe fallback")

    return {
        "oracle": "successor_progression",
        "clauses": {
            "expected_successor": successor,
            "fault_observation": fault_observation,
            "safe_fallback": fallback,
        },
    }
