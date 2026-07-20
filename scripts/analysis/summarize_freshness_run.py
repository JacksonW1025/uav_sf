#!/usr/bin/env python3
"""Derive one compact pre-revocation freshness observation from raw evidence."""

from __future__ import annotations

import argparse
import bisect
import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable

import yaml


SETPOINT_TOPIC = {
    "TRAJECTORY": "trajectory_setpoint",
    "ATTITUDE": "vehicle_attitude_setpoint",
    "RATE": "vehicle_rates_setpoint",
}


def _load_mapping(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected mapping in {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _ros_to_px4_us(ros_ns: int, bridge: dict[str, Any]) -> float:
    return float(bridge["reference_px4_us"]) + (
        (ros_ns - int(bridge["reference_ros_ns"]))
        / float(bridge["rate_ratio"])
        / 1000.0
    )


def _dataset_rows(ulog: Any, name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dataset in ulog.data_list:
        if dataset.name != name or "timestamp" not in dataset.data:
            continue
        for index, timestamp in enumerate(dataset.data["timestamp"]):
            row = {key: values[index].item() for key, values in dataset.data.items()}
            row["timestamp"] = float(timestamp)
            row["instance"] = dataset.multi_id
            rows.append(row)
    return sorted(rows, key=lambda row: float(row["timestamp"]))


def _between(rows: Iterable[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    return [row for row in rows if start <= float(row["timestamp"]) <= end]


def _last_at_or_before(rows: Iterable[dict[str, Any]], cutoff: float) -> dict[str, Any] | None:
    selected = [row for row in rows if float(row["timestamp"]) <= cutoff]
    return max(selected, key=lambda row: float(row["timestamp"]), default=None)


def _tilt_rad(q: list[float]) -> float:
    if len(q) != 4:
        return math.nan
    _, x, y, _ = q
    return math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * (x * x + y * y))))


def _roll_rad(q: list[float]) -> float:
    if len(q) != 4:
        return math.nan
    w, x, y, z = q
    return math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))


def _vector(row: dict[str, Any], field: str, size: int) -> list[float]:
    return [float(row[f"{field}[{index}]"]) for index in range(size)]


def _nearest_before(rows: list[dict[str, Any]], timestamp: float) -> dict[str, Any] | None:
    timestamps = [float(row["timestamp"]) for row in rows]
    index = bisect.bisect_right(timestamps, timestamp) - 1
    return rows[index] if index >= 0 else None


def _source_epoch(
    events: list[dict[str, Any]], external_mode_id: int, fault_us: float
) -> int | None:
    candidates = [
        event
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and event.get("event_type") == "route_epoch_changed"
        and int(event.get("declared_mode", -1)) == external_mode_id
        and float(event["timestamp"]) <= fault_us
        and event.get("route_epoch_id") is not None
    ]
    event = max(candidates, key=lambda item: float(item["timestamp"]), default=None)
    return int(event["route_epoch_id"]) if event is not None else None


def _first_fallback(
    events: list[dict[str, Any]], external_mode_id: int, fault_us: float
) -> dict[str, Any] | None:
    candidates = [
        event
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and event.get("event_type") == "route_epoch_changed"
        and float(event["timestamp"]) >= fault_us
        and int(event.get("declared_mode", external_mode_id)) != external_mode_id
    ]
    return min(candidates, key=lambda item: float(item["timestamp"]), default=None)


def _last_trace_time(
    events: list[dict[str, Any]], event_type: str, epoch: int | None, cutoff: float
) -> float | None:
    values = [
        float(event["timestamp"])
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and event.get("event_type") == event_type
        and event.get("route_epoch_id") == epoch
        and float(event["timestamp"]) <= cutoff
    ]
    return max(values, default=None)


