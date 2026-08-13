#!/usr/bin/env python3
"""Route Conformance Oracle: revocation, installation, exclusivity, continuity."""

from __future__ import annotations

from typing import Any

from scripts.oracles.common import (
    clause,
    collection_covers,
    complete_installation,
    installation_clause,
)
from scripts.model.runtime_route import RouteModelError, RuntimeRouteInstance


def _transition(events: list[dict[str, Any]], source: str, target: str) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in events
            if event["kind"] == "transition_requested"
            and event.get("source_route") == source
            and event.get("target_route") == target
        ),
        None,
    )


def evaluate_route_conformance(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    transition = plan["transition"]
    if not transition["target_activation_expected"]:
        not_applicable = clause(
            "NOT_APPLICABLE", "the preregistered target activation is expected to be rejected"
        )
        return {
            "oracle": "route_conformance",
            "clauses": {
                "revocation": not_applicable,
                "installation": not_applicable,
                "exclusivity": not_applicable,
                "continuity": not_applicable,
                "ownership": not_applicable,
                "reentry_identity": not_applicable,
            },
        }
    thresholds = plan["thresholds"]
    source = transition["source_route"]
    target = transition["target_route"]
    request = _transition(events, source, target)
    if request is None:
        unknown = clause("UNKNOWN", "matching transition request is missing")
        return {
            "oracle": "route_conformance",
            "clauses": {
                "revocation": unknown,
                "installation": unknown,
                "exclusivity": unknown,
                "continuity": unknown,
                "ownership": unknown,
                "reentry_identity": unknown,
            },
        }

    anchor = int(request["timestamp_ns"])
    revoke_deadline = anchor + int(thresholds["revocation_deadline_ns"])
    install_deadline = anchor + int(thresholds["installation_deadline_ns"])
    installation = complete_installation(
        events, route=target, anchor_ns=anchor, deadline_ns=install_deadline
    )
    install_result = installation_clause(installation, label="target")

    target_identity: RuntimeRouteInstance | None = None
    target_write_ns: int | None = None
    target_end_ns: int | None = None
    if installation["complete"]:
        target_identity = RuntimeRouteInstance(**installation["identity"])
        target_write_ns = int(installation["events"]["actuator_write"]["timestamp_ns"])
        target_revocations = sorted(
            (
                event
                for event in events
                if event["kind"] == "revocation"
                and target_identity.matches(event)
                and int(event["timestamp_ns"]) >= target_write_ns
            ),
            key=lambda event: (int(event["timestamp_ns"]), int(event["sequence"])),
        )
        if target_revocations:
            target_end_ns = int(target_revocations[0]["timestamp_ns"])

    all_source_writes = sorted(
        (
            event
            for event in events
            if event["kind"] == "actuator_write" and event.get("route") == source
        ),
        key=lambda event: int(event["timestamp_ns"]),
    )
    source_activations = sorted(
        (
            event
            for event in events
            if event["kind"] == "activation"
            and event.get("route") == source
            and int(event["timestamp_ns"]) <= anchor
        ),
        key=lambda event: (int(event["timestamp_ns"]), int(event["sequence"])),
    )
    source_identity: RuntimeRouteInstance | None = None
    if source_activations:
        try:
            source_identity = RuntimeRouteInstance.from_event(source_activations[-1])
        except RouteModelError:
            source_identity = None
    source_writes = [
        event
        for event in all_source_writes
        if source_identity is not None and source_identity.matches(event)
    ]
    source_writes_during_target = [
        event
        for event in all_source_writes
        if int(event["timestamp_ns"]) >= anchor
        and (target_end_ns is None or int(event["timestamp_ns"]) < target_end_ns)
    ]
    revocations = [
        event
        for event in events
        if event["kind"] == "revocation"
        and event.get("route") == source
        and source_identity is not None
        and source_identity.matches(event)
        and anchor <= int(event["timestamp_ns"]) <= revoke_deadline
    ]
    last_source = max(
        (int(event["timestamp_ns"]) for event in source_writes), default=None
    )
    late_source = [
        event["sequence"]
        for event in source_writes_during_target
        if int(event["timestamp_ns"]) > revoke_deadline
    ]
    first_revocation_ns = (
        int(revocations[0]["timestamp_ns"]) if revocations else None
    )
    post_revocation_source = [
        event["sequence"]
        for event in source_writes_during_target
        if first_revocation_ns is not None
        and int(event["timestamp_ns"]) > first_revocation_ns
    ]
    if source_identity is None:
        revocation_result = clause(
            "UNKNOWN", "the source route instance active at the request is missing"
        )
    elif revocations and not late_source and not post_revocation_source:
        revocation_result = clause(
            "PASS",
            evidence={
                "revocation_sequence": revocations[0]["sequence"],
                "last_source_effect_ns": last_source,
            },
        )
    elif collection_covers(events, revoke_deadline):
        revocation_result = clause(
            "VIOLATION",
            "source route was not completely revoked within its deadline",
            evidence={
                "late_source_sequences": late_source,
                "post_revocation_source_sequences": post_revocation_source,
            },
        )
    else:
        revocation_result = clause(
            "UNKNOWN", "collection does not cover the source revocation deadline"
        )

    overlap = [
        event["sequence"]
        for event in source_writes_during_target
        if target_write_ns is not None and int(event["timestamp_ns"]) >= target_write_ns
    ]
    if target_write_ns is None or not source_writes:
        exclusivity = clause(
            "UNKNOWN", "both source and target actuator-writer evidence are required"
        )
    elif overlap:
        exclusivity = clause(
            "VIOLATION",
            "source actuator effects continued after target installation",
            evidence={"source_sequences": overlap},
        )
    else:
        exclusivity = clause("PASS", evidence={"target_write_ns": target_write_ns})

    last_source_before_target = max(
        (
            int(event["timestamp_ns"])
            for event in source_writes
            if target_write_ns is not None and int(event["timestamp_ns"]) <= target_write_ns
        ),
        default=None,
    )
    if target_write_ns is None or last_source_before_target is None:
        continuity = clause(
            "UNKNOWN", "source-to-target actuator-effect boundary is incomplete"
        )
    else:
        gap = target_write_ns - last_source_before_target
        maximum = int(thresholds["maximum_effect_gap_ns"])
        continuity = clause(
            "PASS" if gap <= maximum else "VIOLATION",
            *(() if gap <= maximum else ("actuator-effect continuity bound was exceeded",)),
            evidence={"effect_gap_ns": gap, "maximum_effect_gap_ns": maximum},
        )

    expected_lifecycle = transition["expected_lifecycle_owner"]
    expected_executor = transition["expected_executor_owner"]
    if not installation["complete"]:
        ownership = clause("UNKNOWN", "target installation identity is incomplete")
    else:
        identity = installation["identity"]
        matches = (
            identity["lifecycle_owner"] == expected_lifecycle
            and identity["executor_owner"] == expected_executor
        )
        ownership = clause(
            "PASS" if matches else "VIOLATION",
            *(() if matches else ("target lifecycle or executor owner is incorrect",)),
            evidence={
                "observed_lifecycle_owner": identity["lifecycle_owner"],
                "observed_executor_owner": identity["executor_owner"],
                "expected_lifecycle_owner": expected_lifecycle,
                "expected_executor_owner": expected_executor,
            },
        )

    activation_count_bounds = plan["strategy"]["timing_bounds_ns"].get(
        "target_activation_count"
    )
    if activation_count_bounds is None:
        reentry_identity = clause(
            "NOT_APPLICABLE", "no repeated-entry identity obligation was preregistered"
        )
    else:
        low, high = map(int, activation_count_bounds)
        requests = sorted(
            (
                event
                for event in events
                if event["kind"] == "transition_requested"
                and event.get("source_route") == source
                and event.get("target_route") == target
            ),
            key=lambda event: (int(event["timestamp_ns"]), int(event["sequence"])),
        )
        installations = [
            complete_installation(
                events,
                route=target,
                anchor_ns=int(candidate["timestamp_ns"]),
                deadline_ns=int(candidate["timestamp_ns"])
                + int(thresholds["installation_deadline_ns"]),
            )
            for candidate in requests
        ]
        complete_identities = [
            RuntimeRouteInstance(**candidate["identity"])
            for candidate in installations
            if candidate["complete"]
        ]
        distinct_identities = set(complete_identities)
        counts_match = (
            low <= len(requests) <= high
            and len(complete_identities) == len(requests)
            and len(distinct_identities) == len(complete_identities)
        )
        reentry_identity = clause(
            "PASS" if counts_match else "VIOLATION",
            *(
                ()
                if counts_match
                else (
                    "each repeated public request must produce one distinct complete route instance",
                )
            ),
            evidence={
                "expected_activation_count": [low, high],
                "request_sequences": [event["sequence"] for event in requests],
                "complete_installation_count": len(complete_identities),
                "distinct_identity_count": len(distinct_identities),
                "route_epochs": [identity.route_epoch for identity in complete_identities],
                "activation_ids": [
                    identity.activation_id for identity in complete_identities
                ],
            },
        )

    return {
        "oracle": "route_conformance",
        "transition_sequence": request["sequence"],
        "clauses": {
            "revocation": revocation_result,
            "installation": install_result,
            "exclusivity": exclusivity,
            "continuity": continuity,
            "ownership": ownership,
            "reentry_identity": reentry_identity,
        },
    }
