#!/usr/bin/env python3
"""Evidence Admissibility Gate for Family A route traces."""

from __future__ import annotations

from typing import Any

from scripts.model.runtime_route import (
    AUTHORITY_EVENT_KINDS,
    ZERO_HASH,
    RuntimeRouteInstance,
    RouteModelError,
    event_digest,
)


def evaluate_evidence(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    reasons: list[str] = []
    checks: dict[str, dict[str, Any]] = {}
    if not events:
        return {
            "status": "INADMISSIBLE",
            "checks": {},
            "reasons": ["trace is empty"],
        }

    expected_previous = ZERO_HASH
    chain_errors: list[str] = []
    for index, event in enumerate(events):
        if event.get("sequence") != index:
            chain_errors.append(f"event {index} has a noncontiguous sequence")
        if event.get("previous_hash") != expected_previous:
            chain_errors.append(f"event {index} has an invalid previous hash")
        without_digest = dict(event)
        observed = without_digest.pop("event_hash", None)
        expected = event_digest(without_digest)
        if observed != expected:
            chain_errors.append(f"event {index} has an invalid event hash")
        expected_previous = str(observed)
    checks["hash_chain"] = {
        "status": "PASS" if not chain_errors else "FAIL",
        "errors": chain_errors,
    }
    reasons.extend(chain_errors)

    run_ids = {event.get("run_id") for event in events}
    run_ok = run_ids == {plan.get("run_id")}
    checks["run_identity"] = {"status": "PASS" if run_ok else "FAIL"}
    if not run_ok:
        reasons.append("trace run identity differs from the plan")

    bounded = (
        events[0].get("kind") == "collection_started"
        and events[-1].get("kind") == "collection_stopped"
    )
    checks["collection_bounds"] = {"status": "PASS" if bounded else "FAIL"}
    if not bounded:
        reasons.append("explicit collection bounds are missing")

    observed_kinds = {event.get("kind") for event in events}
    required = set(plan.get("required_event_kinds", []))
    missing = sorted(required - observed_kinds)
    checks["required_events"] = {
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }
    if missing:
        reasons.append("required event kinds are missing: " + ", ".join(missing))

    attestations = [
        event for event in events if event.get("kind") == "environment_attested"
    ]
    environment_ok = (
        len(attestations) == 1
        and attestations[0].get("sequence") == 1
        and attestations[0].get("execution_environment")
        == plan.get("execution_environment")
    )
    checks["execution_environment"] = {
        "status": "PASS" if environment_ok else "FAIL",
        "attestation_count": len(attestations),
        "attestation_sequence": (
            attestations[0].get("sequence") if len(attestations) == 1 else None
        ),
    }
    if not environment_ok:
        reasons.append(
            "trace execution-environment attestation is missing, misplaced, duplicated, or differs from the plan"
        )

    gaps = [event["sequence"] for event in events if event.get("kind") == "collector_gap"]
    checks["critical_window_coverage"] = {
        "status": "PASS" if not gaps else "FAIL",
        "gap_sequences": gaps,
    }
    if gaps:
        reasons.append("collector gap intersects the recorded run")

    identity_errors: list[str] = []
    authority_events = [
        event for event in events if event.get("kind") in AUTHORITY_EVENT_KINDS
    ]
    for event in authority_events:
        try:
            RuntimeRouteInstance.from_event(event)
        except RouteModelError as exc:
            identity_errors.append(f"event {event['sequence']}: {exc}")
    checks["route_identity"] = {
        "status": "PASS" if not identity_errors else "FAIL",
        "errors": identity_errors,
    }
    reasons.extend(identity_errors)

    domains = {event.get("source_domain") for event in authority_events}
    unmapped = [
        event["sequence"]
        for event in authority_events
        if len(domains) > 1 and not event.get("clock_bridge_id")
    ]
    checks["clock_mapping"] = {
        "status": "PASS" if not unmapped else "FAIL",
        "domains": sorted(str(domain) for domain in domains),
        "unmapped_sequences": unmapped,
    }
    if unmapped:
        reasons.append("mixed critical time domains lack clock-bridge identity")

    return {
        "status": "ADMISSIBLE" if not reasons else "INADMISSIBLE",
        "checks": checks,
        "reasons": reasons,
    }
