#!/usr/bin/env python3
"""Summarize one P2 process-loss or P3 channel-decoupling route experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _last(events: list[dict[str, Any]], event_type: str, epoch: int | None) -> float | None:
    values = [
        float(event["timestamp"])
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and event.get("event_type") == event_type
        and (epoch is None or event.get("route_epoch_id") == epoch)
    ]
    return max(values, default=None)


def _first_after(
    events: list[dict[str, Any]], event_type: str, epoch: int | None, threshold_us: float
) -> float | None:
    values = [
        float(event["timestamp"])
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and event.get("event_type") == event_type
        and float(event["timestamp"]) >= threshold_us
        and (epoch is None or event.get("route_epoch_id") == epoch)
    ]
    return min(values, default=None)


def _px4_interval(ros_ns: int, bridge: dict[str, Any]) -> dict[str, float] | None:
    if bridge.get("status") not in {"VALID", "DEGRADED"}:
        return None
    rate = float(bridge["rate_ratio"])
    midpoint = float(bridge["reference_px4_us"]) + (
        (ros_ns - int(bridge["reference_ros_ns"])) / rate / 1000.0
    )
    radius = float(bridge["uncertainty_ns"]) / rate / 1000.0
    return {
        "lower_us": midpoint - radius,
        "midpoint_us": midpoint,
        "upper_us": midpoint + radius,
    }


def summarize(
    monitor: dict[str, Any],
    events: list[dict[str, Any]],
    bridge: dict[str, Any],
    oracle: dict[str, Any],
) -> dict[str, Any]:
    source_mode = monitor.get("source_mode")
    fault = monitor.get("fault")
    reference_ros_ns = (
        int(fault["ros_time_ns"])
        if isinstance(fault, dict)
        else int(monitor["experiment_window_ros_time_ns"])
    )
    fault_interval = (
        _px4_interval(reference_ros_ns, bridge)
        if isinstance(fault, dict)
        else None
    )
    reference_interval = _px4_interval(reference_ros_ns, bridge)
    reference_us = (
        float(reference_interval["midpoint_us"])
        if reference_interval is not None
        else min(
            (
                float(event["timestamp"])
                for event in events
                if event.get("timestamp_domain") == "ulog_us"
            ),
            default=0.0,
        )
    )
    epoch_events = [
        event
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and event.get("event_type") == "route_epoch_changed"
    ]
    source_candidates = [
        event
        for event in epoch_events
        if event.get("declared_mode") == source_mode and float(event["timestamp"]) <= reference_us
    ]
    source_event = max(source_candidates, key=lambda event: float(event["timestamp"]), default=None)
    source_epoch = source_event.get("route_epoch_id") if source_event else None

    fallback_nav_state = monitor.get("fallback_nav_state")
    fallback_candidates = [
        event
        for event in epoch_events
        if float(event["timestamp"]) >= reference_us
        and (fallback_nav_state is None or event.get("declared_mode") == fallback_nav_state)
    ]
    fallback_event = min(
        fallback_candidates, key=lambda event: float(event["timestamp"]), default=None
    )
    fallback_epoch = fallback_event.get("route_epoch_id") if fallback_event else None
    fallback_us = float(fallback_event["timestamp"]) if fallback_event else reference_us

    producer_before_fault = [
        event
        for event in events
        if event.get("timestamp_domain") == "ros_node_ns"
        and event.get("event_type") == "producer_still_publishing"
        and (
            not isinstance(fault, dict)
            or float(event["timestamp"]) <= float(fault["ros_time_ns"])
        )
    ]
    last_producer_ros_ns = max(
        (float(event["timestamp"]) for event in producer_before_fault), default=None
    )
    post_revocation_consumption = sum(
        1
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and event.get("route_epoch_id") == source_epoch
        and event.get("event_type") == "px4_setpoint_consumed"
        and float(event["timestamp"]) > fallback_us
    )
    post_revocation_writer = sum(
        1
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and event.get("route_epoch_id") == source_epoch
        and event.get("event_type") == "actuator_output_published"
        and float(event["timestamp"]) > fallback_us
    )

    if monitor["experiment_kind"] == "p2":
        expected_fallback = True
        behavior_matches = bool(monitor.get("automatic_fallback_observed"))
    else:
        expected_fallback = not bool(monitor["heartbeat_or_health_enabled"])
        behavior_matches = bool(monitor.get("automatic_fallback_observed")) == expected_fallback
    evidence_complete = (
        monitor.get("status") == "PASS"
        and bridge.get("status") == "VALID"
        and source_epoch is not None
    )
    verdict = "PASS" if evidence_complete and behavior_matches else "FAIL"
    reasons: list[str] = []
    if monitor.get("status") != "PASS":
        reasons.append("flight_monitor_failed")
    if bridge.get("status") != "VALID":
        reasons.append("clock_bridge_not_valid")
    if source_epoch is None:
        reasons.append("source_epoch_not_identified")
    if not behavior_matches:
        reasons.append("observed_fallback_behavior_did_not_match_preregistered_expectation")

    return {
        "schema_version": "1.0",
        "experiment_kind": monitor["experiment_kind"],
        "object": monitor["object"],
        "fault_class": monitor.get("fault_class"),
        "heartbeat_or_health_enabled": monitor["heartbeat_or_health_enabled"],
        "setpoint_enabled": monitor["setpoint_enabled"],
        "verdict": verdict,
        "reasons": reasons,
        "clock_bridge": {
            "clock_bridge_id": bridge.get("clock_bridge_id"),
            "status": bridge.get("status"),
            "uncertainty_ns": bridge.get("uncertainty_ns"),
            "fault_px4_time_interval": fault_interval,
        },
        "source_route": {
            "mode": source_mode,
            "route_epoch_id": source_epoch,
            "last_producer_heartbeat_ros_ns": (
                last_producer_ros_ns if monitor["object"] == "offboard" else None
            ),
            "producer_heartbeat_measurement_status": (
                "AVAILABLE"
                if monitor["object"] == "offboard"
                else "UNKNOWN_EXTERNAL_HEALTH_REPLY_NOT_LOGGED"
            ),
            "last_producer_setpoint_ros_ns": last_producer_ros_ns,
            "last_px4_consumption_us": _last(events, "px4_setpoint_consumed", source_epoch),
            "last_allocator_event_us": _last(events, "allocator_input_published", source_epoch),
            "last_writer_event_us": _last(events, "actuator_output_published", source_epoch),
        },
        "failure_and_fallback": {
            "expected_fallback": expected_fallback,
            "automatic_fallback_observed": monitor.get("automatic_fallback_observed"),
            "detection_latency_ms": monitor.get("failure_detection_latency_ms"),
            "fallback_nav_state": fallback_nav_state,
            "fallback_route_epoch_id": fallback_epoch,
            "fallback_epoch_started_us": fallback_us if fallback_event else None,
            "first_fallback_consumption_us": _first_after(
                events, "px4_setpoint_consumed", fallback_epoch, fallback_us
            ),
            "first_fallback_allocator_event_us": _first_after(
                events, "allocator_input_published", fallback_epoch, fallback_us
            ),
            "first_fallback_writer_event_us": _first_after(
                events, "actuator_output_published", fallback_epoch, fallback_us
            ),
            "post_revocation_old_epoch_consumption_count": post_revocation_consumption,
            "post_revocation_old_epoch_writer_count": post_revocation_writer,
        },
        "physical_recovery": monitor["physical_recovery"],
        "route_oracle_version": oracle.get("route_oracle_version"),
        "route_oracle_clauses": {
            name: clause.get("status") for name, clause in oracle.get("clauses", {}).items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monitor-result", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--clock-bridge", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(
        json.loads(args.monitor_result.read_text(encoding="utf-8")),
        [
            json.loads(line)
            for line in args.trace.read_text(encoding="utf-8").splitlines()
            if line
        ],
        json.loads(args.clock_bridge.read_text(encoding="utf-8")),
        json.loads(args.oracle.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": result["verdict"], "output": str(args.output)}))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