def _last_external_subject_timestamp(
    events: list[dict[str, Any]],
    setpoint_type: str,
    epoch: int | None,
    cutoff: float,
) -> float | None:
    """Return the receive-time timestamp of the retained external setpoint.

    The locked interface library publishes zero-valued source timestamps, so PX4
    replaces them with HRT at uORB ingress.  The observation-only controller
    event carries that value as ``observation.subject_timestamp`` on every
    subsequent consumption.  Filtering by both route epoch and setpoint topic
    excludes downstream and fallback setpoints that share the same uORB topic.
    """
    values = [
        float(event["observation"]["subject_timestamp"])
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and event.get("event_type") == "px4_setpoint_consumed"
        and event.get("route_epoch_id") == epoch
        and event.get("setpoint_topic") == SETPOINT_TOPIC[setpoint_type]
        and float(event["timestamp"]) <= cutoff
        and isinstance(event.get("observation"), dict)
        and event["observation"].get("subject_timestamp") is not None
        and float(event["observation"]["subject_timestamp"]) > 0
    ]
    return max(values, default=None)


def _health_evidence(
    requests: list[dict[str, Any]],
    replies: list[dict[str, Any]],
    fault_us: float,
    cutoff_us: float,
) -> dict[str, Any]:
    prior_replies = [reply for reply in replies if float(reply["timestamp"]) <= fault_us]
    if not prior_replies:
        return {
            "registration_id": None,
            "health_loss_detection_us": None,
            "alive_through_target": False,
            "request_count": 0,
            "matched_reply_count": 0,
        }
    registration_id = int(prior_replies[-1]["registration_id"])
    mask = 1 << registration_id
    target_requests = _between(requests, fault_us, cutoff_us)
    reply_keys = {
        (int(reply["request_id"]), int(reply["registration_id"]))
        for reply in _between(replies, fault_us, cutoff_us + 400_000.0)
    }
    requests_while_valid = [
        request for request in target_requests if int(request["valid_registrations_mask"]) & mask
    ]
    matched = sum(
        (int(request["request_id"]), registration_id) in reply_keys
        for request in requests_while_valid
    )
    detection = next(
        (
            float(request["timestamp"])
            for request in target_requests
            if not int(request["valid_registrations_mask"]) & mask
        ),
        None,
    )
    alive = (
        bool(requests_while_valid)
        and detection is None
        and matched == len(requests_while_valid)
        and float(requests_while_valid[-1]["timestamp"]) >= cutoff_us - 400_000.0
    )
    return {
        "registration_id": registration_id,
        "health_loss_detection_us": detection,
        "alive_through_target": alive,
        "request_count": len(requests_while_valid),
        "matched_reply_count": matched,
    }


def _physical_metrics(
    positions: list[dict[str, Any]],
    attitudes: list[dict[str, Any]],
    angular_rates: list[dict[str, Any]],
    fault_us: float,
    end_us: float,
) -> dict[str, float | None]:
    position_window = _between(positions, fault_us, end_us)
    attitude_window = _between(attitudes, fault_us, end_us)
    rate_window = _between(angular_rates, fault_us, end_us)
    initial_position = _nearest_before(positions, fault_us)
    initial_altitude = -float(initial_position["z"]) if initial_position is not None else None
    altitude_loss = (
        max(
            0.0,
            initial_altitude - min(-float(row["z"]) for row in position_window),
        )
        if initial_altitude is not None and position_window
        else None
    )
    horizontal_displacement = (
        max(
            math.hypot(
                float(row["x"]) - float(initial_position["x"]),
                float(row["y"]) - float(initial_position["y"]),
            )
            for row in position_window
        )
        if initial_position is not None and position_window
        else None
    )
    maximum_tilt = max(
        (_tilt_rad(_vector(row, "q", 4)) for row in attitude_window), default=None
    )
    maximum_rate = max(
        (math.sqrt(sum(value * value for value in _vector(row, "xyz", 3))) for row in rate_window),
        default=None,
    )
    return {
        "maximum_attitude_excursion_deg": (
            math.degrees(maximum_tilt) if maximum_tilt is not None else None
        ),
        "maximum_angular_rate_excursion_rad_s": maximum_rate,
        "altitude_loss_m": altitude_loss,
        "horizontal_displacement_m": horizontal_displacement,
    }


