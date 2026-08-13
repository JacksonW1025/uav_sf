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
    if not transition["completion_expected"]:
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

    timing_bounds = plan["strategy"]["timing_bounds_ns"]
    adjacent_delay_bound = timing_bounds.get("adjacent_after_activation_ns")
    if adjacent_delay_bound is None:
        adjacent_timing = clause("NOT_APPLICABLE", "no adjacent request is planned")
        adjacent_order = clause("NOT_APPLICABLE", "no adjacent request is planned")
        adjacent_successor = clause("NOT_APPLICABLE", "no adjacent request is planned")
    else:
        activation = _event_after(
            events, "activation", anchor, route=transition["target_route"]
        )
        adjacent = _event_after(events, "adjacent_request", anchor)
        if activation is None or adjacent is None:
            adjacent_timing = clause(
                "VIOLATION", "target activation or adjacent request evidence is missing"
            )
            adjacent_order = clause(
                "UNKNOWN", "adjacent ordering cannot be established without both anchors"
            )
            adjacent_successor = clause(
                "UNKNOWN", "adjacent successor cannot be anchored"
            )
        else:
            activation_ns = int(activation["timestamp_ns"])
            adjacent_ns = int(adjacent["timestamp_ns"])
            observed_delay = adjacent_ns - activation_ns
            minimum_delay, maximum_delay = map(int, adjacent_delay_bound)
            delay_ok = minimum_delay <= observed_delay <= maximum_delay
            adjacent_timing = clause(
                "PASS" if delay_ok else "VIOLATION",
                *(() if delay_ok else ("adjacent request left its preregistered timing bucket",)),
                evidence={
                    "activation_sequence": activation["sequence"],
                    "adjacent_sequence": adjacent["sequence"],
                    "observed_delay_ns": observed_delay,
                    "allowed_delay_ns": [minimum_delay, maximum_delay],
                },
            )
            completion_after_activation = _event_after(
                events, "completion", activation_ns, route=transition["target_route"]
            )
            order_key = next(
                (
                    key
                    for key in (
                        "adjacent_before_completion_ns",
                        "completion_before_adjacent_ns",
                        "adjacent_completion_distance_ns",
                    )
                    if key in timing_bounds
                ),
                None,
            )
            completion_ns = (
                int(completion_after_activation["timestamp_ns"])
                if completion_after_activation is not None
                else None
            )
            if order_key == "adjacent_before_completion_ns":
                if completion_ns is None:
                    adjacent_order = clause(
                        "PASS",
                        evidence={"observed_order": "completion_preempted"},
                    )
                else:
                    distance = completion_ns - adjacent_ns
                    low, high = map(int, timing_bounds[order_key])
                    ok = low <= distance <= high
                    adjacent_order = clause(
                        "PASS" if ok else "VIOLATION",
                        *(() if ok else ("adjacent request was not before completion as planned",)),
                        evidence={"observed_order": "adjacent_before_completion", "distance_ns": distance, "allowed_distance_ns": [low, high]},
                    )
            elif order_key == "completion_before_adjacent_ns":
                distance = adjacent_ns - completion_ns if completion_ns is not None else -1
                low, high = map(int, timing_bounds[order_key])
                ok = completion_ns is not None and low <= distance <= high
                adjacent_order = clause(
                    "PASS" if ok else "VIOLATION",
                    *(() if ok else ("completion was not before the adjacent request as planned",)),
                    evidence={"observed_order": "completion_before_adjacent" if completion_ns is not None else "completion_missing", "distance_ns": distance, "allowed_distance_ns": [low, high]},
                )
            elif order_key == "adjacent_completion_distance_ns":
                if completion_ns is None:
                    adjacent_order = clause(
                        "PASS", evidence={"observed_order": "completion_preempted_near_boundary"}
                    )
                else:
                    distance = abs(adjacent_ns - completion_ns)
                    low, high = map(int, timing_bounds[order_key])
                    ok = low <= distance <= high
                    adjacent_order = clause(
                        "PASS" if ok else "VIOLATION",
                        *(() if ok else ("completion and adjacent request were outside the near bucket",)),
                        evidence={"observed_order": "near_completion", "distance_ns": distance, "allowed_distance_ns": [low, high]},
                    )
            else:
                adjacent_order = clause(
                    "UNKNOWN", "the adjacent request has no preregistered order contract"
                )
            adjacent_installation = complete_installation(
                events,
                route=transition["expected_successor"],
                anchor_ns=adjacent_ns,
                deadline_ns=adjacent_ns + int(thresholds["successor_deadline_ns"]),
            )
            adjacent_successor = installation_clause(
                adjacent_installation, label="adjacent-request successor"
            )

    return {
        "oracle": "successor_progression",
        "clauses": {
            "expected_successor": successor,
            "fault_observation": fault_observation,
            "safe_fallback": fallback,
            "adjacent_timing": adjacent_timing,
            "adjacent_order": adjacent_order,
            "adjacent_successor": adjacent_successor,
        },
    }
