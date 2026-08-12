#!/usr/bin/env python3
"""Freshness and Lineage Oracle for the installed target route."""

from __future__ import annotations

from typing import Any

from scripts.model.runtime_route import EFFECT_EVENT_KINDS, RuntimeRouteInstance
from scripts.oracles.common import clause, complete_installation


def evaluate_freshness_lineage(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    transition = plan["transition"]
    target = transition["target_route"]
    request = next(
        (
            event
            for event in events
            if event["kind"] == "transition_requested"
            and event.get("source_route") == transition["source_route"]
            and event.get("target_route") == target
        ),
        None,
    )
    if request is None:
        unknown = clause("UNKNOWN", "matching transition request is missing")
        return {
            "oracle": "freshness_lineage",
            "clauses": {"freshness": unknown, "lineage": unknown},
        }
    anchor = int(request["timestamp_ns"])
    deadline = anchor + int(plan["thresholds"]["installation_deadline_ns"])
    installation = complete_installation(
        events, route=target, anchor_ns=anchor, deadline_ns=deadline
    )
    if not installation["complete"]:
        unknown = clause("UNKNOWN", "target route installation is incomplete")
        return {
            "oracle": "freshness_lineage",
            "clauses": {"freshness": unknown, "lineage": unknown},
        }

    identity = RuntimeRouteInstance(**installation["identity"])
    target_effects = [
        event
        for event in events
        if event["kind"] in EFFECT_EVENT_KINDS
        and event.get("route") == target
        and anchor <= int(event["timestamp_ns"]) <= int(installation["completed_at_ns"])
    ]
    ages = [
        int(event["timestamp_ns"]) - int(event["command_subject_ns"])
        for event in target_effects
    ]
    maximum_age = int(plan["thresholds"]["maximum_command_age_ns"])
    invalid_ages = [age for age in ages if age < 0 or age > maximum_age]
    if not ages:
        freshness = clause("UNKNOWN", "no target command-consumption evidence exists")
    elif invalid_ages:
        freshness = clause(
            "VIOLATION",
            "a consumed command is future-dated or exceeds the freshness bound",
            evidence={"observed_ages_ns": ages, "maximum_command_age_ns": maximum_age},
        )
    else:
        freshness = clause(
            "PASS",
            evidence={"maximum_observed_age_ns": max(ages), "checked_events": len(ages)},
        )

    conflicts = [
        event["sequence"] for event in target_effects if not identity.matches(event)
    ]
    kinds = {event["kind"] for event in target_effects if identity.matches(event)}
    complete_kinds = set(EFFECT_EVENT_KINDS) <= kinds
    if conflicts:
        lineage = clause(
            "VIOLATION",
            "target effect events contain conflicting route-instance lineage",
            evidence={"conflicting_sequences": conflicts, "installed_identity": installation["identity"]},
        )
    elif not complete_kinds:
        lineage = clause(
            "UNKNOWN", "producer-to-writer lineage does not cover every effect stage"
        )
    else:
        lineage = clause(
            "PASS",
            evidence={"installed_identity": installation["identity"]},
        )
    return {
        "oracle": "freshness_lineage",
        "clauses": {"freshness": freshness, "lineage": lineage},
    }