def _pre_revocation_physical_end(
    fault_type: str, fallback_installed_us: float | None, target_end_us: float
) -> float:
    if fault_type == "TOTAL_PROCESS_STOP" and fallback_installed_us is not None:
        return fallback_installed_us
    return target_end_us


def _baseline_metrics(
    positions: list[dict[str, Any]],
    attitudes: list[dict[str, Any]],
    angular_rates: list[dict[str, Any]],
    fault_us: float,
    duration_s: float,
) -> dict[str, Any]:
    start = fault_us - duration_s * 1_000_000.0
    pos = _between(positions, start, fault_us)
    att = _between(attitudes, start, fault_us)
    rates = _between(angular_rates, start, fault_us)
    altitude = [-float(row["z"]) for row in pos]
    horizontal_speed = [math.hypot(float(row["vx"]), float(row["vy"])) for row in pos]
    rolls = [_roll_rad(_vector(row, "q", 4)) for row in att]
    roll_rates = [float(row["xyz[0]"]) for row in rates]
    return {
        "window_start_us": start,
        "window_end_us": fault_us,
        "position_samples": len(pos),
        "attitude_samples": len(att),
        "angular_rate_samples": len(rates),
        "altitude_span_m": max(altitude) - min(altitude) if altitude else None,
        "median_horizontal_speed_m_s": statistics.median(horizontal_speed) if horizontal_speed else None,
        "median_roll_rad": statistics.median(rolls) if rolls else None,
        "median_roll_rate_rad_s": statistics.median(roll_rates) if roll_rates else None,
    }


def _baseline_complete(
    metrics: dict[str, Any], setpoint_type: str, profile: dict[str, Any]
) -> tuple[bool, list[str]]:
    acceptance = profile.get("acceptance", {}) if isinstance(profile, dict) else {}
    minimum_samples = int(acceptance.get("minimum_samples_per_physical_topic", 20))
    maximum_altitude_span = float(acceptance.get("maximum_pre_fault_altitude_span_m", 1.0))
    reasons: list[str] = []
    for name in ("position_samples", "attitude_samples", "angular_rate_samples"):
        if int(metrics.get(name, 0)) < minimum_samples:
            reasons.append(f"{name}_below_{minimum_samples}")
    altitude_span = metrics.get("altitude_span_m")
    if altitude_span is None or float(altitude_span) > maximum_altitude_span:
        reasons.append("pre_fault_altitude_span_exceeded")
    if setpoint_type == "TRAJECTORY":
        speed = metrics.get("median_horizontal_speed_m_s")
        if speed is None or float(speed) < float(acceptance.get("trajectory_minimum_speed_m_s", 0.1)):
            reasons.append("trajectory_motion_context_not_reached")
    elif setpoint_type == "ATTITUDE":
        roll = metrics.get("median_roll_rad")
        if roll is None or abs(float(roll)) < float(acceptance.get("attitude_minimum_roll_rad", 0.04)):
            reasons.append("attitude_motion_context_not_reached")
    else:
        roll_rate = metrics.get("median_roll_rate_rad_s")
        if roll_rate is None or abs(float(roll_rate)) < float(acceptance.get("rate_minimum_roll_rate_rad_s", 0.03)):
            reasons.append("rate_motion_context_not_reached")
    return not reasons, reasons


