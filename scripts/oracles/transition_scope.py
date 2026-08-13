"""Select and bound one matching transition request for post-hoc replay."""

from __future__ import annotations

from typing import Any


def matching_transition_requests(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> list[dict[str, Any]]:
    transition = plan["transition"]
    return sorted(
        (
            event
            for event in events
            if event["kind"] == "transition_requested"
            and event.get("source_route") == transition["source_route"]
            and event.get("target_route") == transition["target_route"]
        ),
        key=lambda event: (int(event["timestamp_ns"]), int(event["sequence"])),
    )


def selected_transition_request(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any] | None:
    requests = matching_transition_requests(events, plan)
    selected = plan.get("_analysis_transition_sequence")
    if selected is None:
        return requests[0] if requests else None
    return next(
        (event for event in requests if int(event["sequence"]) == int(selected)),
        None,
    )


def transition_window_end_ns(
    events: list[dict[str, Any]], plan: dict[str, Any], request: dict[str, Any]
) -> int:
    later = [
        int(candidate["timestamp_ns"])
        for candidate in matching_transition_requests(events, plan)
        if int(candidate["timestamp_ns"]) > int(request["timestamp_ns"])
    ]
    if later:
        return min(later) - 1
    return max(int(event["timestamp_ns"]) for event in events)
