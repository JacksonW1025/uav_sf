#!/usr/bin/env python3
"""Verify that a run leaves no external authority and reaches a safe terminal state."""

from __future__ import annotations

from typing import Any


EXTERNAL_ROUTES = {"legacy_offboard", "dynamic_external_mode", "mode_executor"}


def evaluate_cleanup(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    active: dict[str, set[str]] = {route: set() for route in EXTERNAL_ROUTES}
    current_route: str | None = None
    for event in sorted(events, key=lambda value: (value["timestamp_ns"], value["sequence"])):
        route = event.get("route")
        activation = event.get("activation_id")
        if event["kind"] == "activation" and route in EXTERNAL_ROUTES and activation:
            active[str(route)].add(str(activation))
            current_route = str(route)
        elif event["kind"] == "revocation" and route in EXTERNAL_ROUTES:
            if activation:
                active[str(route)].discard(str(activation))
            else:
                active[str(route)].clear()
        elif event["kind"] == "activation" and route:
            current_route = str(route)
    remaining = {route: sorted(values) for route, values in active.items() if values}
    terminal = next(
        (event for event in reversed(events) if event["kind"] == "terminal_state"),
        None,
    )
    cleanup = plan["cleanup"]
    reasons: list[str] = []
    if not events or events[-1]["kind"] != "collection_stopped":
        reasons.append("collector is not closed")
    if remaining:
        reasons.append("external route activation remains registered")
    if current_route not in cleanup["safe_terminal_routes"]:
        reasons.append("terminal route is not an allowed safe internal route")
    if terminal is None:
        reasons.append("terminal state evidence is missing")
    else:
        if cleanup["require_landed"] and terminal.get("landed") is not True:
            reasons.append("landing evidence is missing")
        if cleanup["require_disarmed"] and terminal.get("disarmed") is not True:
            reasons.append("disarm evidence is missing")
    return {
        "status": "PASS" if not reasons else "INCOMPLETE",
        "reasons": reasons,
        "remaining_external_activations": remaining,
        "terminal_route": current_route,
    }