def _physical_recovery_time(
    positions: list[dict[str, Any]],
    attitudes: list[dict[str, Any]],
    rates: list[dict[str, Any]],
    fallback_us: float | None,
    end_us: float,
    profile: dict[str, Any],
) -> float | None:
    if fallback_us is None:
        return None
    acceptance = profile.get("acceptance", {}) if isinstance(profile, dict) else {}
    tilt_limit = math.radians(float(acceptance.get("recovery_tilt_deg", 15.0)))
    rate_limit = float(acceptance.get("recovery_rate_rad_s", 0.5))
    vertical_speed_limit = float(acceptance.get("recovery_vertical_speed_m_s", 0.7))
    hold_us = float(acceptance.get("recovery_hold_ms", 500.0)) * 1000.0
    stable_start: float | None = None
    for attitude in _between(attitudes, fallback_us, end_us):
        timestamp = float(attitude["timestamp"])
        rate = _nearest_before(rates, timestamp)
        position = _nearest_before(positions, timestamp)
        stable = (
            rate is not None
            and position is not None
            and _tilt_rad(_vector(attitude, "q", 4)) <= tilt_limit
            and math.sqrt(sum(value * value for value in _vector(rate, "xyz", 3))) <= rate_limit
            and abs(float(position["vz"])) <= vertical_speed_limit
        )
        if stable and stable_start is None:
            stable_start = timestamp
        elif not stable:
            stable_start = None
        if stable_start is not None and timestamp - stable_start >= hold_us:
            return stable_start
    return None


