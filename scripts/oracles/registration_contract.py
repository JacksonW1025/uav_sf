#!/usr/bin/env python3
"""Registration and activation-rejection obligations for Family A."""

from __future__ import annotations

from typing import Any

from scripts.oracles.common import clause


def evaluate_registration_contract(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    transition = plan["transition"]
    registration_rejections = [
        event
        for event in events
        if event["kind"] == "registration" and int(event.get("result_code", -1)) == 2
    ]
    if transition["registration_rejection_expected"]:
        registration = (
            clause(
                "PASS",
                evidence={
                    "rejection_sequences": [event["sequence"] for event in registration_rejections]
                },
            )
            if registration_rejections
            else clause("VIOLATION", "expected registration rejection is missing")
        )
    elif registration_rejections:
        registration = clause(
            "VIOLATION",
            "an unexpected registration rejection was observed",
            evidence={
                "rejection_sequences": [event["sequence"] for event in registration_rejections]
            },
        )
    else:
        registration = clause("NOT_APPLICABLE", "registration rejection is not expected")

    target_activations = [
        event
        for event in events
        if event["kind"] == "activation"
        and event.get("route") == transition["target_route"]
    ]
    rejection_faults = [
        event
        for event in events
        if event["kind"] == "fault_detected"
        and (
            "reject" in str(event.get("reason", "")).lower()
            or int(event.get("result_code", -1)) == 2
        )
    ]
    if transition["activation_rejection_expected"]:
        if target_activations:
            activation = clause(
                "VIOLATION",
                "target activated despite the expected rejection",
                evidence={
                    "activation_sequences": [event["sequence"] for event in target_activations]
                },
            )
        elif rejection_faults:
            activation = clause(
                "PASS",
                evidence={
                    "rejection_sequences": [event["sequence"] for event in rejection_faults]
                },
            )
        else:
            activation = clause("VIOLATION", "explicit activation rejection evidence is missing")
    else:
        activation = clause("NOT_APPLICABLE", "activation rejection is not expected")
    return {
        "oracle": "registration_contract",
        "clauses": {
            "registration_rejection": registration,
            "activation_rejection": activation,
        },
    }
