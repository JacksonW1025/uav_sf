"""Shared clause and complete-route installation logic."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from scripts.model.runtime_route import RuntimeRouteInstance, RouteModelError


STATUSES = {"PASS", "VIOLATION", "UNKNOWN", "NOT_APPLICABLE"}
INSTALLATION_KINDS = (
    "activation",
    "command_consumed",
    "controller_output",
    "allocator_output",
    "actuator_write",
)


def clause(
    status: str, *reasons: str, evidence: dict[str, Any] | None = None
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"invalid clause status: {status}")
    return {
        "status": status,
        "reasons": list(reasons),
        "evidence": evidence or {},
    }


def collection_covers(events: Iterable[dict[str, Any]], deadline_ns: int) -> bool:
    return any(
        event["kind"] == "collection_stopped"
        and int(event["timestamp_ns"]) >= deadline_ns
        for event in events
    )


def complete_installation(
    events: list[dict[str, Any]],
    *,
    route: str,
    anchor_ns: int,
    deadline_ns: int,
) -> dict[str, Any]:
    candidates = [
        event
        for event in sorted(events, key=lambda value: (value["timestamp_ns"], value["sequence"]))
        if event.get("route") == route
        and event["kind"] in INSTALLATION_KINDS
        and anchor_ns <= int(event["timestamp_ns"]) <= deadline_ns
    ]
    identities: list[RuntimeRouteInstance] = []
    for event in candidates:
        try:
            identity = RuntimeRouteInstance.from_event(event)
        except RouteModelError:
            continue
        if identity not in identities:
            identities.append(identity)

    best: dict[str, Any] | None = None
    for identity in identities:
        selected: dict[str, dict[str, Any]] = {}
        cursor = anchor_ns
        for kind in INSTALLATION_KINDS:
            match = next(
                (
                    event
                    for event in candidates
                    if event["kind"] == kind
                    and int(event["timestamp_ns"]) >= cursor
                    and identity.matches(event)
                ),
                None,
            )
            if match is None:
                break
            selected[kind] = match
            cursor = int(match["timestamp_ns"])
        if len(selected) == len(INSTALLATION_KINDS):
            result = {
                "complete": True,
                "identity": asdict(identity),
                "events": {
                    kind: {
                        "sequence": event["sequence"],
                        "timestamp_ns": event["timestamp_ns"],
                    }
                    for kind, event in selected.items()
                },
                "completed_at_ns": cursor,
            }
            if best is None or cursor < int(best["completed_at_ns"]):
                best = result
    if best is not None:
        return best
    observed = sorted({str(event["kind"]) for event in candidates})
    return {
        "complete": False,
        "observed_kinds": observed,
        "missing_kinds": [kind for kind in INSTALLATION_KINDS if kind not in observed],
        "deadline_covered": collection_covers(events, deadline_ns),
    }


def installation_clause(
    installation: dict[str, Any], *, label: str
) -> dict[str, Any]:
    if installation["complete"]:
        return clause("PASS", evidence=installation)
    reason = f"{label} route was not completely installed within its deadline"
    return clause(
        "VIOLATION" if installation["deadline_covered"] else "UNKNOWN",
        reason,
        evidence=installation,
    )