def summarize(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from pyulog import ULog
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("pyulog is required") from exc

    monitor = _load_mapping(args.monitor_result)
    bridge = _load_mapping(args.clock_bridge)
    fault = _load_mapping(args.fault_record)
    profile = _load_mapping(args.profile) if args.profile is not None else {}
    events = _jsonl(args.trace)
    monitor_events = _jsonl(args.monitor_events)
    ulog = ULog(str(args.ulog))
    positions = _dataset_rows(ulog, "vehicle_local_position")
    attitudes = _dataset_rows(ulog, "vehicle_attitude")
    angular_rates = _dataset_rows(ulog, "vehicle_angular_velocity")
    requests = _dataset_rows(ulog, "arming_check_request")
    replies = _dataset_rows(ulog, "arming_check_reply")
    failsafe_flags = _dataset_rows(ulog, "failsafe_flags")
    statuses = _dataset_rows(ulog, "vehicle_status")

    fault_us = _ros_to_px4_us(int(fault["ros_time_ns"]), bridge)
    target_end_ros_ns = int(monitor["target_window_end_ros_time_ns"])
    target_end_us = _ros_to_px4_us(target_end_ros_ns, bridge)
    source_epoch = _source_epoch(events, int(monitor["external_mode_id"]), fault_us)
    fallback_event = (
        _first_fallback(events, int(monitor["external_mode_id"]), fault_us)
        if args.fault_type == "TOTAL_PROCESS_STOP"
        else None
    )
    fallback_installed_us = float(fallback_event["timestamp"]) if fallback_event else None
    cutoff_us = fallback_installed_us if fallback_installed_us is not None else target_end_us

    all_producer_events = [
        event
        for event in events
        if event.get("timestamp_domain") == "ros_node_ns"
        and event.get("event_type") == "producer_still_publishing"
    ]
    producer_events = [
        event for event in all_producer_events if float(event["timestamp"]) <= target_end_ros_ns
    ]
    last_producer_ros_ns = max(
        (int(event["timestamp"]) for event in producer_events), default=None
    )
    last_producer_us = (
        _ros_to_px4_us(last_producer_ros_ns, bridge)
        if last_producer_ros_ns is not None
        else None
    )
    last_receive_us = _last_external_subject_timestamp(
        events, args.setpoint_type, source_epoch, cutoff_us
    )
    last_consumption_us = _last_trace_time(
        events, "px4_setpoint_consumed", source_epoch, cutoff_us
    )
    last_allocator_us = _last_trace_time(
        events, "allocator_input_published", source_epoch, cutoff_us
    )
    last_writer_us = _last_trace_time(
        events, "actuator_output_published", source_epoch, cutoff_us
    )
    health = _health_evidence(requests, replies, fault_us, target_end_us)
    external_mode_mask = 1 << int(monitor["external_mode_id"])
    health_flag = next(
        (
            row
            for row in failsafe_flags
            if fault_us <= float(row["timestamp"]) <= target_end_us
            and int(row.get("mode_req_other", 0)) & external_mode_mask
        ),
        None,
    )
    if health_flag is not None:
        health["health_loss_detection_us"] = float(health_flag["timestamp"])
        health["detection_source"] = "failsafe_flags.mode_req_other_external_mode_bit"
    else:
        health["detection_source"] = (
            "arming_check_request.valid_registrations_mask"
            if health["health_loss_detection_us"] is not None
            else None
        )

    fallback_declared_us = None
    if args.fault_type == "TOTAL_PROCESS_STOP":
        fallback_status = next(
            (
                status
                for status in statuses
                if float(status["timestamp"]) >= fault_us and bool(status.get("failsafe", False))
            ),
            None,
        )
        fallback_declared_us = (
            float(fallback_status["timestamp"]) if fallback_status is not None else fallback_installed_us
        )

    cleanup_transition = next(
        (
            record
            for record in monitor_events
            if record.get("event_type") == "state_transition"
            and record.get("current") == "CLEANUP_LAND"
        ),
        None,
    )
    physical_end_us = (
        _ros_to_px4_us(int(cleanup_transition["ros_time_ns"]), bridge)
        if cleanup_transition is not None
        else target_end_us
    )
    baseline_duration_s = float(
        profile.get("acceptance", {}).get("pre_fault_stable_seconds", 2.0)
        if isinstance(profile.get("acceptance", {}), dict)
        else 2.0
    )
    baseline = _baseline_metrics(
        positions, attitudes, angular_rates, fault_us, baseline_duration_s
    )
    baseline_complete, baseline_reasons = _baseline_complete(
        baseline, args.setpoint_type, profile
    )
    pre_revocation_physical_end_us = _pre_revocation_physical_end(
        args.fault_type, fallback_installed_us, target_end_us
    )
    physical_metrics = _physical_metrics(
        positions,
        attitudes,
        angular_rates,
        fault_us,
        pre_revocation_physical_end_us,
    )
    recovery_physical_metrics = _physical_metrics(
        positions,
        attitudes,
        angular_rates,
        pre_revocation_physical_end_us,
        physical_end_us,
    )
    full_post_fault_physical_metrics = _physical_metrics(
        positions, attitudes, angular_rates, fault_us, physical_end_us
    )
    recovery_us = _physical_recovery_time(
        positions,
        attitudes,
        angular_rates,
        fallback_installed_us,
        physical_end_us,
        profile,
    )

    required_trace = all(
        value is not None
        for value in (source_epoch, last_receive_us, last_consumption_us, last_allocator_us, last_writer_us)
    )
    target_complete = (
        monitor.get("status") == "PASS"
        and required_trace
        and target_end_us >= fault_us
        and (
            fallback_installed_us is not None
            if args.fault_type == "TOTAL_PROCESS_STOP"
            else bool(monitor.get("target_policy_terminated"))
            and bool(monitor.get("external_route_retained_at_window_end"))
            and health["alive_through_target"]
        )
    )
    fallback_complete = (
        fallback_installed_us is not None and physical_end_us > fallback_installed_us
        if args.fault_type == "TOTAL_PROCESS_STOP"
        else False
    )
    channel_stop_observed = any(
        event.get("timestamp_domain") == "ros_node_ns"
        and event.get("event_type") == "freshness_channel_state"
        and "setpoint_enabled=False" in str(event.get("evidence_source", ""))
        and int(event["timestamp"]) >= int(fault["ros_time_ns"])
        for event in events
    )
    producer_stopped = last_producer_ros_ns is not None and (
        args.fault_type == "TOTAL_PROCESS_STOP"
        or channel_stop_observed
    ) and not any(
        int(event["timestamp"]) > target_end_ros_ns for event in all_producer_events
    )
    environment_status = "VALID" if monitor.get("status") == "PASS" else "ENVIRONMENT_FAILURE"
    observation = {
        "schema_version": "1.0",
        "run_id": args.run_id,
        "setpoint_type": args.setpoint_type,
        "fault_type": args.fault_type,
        "producer_stopped": producer_stopped,
        "health_alive_through_target_window": (
            health["alive_through_target"] if args.fault_type == "SETPOINT_ONLY_STALL" else False
        ),
        "external_route_retained_at_window_end": bool(
            monitor.get("external_route_retained_at_window_end")
        ),
        "environment_status": environment_status,
        "clock_bridge_status": bridge.get("status", "UNKNOWN"),
        "windows": {
            "pre_fault_stable": "COMPLETE" if baseline_complete else "INCOMPLETE",
            "pre_revocation_target": "COMPLETE" if target_complete else "INCOMPLETE",
            "fallback": (
                "COMPLETE"
                if fallback_complete
                else "POLICY_TERMINATED"
                if args.fault_type == "SETPOINT_ONLY_STALL" and target_complete
                else "INCOMPLETE"
            ),
        },
        "timestamps_us": {
            "fault_injection": fault_us,
            "producer_last_publish": last_producer_us,
            "px4_last_setpoint_receive": last_receive_us,
            "last_fresh_setpoint": last_receive_us,
            "last_setpoint_consumption": last_consumption_us,
            "last_external_allocator_input": last_allocator_us,
            "last_external_writer_output": last_writer_us,
            "health_loss_detection": (
                health["health_loss_detection_us"]
                if args.fault_type == "TOTAL_PROCESS_STOP"
                else None
            ),
            "fallback_declared": fallback_declared_us,
            "fallback_installed": fallback_installed_us,
            "physical_recovery": recovery_us,
            "target_window_end": target_end_us,
        },
        "physical_metrics": physical_metrics,
        "recovery_physical_metrics": recovery_physical_metrics,
        "full_post_fault_physical_metrics": full_post_fault_physical_metrics,
        "baseline_metrics": baseline,
        "baseline_reasons": baseline_reasons,
        "evidence_quality": {
            "source_route_epoch_id": source_epoch,
            "health": health,
            "physical_window_end_us": physical_end_us,
            "pre_revocation_physical_window_end_us": pre_revocation_physical_end_us,
            "physical_metrics_window": "fault_to_route_revocation_or_bounded_target_end",
            "recovery_physical_metrics_window": (
                "route_revocation_or_bounded_target_end_to_cleanup"
            ),
            "clock_uncertainty_ns": bridge.get("uncertainty_ns"),
            "required_trace_complete": required_trace,
            "px4_receive_time_source": (
                "controller_consumption.observation.subject_timestamp"
                if last_receive_us is not None
                else None
            ),
        },
        "inputs": {
            "ulog": str(args.ulog),
            "route_trace": str(args.trace),
            "monitor_result": str(args.monitor_result),
            "clock_bridge_id": bridge.get("clock_bridge_id"),
            "profile": str(args.profile) if args.profile is not None else None,
        },
    }
    return observation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--setpoint-type", choices=tuple(SETPOINT_TOPIC), required=True)
    parser.add_argument("--fault-type", choices=("TOTAL_PROCESS_STOP", "SETPOINT_ONLY_STALL"), required=True)
    parser.add_argument("--ulog", type=Path, required=True)
    parser.add_argument("--monitor-result", type=Path, required=True)
    parser.add_argument("--monitor-events", type=Path, required=True)
    parser.add_argument("--fault-record", type=Path, required=True)
    parser.add_argument("--clock-bridge", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": args.run_id, "windows": result["windows"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
