#!/usr/bin/env python3
"""Route Oracle v0 for route-replacing authority transitions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tracing.actuator_writer_collector import summarize as summarize_writers


RESULT_SCHEMA = json.loads(
    (ROOT / "data" / "schemas" / "route_oracle_result.schema.json").read_text(encoding="utf-8")
)
EXTERNAL_MODES = {14, *range(23, 31)}


def _clause(
    status: str,
    metrics: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "metrics": metrics or {},
        "evidence": evidence or [],
        "reasons": reasons or [],
    }


def _mode_transition(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    previous: Any = None
    initialized = False
    changes: list[dict[str, Any]] = []
    for event in events:
        if event.get("timestamp_domain") != "ulog_us" or event.get("event_type") != "vehicle_status":
            continue
        mode = event.get("declared_mode")
        if initialized and mode != previous:
            changes.append(
                {
                    "timestamp_us": float(event["timestamp"]),
                    "source_mode": previous,
                    "target_mode": mode,
                    "timestamp_domain": "ulog_us",
                }
            )
        previous = mode
        initialized = True
    for change in changes:
        if change["source_mode"] in EXTERNAL_MODES and change["target_mode"] not in EXTERNAL_MODES:
            return change
    return changes[0] if changes else None


def _valid_bridge(bridge: dict[str, Any] | None) -> bool:
    if bridge is None:
        return False
    required = {"clock_bridge_id", "offset", "uncertainty", "validity_interval"}
    return (
        required <= set(bridge)
        and isinstance(bridge["clock_bridge_id"], str)
        and isinstance(bridge["offset"], (int, float))
        and isinstance(bridge["uncertainty"], (int, float))
        and float(bridge["uncertainty"]) >= 0
        and isinstance(bridge["validity_interval"], list)
        and len(bridge["validity_interval"]) == 2
    )


def _px4_time(event: dict[str, Any], bridge: dict[str, Any] | None) -> float | None:
    domain = event.get("timestamp_domain")
    timestamp = float(event["timestamp"])
    if domain in {"ulog_us", "px4_boot_us", "px4_uorb_us"}:
        return timestamp
    if domain == "ros_node_ns" and _valid_bridge(bridge):
        return (timestamp - float(bridge["offset"])) / 1000.0
    return None


def _events_with_mode(
    events: Iterable[dict[str, Any]], mode: Any, event_type: str | None = None
) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if event.get("declared_mode") == mode
        and (event_type is None or event.get("event_type") == event_type)
    ]


def evaluate(
    events: list[dict[str, Any]],
    writer_summary: dict[str, Any],
    clock_bridge: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = str(events[0].get("run_id", "unknown")) if events else "unknown"
    transition = _mode_transition(events)
    if transition is None:
        clauses = {
            name: _clause("NOT_APPLICABLE", reasons=["no declared mode transition was observed"])
            for name in ("revocation", "installation", "exclusivity", "continuity", "recovery")
        }
        return {
            "schema_version": "1.0",
            "route_oracle_version": "0.1",
            "run_id": run_id,
            "status": "NOT_APPLICABLE",
            "transition": None,
            "clock_bridge": clock_bridge,
            "clauses": clauses,
        }

    exit_time = float(transition["timestamp_us"])
    source_mode = transition["source_mode"]
    target_mode = transition["target_mode"]
    old_consumptions = [
        event
        for event in _events_with_mode(events, source_mode, "px4_setpoint_consumed")
        if event.get("timestamp_domain") == "ulog_us"
        and float(event["timestamp"]) <= exit_time
    ]
    old_writers = [
        event
        for event in _events_with_mode(events, source_mode, "actuator_output_published")
        if event.get("timestamp_domain") == "ulog_us"
        and float(event["timestamp"]) <= exit_time
    ]
    old_producers = _events_with_mode(events, source_mode, "producer_still_publishing")

    comparable_producers = [
        (event, timestamp)
        for event in old_producers
        if (timestamp := _px4_time(event, clock_bridge)) is not None
    ]
    last_consume_event = max(
        old_consumptions, key=lambda event: float(event["timestamp"]), default=None
    )
    last_consume = (
        float(last_consume_event["timestamp"])
        if last_consume_event is not None
        else None
    )
    old_consume_epoch = (
        last_consume_event.get("route_epoch_id")
        if last_consume_event is not None
        else None
    )
    last_writer_event = max(
        old_writers, key=lambda event: float(event["timestamp"]), default=None
    )
    last_writer = (
        float(last_writer_event["timestamp"]) if last_writer_event is not None else None
    )
    old_writer_epoch = (
        last_writer_event.get("route_epoch_id") if last_writer_event is not None else None
    )
    last_producer = max((timestamp for _, timestamp in comparable_producers), default=None)
    post_consumptions = (
        [
            event
            for event in events
            if event.get("event_type") == "px4_setpoint_consumed"
            and event.get("timestamp_domain") == "ulog_us"
            and float(event["timestamp"]) > exit_time
            and event.get("route_epoch_id") == old_consume_epoch
        ]
        if old_consume_epoch is not None
        else []
    )
    post_writers = (
        [
            event
            for event in events
            if event.get("event_type") == "actuator_output_published"
            and event.get("timestamp_domain") == "ulog_us"
            and float(event["timestamp"]) > exit_time
            and event.get("route_epoch_id") == old_writer_epoch
        ]
        if old_writer_epoch is not None
        else []
    )
    influence_times = [value for value in (last_consume, last_writer) if value is not None]
    revocation_latency_ms = (
        (max(influence_times) - exit_time) / 1000.0 if influence_times else None
    )
    revocation_metrics = {
        "declared_route_exit_us": exit_time,
        "last_producer_publish_us": last_producer,
        "last_old_route_consumption_us": last_consume,
        "last_old_writer_event_us": last_writer,
        "revocation_latency_ms": revocation_latency_ms,
        "post_revocation_consumption_count": (
            len(post_consumptions) if old_consume_epoch is not None else None
        ),
        "post_revocation_writer_count": (
            len(post_writers) if old_writer_epoch is not None else None
        ),
    }
    revocation_reasons: list[str] = []
    if old_producers and not comparable_producers:
        revocation_reasons.append("producer evidence is cross-domain and has no valid clock bridge")
    if not old_consumptions:
        revocation_reasons.append("no source-route consumption evidence")
    elif old_consume_epoch is None:
        revocation_reasons.append(
            "old-route consumption events lack route_epoch_id; a later activation of the same mode cannot be attributed to the old route"
        )
    if not old_writers:
        revocation_reasons.append("no source-route writer evidence")
    elif old_writer_epoch is None:
        revocation_reasons.append(
            "old-route writer events lack route_epoch_id; a shared final writer cannot be attributed to one route"
        )
    if (old_consume_epoch is not None and post_consumptions) or (
        old_writer_epoch is not None and post_writers
    ):
        revocation = _clause(
            "VIOLATION",
            revocation_metrics,
            reasons=["source-route influence persisted after declared route exit", *revocation_reasons],
        )
    elif revocation_reasons:
        revocation = _clause("UNKNOWN", revocation_metrics, reasons=revocation_reasons)
    else:
        revocation = _clause("PASS", revocation_metrics)

    after = [
        event
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and float(event["timestamp"]) >= exit_time
        and event.get("declared_mode") == target_mode
    ]
    target_declared = any(event.get("event_type") == "vehicle_status" for event in after)
    target_consumptions = [
        event for event in after if event.get("event_type") == "px4_setpoint_consumed"
    ]
    target_allocators = [
        event for event in after if event.get("event_type") == "allocator_input_published"
    ]
    target_writers = [
        event for event in after if event.get("event_type") == "actuator_output_published"
    ]
    configured = any(event.get("setpoint_level") != "unknown" for event in after)
    modules = any(event.get("enabled_modules") for event in after)
    registration_required = target_mode in EXTERNAL_MODES and target_mode != 14
    registered = any(
        isinstance(event.get("registration_state"), dict)
        and event["registration_state"].get("registered")
        for event in events
    )
    installation_checks = {
        "declared_mode": target_declared,
        "registration_or_activation": registered if registration_required else True,
        "setpoint_configuration": configured,
        "fresh_consumption": bool(target_consumptions),
        "enabled_modules": modules,
        "allocator_input": bool(target_allocators),
        "final_writer": bool(target_writers),
    }
    missing_installation = [name for name, present in installation_checks.items() if not present]
    installation = _clause(
        "PASS" if not missing_installation else "UNKNOWN",
        {
            "checks": installation_checks,
            "first_target_consumption_us": (
                float(target_consumptions[0]["timestamp"]) if target_consumptions else None
            ),
            "first_target_writer_us": float(target_writers[0]["timestamp"]) if target_writers else None,
        },
        reasons=[f"missing target-route evidence: {name}" for name in missing_installation],
    )

    writer_status = writer_summary.get("status")
    if writer_status == "EXCLUSIVE":
        exclusivity_status = "PASS"
        exclusivity_reasons: list[str] = []
    elif writer_status == "COMPETING_WRITERS":
        exclusivity_status = "VIOLATION"
        exclusivity_reasons = ["multiple actuator writers occurred in an exclusivity window"]
    else:
        exclusivity_status = "UNKNOWN"
        exclusivity_reasons = [f"writer coverage status is {writer_status}"]
    exclusivity = _clause(
        exclusivity_status,
        {
            "candidate_writers": writer_summary.get("candidate_writers", []),
            "observed_writers": writer_summary.get("observed_writers", []),
            "uninstrumented_candidates": writer_summary.get("uninstrumented_candidates", []),
            "sequence_gap_count": len(writer_summary.get("sequence_gaps", [])),
            "competing_window_count": len(writer_summary.get("competing_windows", [])),
            "observation_hole_count": len(writer_summary.get("observation_holes", [])),
        },
        reasons=exclusivity_reasons,
    )

    all_writer_times = sorted(
        float(event["timestamp"])
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and event.get("event_type") == "actuator_output_published"
    )
    before = [timestamp for timestamp in all_writer_times if timestamp <= exit_time]
    after_writer_times = [timestamp for timestamp in all_writer_times if timestamp >= exit_time]
    last_old_influence = before[-1] if before else None
    first_target_influence = after_writer_times[0] if after_writer_times else None
    gap_ms = (
        (first_target_influence - last_old_influence) / 1000.0
        if last_old_influence is not None and first_target_influence is not None
        else None
    )
    expected_period_ms = float(writer_summary.get("expected_period_ms", 0.0))
    allowed_gap_ms = max(20.0, 3.0 * expected_period_ms)
    if writer_status != "EXCLUSIVE" or gap_ms is None:
        continuity_status = "UNKNOWN"
        continuity_reasons = ["continuous, fully covered writer evidence is unavailable"]
    elif gap_ms > allowed_gap_ms:
        continuity_status = "VIOLATION"
        continuity_reasons = ["maximum no-owner window exceeds the observation contract"]
    else:
        continuity_status = "PASS"
        continuity_reasons = []
    continuity = _clause(
        continuity_status,
        {
            "last_old_valid_influence_us": last_old_influence,
            "first_target_valid_influence_us": first_target_influence,
            "maximum_unowned_window_ms": gap_ms,
            "allowed_gap_ms": allowed_gap_ms,
            "valid_fallback_output": bool(target_writers),
        },
        reasons=continuity_reasons,
    )

    fallback_selected = target_mode not in EXTERNAL_MODES
    producer_stopped = (
        bool(comparable_producers) and old_consume_epoch is not None and not post_consumptions
    )
    recovery_checks = {
        "fallback_selected": fallback_selected,
        "fallback_modules_installed": modules,
        "fallback_writer_active": bool(target_writers),
        "old_consumer_stopped": (
            not post_consumptions if old_consume_epoch is not None else None
        ),
        "old_writer_stopped": (
            not post_writers if old_writer_epoch is not None else None
        ),
        "old_producer_stopped": producer_stopped,
    }
    missing_recovery = [name for name, present in recovery_checks.items() if not present]
    if not fallback_selected:
        recovery_status = "NOT_APPLICABLE"
        recovery_reasons = ["transition target is not an internal fallback route"]
    elif missing_recovery:
        recovery_status = "UNKNOWN"
        recovery_reasons = [f"missing recovery evidence: {name}" for name in missing_recovery]
    else:
        recovery_status = "PASS"
        recovery_reasons = []
    recovery = _clause(
        recovery_status,
        {"checks": recovery_checks, "automatic_old_route_reentry_observed": False},
        reasons=recovery_reasons,
    )

    clauses = {
        "revocation": revocation,
        "installation": installation,
        "exclusivity": exclusivity,
        "continuity": continuity,
        "recovery": recovery,
    }
    statuses = {clause["status"] for clause in clauses.values()}
    if "VIOLATION" in statuses:
        overall = "VIOLATION"
    elif statuses <= {"PASS", "NOT_APPLICABLE"}:
        overall = "PASS"
    else:
        overall = "UNKNOWN"

    return {
        "schema_version": "1.0",
        "route_oracle_version": "0.1",
        "run_id": run_id,
        "status": overall,
        "transition": transition,
        "clock_bridge": clock_bridge,
        "clauses": clauses,
    }


def run(trace: Path, clock_bridge: dict[str, Any] | None = None) -> dict[str, Any]:
    events = [
        json.loads(line)
        for line in trace.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result = evaluate(events, summarize_writers(trace), clock_bridge)
    Draft202012Validator(RESULT_SCHEMA).validate(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clock-bridge", type=Path)
    args = parser.parse_args()
    bridge = (
        json.loads(args.clock_bridge.read_text(encoding="utf-8"))
        if args.clock_bridge is not None
        else None
    )
    result = run(args.trace, bridge)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
