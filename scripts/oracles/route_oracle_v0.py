#!/usr/bin/env python3
"""Route Oracle v0 for route transitions and retained-route observations."""

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
ORACLE_VERSION = "0.4"
RESULT_SCHEMA_VERSION = "1.3"
DEFAULT_THRESHOLD_PROFILE_ID = "route-oracle-v0.3-default"
DEFAULT_RETAINED_SETTLE_MS = 500.0
DEFAULT_RETAINED_DURATION_MS = 3000.0
DEFAULT_THRESHOLDS = {
    "installation_deadline_ms": 300.0,
    "recovery_deadline_ms": 300.0,
    "minimum_continuity_gap_ms": 20.0,
    "continuity_period_multiplier": 3.0,
}


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


def _mode_transition(
    events: list[dict[str, Any]],
    source_mode: Any | None = None,
    target_mode: Any | None = None,
) -> dict[str, Any] | None:
    previous: Any = None
    previous_epoch: Any = None
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
                    "source_route_epoch_id": previous_epoch,
                    "timestamp_domain": "ulog_us",
                }
            )
        previous = mode
        previous_epoch = event.get("route_epoch_id")
        initialized = True
    if source_mode is not None or target_mode is not None:
        selected = [
            change
            for change in changes
            if (source_mode is None or change["source_mode"] == source_mode)
            and (target_mode is None or change["target_mode"] == target_mode)
        ]
        return selected[0] if selected else None

    external_exits = [
        change
        for change in changes
        if change["source_mode"] in EXTERNAL_MODES
        and change["target_mode"] not in EXTERNAL_MODES
    ]
    for change in external_exits:
        if any(
            event.get("timestamp_domain") == "ulog_us"
            and event.get("event_type") == "px4_setpoint_consumed"
            and event.get("declared_mode") == change["source_mode"]
            and event.get("route_epoch_id") == change["source_route_epoch_id"]
            and float(event["timestamp"]) <= float(change["timestamp_us"])
            for event in events
        ):
            return change
    if external_exits:
        return external_exits[0]
    return changes[0] if changes else None


def _valid_bridge(bridge: dict[str, Any] | None) -> bool:
    if bridge is None:
        return False
    required = {
        "clock_bridge_id",
        "status",
        "offset_ns",
        "rate_ratio",
        "reference_px4_us",
        "reference_ros_ns",
        "uncertainty_ns",
        "valid_from",
        "valid_until",
    }
    return (
        required <= set(bridge)
        and bridge["status"] == "VALID"
        and isinstance(bridge["clock_bridge_id"], str)
        and isinstance(bridge["offset_ns"], (int, float))
        and isinstance(bridge["rate_ratio"], (int, float))
        and float(bridge["rate_ratio"]) > 0
        and isinstance(bridge["reference_px4_us"], (int, float))
        and isinstance(bridge["reference_ros_ns"], (int, float))
        and isinstance(bridge["uncertainty_ns"], (int, float))
        and float(bridge["uncertainty_ns"]) >= 0
        and isinstance(bridge["valid_from"], (int, float))
        and isinstance(bridge["valid_until"], (int, float))
    )


def _px4_time(event: dict[str, Any], bridge: dict[str, Any] | None) -> float | None:
    domain = event.get("timestamp_domain")
    timestamp = float(event["timestamp"])
    if domain in {"ulog_us", "px4_boot_us", "px4_uorb_us"}:
        return timestamp
    if domain == "ros_node_ns" and _valid_bridge(bridge):
        mapped = float(bridge["reference_px4_us"]) + (
            timestamp - float(bridge["reference_ros_ns"])
        ) / (1000.0 * float(bridge["rate_ratio"]))
        if float(bridge["valid_from"]) <= mapped <= float(bridge["valid_until"]):
            return mapped
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


def _default_evidence_completeness(
    events: list[dict[str, Any]],
    writer_summary: dict[str, Any],
    clock_bridge: dict[str, Any] | None,
    transition: dict[str, Any] | None,
    source_artifact_complete: bool | None,
) -> dict[str, str]:
    if transition is None:
        return {
            "source_artifact": "COMPLETE" if events else "INCOMPLETE",
            "critical_window": "NOT_APPLICABLE",
            "writer_sequence": "NOT_APPLICABLE",
            "candidate_writer_coverage": "NOT_APPLICABLE",
            "clock_bridge": "NOT_REQUIRED",
            "route_epoch": "NOT_APPLICABLE",
        }

    cross_domain = any(
        event.get("timestamp_domain") == "ros_node_ns"
        for event in events
        if event.get("event_type") == "producer_still_publishing"
    )
    source_mode = transition["source_mode"]
    epoch_events = [
        event
        for event in events
        if event.get("declared_mode") == source_mode
        and event.get("event_type")
        in {"px4_setpoint_consumed", "allocator_input_published", "actuator_output_published"}
    ]
    route_epoch_status = (
        "COMPLETE"
        if epoch_events and all(event.get("route_epoch_id") is not None for event in epoch_events)
        else "INCOMPLETE"
    )
    critical_quality = str(
        writer_summary.get("critical_window_quality", {}).get("status", "INSUFFICIENT")
    )
    return {
        "source_artifact": (
            "COMPLETE"
            if source_artifact_complete is True
            else "INCOMPLETE"
            if source_artifact_complete is False
            else "UNKNOWN"
        ),
        "critical_window": critical_quality,
        "writer_sequence": (
            "COMPLETE"
            if not writer_summary.get("sequence_gaps")
            and writer_summary.get("global_capture_quality", {}).get("status") == "COMPLETE"
            else "INCOMPLETE"
        ),
        "candidate_writer_coverage": (
            "COMPLETE"
            if not writer_summary.get("uninstrumented_candidates")
            else "INCOMPLETE"
        ),
        "clock_bridge": (
            "VALID"
            if cross_domain and _valid_bridge(clock_bridge)
            else "MISSING"
            if cross_domain
            else "NOT_REQUIRED"
        ),
        "route_epoch": route_epoch_status,
    }


def _first_timestamp(events: list[dict[str, Any]]) -> float | None:
    return min((float(event["timestamp"]) for event in events), default=None)


def _deadline_status(
    *,
    missing: list[str],
    first_complete_us: float | None,
    transition_us: float,
    deadline_ms: float,
    source_artifact_complete: bool,
    label: str,
) -> tuple[str, list[str]]:
    latency_ms = (
        (first_complete_us - transition_us) / 1000.0
        if first_complete_us is not None
        else None
    )
    if not missing and latency_ms is not None and latency_ms > deadline_ms:
        return "VIOLATION", [
            f"{label} completed after the {deadline_ms:g} ms preregistered deadline"
        ]
    if missing and source_artifact_complete:
        return "VIOLATION", [f"required {label} element absent in a complete artifact: {name}" for name in missing]
    if missing:
        return "UNKNOWN", [f"missing {label} evidence: {name}" for name in missing]
    return "PASS", []


def _retained_result(
    events: list[dict[str, Any]],
    writer_summary: dict[str, Any],
    clock_bridge: dict[str, Any] | None,
    *,
    expected_mode: Any,
    settle_ms: float,
    duration_ms: float,
    source_artifact_complete: bool | None,
    ground_truth_case_id: str | None,
    oracle_validation_profile: str,
    threshold_profile_id: str,
    thresholds: dict[str, float],
) -> dict[str, Any]:
    run_id = str(events[0].get("run_id", "unknown")) if events else "unknown"
    source_status = (
        "COMPLETE"
        if source_artifact_complete is True
        else "INCOMPLETE"
        if source_artifact_complete is False
        else "UNKNOWN"
    )
    channel_events = sorted(
        (
            event
            for event in events
            if event.get("event_type") == "channel_configuration_applied"
            and event.get("timestamp_domain") == "ros_node_ns"
        ),
        key=lambda event: float(event["timestamp"]),
    )
    anchors = sorted(
        (
            event
            for event in events
            if event.get("event_type") == "experiment_window_started"
            and event.get("timestamp_domain") == "ros_node_ns"
        ),
        key=lambda event: float(event["timestamp"]),
    )
    anchor = next(
        (
            candidate
            for candidate in anchors
            if any(
                float(channel["timestamp"]) <= float(candidate["timestamp"])
                for channel in channel_events
            )
        ),
        None,
    )
    clock_status = (
        "VALID"
        if _valid_bridge(clock_bridge)
        else "MISSING"
        if clock_bridge is None
        else "INVALID"
    )
    nominal_start_ros_ns = (
        float(anchor["timestamp"]) + settle_ms * 1_000_000.0
        if anchor is not None
        else None
    )
    nominal_end_ros_ns = (
        nominal_start_ros_ns + duration_ms * 1_000_000.0
        if nominal_start_ros_ns is not None
        else None
    )
    start_us = (
        _px4_time(
            {"timestamp": nominal_start_ros_ns, "timestamp_domain": "ros_node_ns"},
            clock_bridge,
        )
        if nominal_start_ros_ns is not None
        else None
    )
    end_us = (
        _px4_time(
            {"timestamp": nominal_end_ros_ns, "timestamp_domain": "ros_node_ns"},
            clock_bridge,
        )
        if nominal_end_ros_ns is not None
        else None
    )
    uncertainty_us = (
        float(clock_bridge["uncertainty_ns"])
        / (1000.0 * float(clock_bridge["rate_ratio"]))
        if _valid_bridge(clock_bridge)
        else None
    )
    strict_start_us = (
        start_us + uncertainty_us
        if start_us is not None and uncertainty_us is not None
        else None
    )
    strict_end_us = (
        end_us - uncertainty_us
        if end_us is not None and uncertainty_us is not None
        else None
    )
    bound_events = [
        event
        for event in events
        if event.get("event_type") == "probe_state_transition"
        and event.get("timestamp_domain") == "ros_node_ns"
        and nominal_end_ros_ns is not None
        and float(event["timestamp"]) >= nominal_end_ros_ns
    ]

    setup_reasons: list[str] = []
    if source_artifact_complete is not True:
        setup_reasons.append("complete source artifact was not established")
    if not channel_events:
        setup_reasons.append("channel-configuration marker is unavailable")
    if anchor is None:
        setup_reasons.append("retained-window anchor is unavailable")
    if clock_status != "VALID" or start_us is None or end_us is None:
        setup_reasons.append("retained-window endpoints lack a valid clock mapping")
    if duration_ms < DEFAULT_RETAINED_DURATION_MS:
        setup_reasons.append("retained-window duration is below the preregistered minimum")
    if not bound_events:
        setup_reasons.append("bounded monitor observation does not cover the retained window")

    route_events: list[dict[str, Any]] = []
    before_start: list[dict[str, Any]] = []
    after_end: list[dict[str, Any]] = []
    if start_us is not None and end_us is not None:
        status_events = [
            event
            for event in events
            if event.get("event_type") == "vehicle_status"
            and event.get("timestamp_domain") == "ulog_us"
        ]
        before_start = [
            event for event in status_events if float(event["timestamp"]) <= start_us
        ]
        after_end = [
            event for event in status_events if float(event["timestamp"]) >= end_us
        ]
        route_events = [
            event
            for event in events
            if event.get("timestamp_domain") == "ulog_us"
            and event.get("event_type") in {"vehicle_status", "route_epoch_changed"}
            and start_us <= float(event["timestamp"]) <= end_us
        ]
    start_event = max(
        before_start, key=lambda event: float(event["timestamp"]), default=None
    )
    end_event = min(
        after_end, key=lambda event: float(event["timestamp"]), default=None
    )
    expected_epoch = start_event.get("route_epoch_id") if start_event else None
    expected_authority = (
        "ros2_offboard"
        if expected_mode == 14
        else "dynamic_external_mode"
        if expected_mode in EXTERNAL_MODES
        else None
    )
    route_reasons: list[str] = []
    if start_event is None or start_event.get("declared_mode") != expected_mode:
        route_reasons.append("expected external route was not established at window start")
    if expected_epoch is None:
        route_reasons.append("retained route epoch is unavailable at window start")
    if end_event is None:
        route_reasons.append("declared-route evidence does not cover the window end")
    if expected_authority is None:
        route_reasons.append("expected retained mode is not an external route")

    registration_reasons: list[str] = []
    if expected_mode in EXTERNAL_MODES and expected_mode != 14:
        registration = start_event.get("registration_state") if start_event else None
        if not isinstance(registration, dict) or not registration.get("registered"):
            registration_reasons.append(
                "dynamic external registration was not established at window start"
            )
    activation_events = [
        event
        for event in events
        if event.get("route_activation_id") is not None
        and nominal_start_ros_ns is not None
        and event.get("timestamp_domain") == "ros_node_ns"
        and float(event["timestamp"]) <= nominal_start_ros_ns
    ]
    activation_id = (
        activation_events[-1].get("route_activation_id") if activation_events else None
    )
    registration_instance_id = (
        activation_events[-1].get("registration_instance_id")
        if activation_events
        else None
    )

    interior_changes: list[dict[str, Any]] = []
    boundary_changes: list[dict[str, Any]] = []
    if expected_epoch is not None and start_us is not None and end_us is not None:
        mismatches = [
            event
            for event in route_events
            if event.get("declared_mode") != expected_mode
            or event.get("route_epoch_id") != expected_epoch
            or (
                expected_authority is not None
                and event.get("authority_source") not in {None, expected_authority}
            )
        ]
        for event in mismatches:
            timestamp = float(event["timestamp"])
            if (
                strict_start_us is not None
                and strict_end_us is not None
                and strict_start_us < timestamp < strict_end_us
            ):
                interior_changes.append(event)
            else:
                boundary_changes.append(event)
    unexpected_modes = {
        event.get("declared_mode")
        for event in interior_changes
        if event.get("declared_mode") != expected_mode
    }
    unexpected_fallback_count = len(
        {mode for mode in unexpected_modes if mode not in EXTERNAL_MODES}
    )
    unexpected_route_change_count = len(
        {
            (
                event.get("declared_mode"),
                event.get("route_epoch_id"),
            )
            for event in interior_changes
        }
    )
    authority_conflicts = [
        event
        for event in route_events
        if expected_authority is not None
        and event.get("authority_source") not in {None, expected_authority}
    ]
    registration_conflicts = [
        event
        for event in route_events
        if expected_mode in EXTERNAL_MODES
        and expected_mode != 14
        and isinstance(event.get("registration_state"), dict)
        and not event["registration_state"].get("registered", False)
    ]
    authority_conflict_count = len(authority_conflicts) + len(registration_conflicts)

    writer_events: list[dict[str, Any]] = []
    if start_us is not None and end_us is not None:
        writer_events = sorted(
            (
                event
                for event in events
                if event.get("event_type") == "actuator_output_published"
                and event.get("timestamp_domain") == "ulog_us"
                and start_us <= float(event["timestamp"]) <= end_us
            ),
            key=lambda event: float(event["timestamp"]),
        )
    observed_writers = sorted(
        {
            str(event.get("actuator_writer"))
            for event in writer_events
            if event.get("actuator_writer") is not None
        }
    )
    writer_epochs = {
        event.get("route_epoch_id")
        for event in writer_events
        if event.get("route_epoch_id") is not None
    }
    writer_conflict_count = max(0, len(observed_writers) - 1)
    if expected_epoch is not None and any(epoch != expected_epoch for epoch in writer_epochs):
        writer_conflict_count += 1
    sequence_complete = bool(writer_events)
    previous_by_writer: dict[str, int] = {}
    for event in writer_events:
        writer = str(event.get("actuator_writer"))
        observation = event.get("observation")
        if not isinstance(observation, dict) or not isinstance(observation.get("sequence"), int):
            sequence_complete = False
            continue
        sequence = int(observation["sequence"])
        if writer in previous_by_writer and sequence != previous_by_writer[writer] + 1:
            sequence_complete = False
        previous_by_writer[writer] = sequence
    candidate_coverage = not writer_summary.get("uninstrumented_candidates")
    expected_period_ms = float(writer_summary.get("expected_period_ms", 0.0))
    allowed_gap_ms = max(
        float(thresholds["minimum_continuity_gap_ms"]),
        float(thresholds["continuity_period_multiplier"]) * expected_period_ms,
    )
    maximum_gap_ms: float | None = None
    if writer_events and start_us is not None and end_us is not None:
        timestamps = [float(event["timestamp"]) for event in writer_events]
        gaps_us = [timestamps[0] - start_us, end_us - timestamps[-1]]
        gaps_us.extend(right - left for left, right in zip(timestamps, timestamps[1:]))
        maximum_gap_ms = max(gaps_us) / 1000.0

    writer_reasons: list[str] = []
    if not writer_events:
        writer_reasons.append("retained-window writer evidence is unavailable")
    if not observed_writers:
        writer_reasons.append("retained writer identity is unavailable")
    if not sequence_complete:
        writer_reasons.append("retained writer sequence is incomplete")
    if not candidate_coverage:
        writer_reasons.append("candidate writer coverage is incomplete")

    proved_route_violation = bool(interior_changes)
    proved_exclusivity_violation = (
        proved_route_violation or authority_conflict_count > 0 or writer_conflict_count > 0
    )
    proved_gap_violation = (
        maximum_gap_ms is not None
        and maximum_gap_ms > allowed_gap_ms
        and sequence_complete
        and candidate_coverage
    )
    coverage_reasons = [
        *setup_reasons,
        *route_reasons,
        *registration_reasons,
        *writer_reasons,
    ]
    if boundary_changes:
        coverage_reasons.append("route-change membership is ambiguous at a clock boundary")
    if proved_route_violation or proved_exclusivity_violation or proved_gap_violation:
        critical_window = "COMPLETE" if not setup_reasons else "INSUFFICIENT"
    else:
        critical_window = "COMPLETE" if not coverage_reasons else "INSUFFICIENT"

    exclusivity_metrics = {
        "expected_mode": expected_mode,
        "expected_route_epoch_id": expected_epoch,
        "expected_authority_source": expected_authority,
        "activation_id": activation_id,
        "registration_instance_id": registration_instance_id,
        "observed_writers": observed_writers,
        "unexpected_route_change_count": unexpected_route_change_count,
        "unexpected_fallback_count": unexpected_fallback_count,
        "authority_conflict_count": authority_conflict_count,
        "writer_conflict_count": writer_conflict_count,
    }
    if proved_exclusivity_violation:
        exclusivity = _clause(
            "VIOLATION", exclusivity_metrics, reasons=["retained route was not exclusive"]
        )
    elif coverage_reasons:
        exclusivity = _clause("UNKNOWN", exclusivity_metrics, reasons=coverage_reasons)
    else:
        exclusivity = _clause("PASS", exclusivity_metrics)

    continuity_metrics = {
        "retained_window_duration_ms": duration_ms,
        "maximum_unowned_window_ms": maximum_gap_ms,
        "allowed_gap_ms": allowed_gap_ms,
        "writer_event_count": len(writer_events),
        "writer_sequence_complete": sequence_complete,
    }
    if proved_route_violation or proved_gap_violation:
        continuity_reasons = []
        if proved_route_violation:
            continuity_reasons.append("expected retained route changed inside the window")
        if proved_gap_violation:
            continuity_reasons.append("maximum unowned window exceeds the observation contract")
        continuity = _clause("VIOLATION", continuity_metrics, reasons=continuity_reasons)
    elif coverage_reasons:
        continuity = _clause("UNKNOWN", continuity_metrics, reasons=coverage_reasons)
    else:
        continuity = _clause("PASS", continuity_metrics)

    clauses = {
        "revocation": _clause(
            "NOT_APPLICABLE", reasons=["retained-route observation expects no revocation"]
        ),
        "installation": _clause(
            "NOT_APPLICABLE", reasons=["retained-route observation expects no target installation"]
        ),
        "exclusivity": exclusivity,
        "continuity": continuity,
        "recovery": _clause(
            "NOT_APPLICABLE", reasons=["retained-route observation expects no fallback recovery"]
        ),
    }
    statuses = {clause["status"] for clause in clauses.values()}
    overall = (
        "VIOLATION"
        if "VIOLATION" in statuses
        else "PASS"
        if statuses <= {"PASS", "NOT_APPLICABLE"}
        else "UNKNOWN"
    )
    categories: list[str] = []
    if unexpected_fallback_count:
        categories.append("UNEXPECTED_FALLBACK")
    elif unexpected_route_change_count:
        categories.append("UNEXPECTED_ROUTE_CHANGE")
    if proved_gap_violation:
        categories.append("ROUTE_RETENTION_GAP")
    if authority_conflict_count:
        categories.append("AUTHORITY_CONFLICT")
    if writer_conflict_count:
        categories.append("WRITER_CONFLICT")
    if overall == "UNKNOWN":
        categories.append("STALE_OR_INSUFFICIENT_EVIDENCE")

    retained_route = {
        "expected_mode": expected_mode,
        "expected_route_epoch_id": expected_epoch,
        "anchor_event": "experiment_window_started",
        "anchor_ros_ns": float(anchor["timestamp"]) if anchor is not None else None,
        "settle_interval_ms": settle_ms,
        "nominal_start_ros_ns": nominal_start_ros_ns,
        "nominal_end_ros_ns": nominal_end_ros_ns,
        "nominal_start_us": start_us,
        "nominal_end_us": end_us,
        "clock_uncertainty_us": uncertainty_us,
        "nominal_duration_ms": duration_ms,
        "coverage_verdict": critical_window,
        **exclusivity_metrics,
        **continuity_metrics,
    }
    evidence_completeness = {
        "source_artifact": source_status,
        "critical_window": critical_window,
        "writer_sequence": "COMPLETE" if sequence_complete else "INCOMPLETE",
        "candidate_writer_coverage": "COMPLETE" if candidate_coverage else "INCOMPLETE",
        "clock_bridge": clock_status,
        "route_epoch": "COMPLETE" if expected_epoch is not None else "INCOMPLETE",
    }
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "route_oracle_version": ORACLE_VERSION,
        "run_id": run_id,
        "observation_kind": "RETAINED_ROUTE",
        "status": overall,
        "violation_categories": categories,
        "transition": None,
        "retained_route": retained_route,
        "clock_bridge": clock_bridge,
        "ground_truth_case_id": ground_truth_case_id,
        "oracle_validation_profile": oracle_validation_profile,
        "threshold_profile_id": threshold_profile_id,
        "evidence_completeness": evidence_completeness,
        "clauses": clauses,
    }


def evaluate(
    events: list[dict[str, Any]],
    writer_summary: dict[str, Any],
    clock_bridge: dict[str, Any] | None = None,
    *,
    ground_truth_case_id: str | None = None,
    oracle_validation_profile: str = "production",
    threshold_profile_id: str = DEFAULT_THRESHOLD_PROFILE_ID,
    thresholds: dict[str, float] | None = None,
    source_artifact_complete: bool | None = None,
    transition_source_mode: Any | None = None,
    transition_target_mode: Any | None = None,
    observation_kind: str = "transition",
    retained_route_mode: Any | None = None,
    retained_settle_ms: float = DEFAULT_RETAINED_SETTLE_MS,
    retained_window_duration_ms: float = DEFAULT_RETAINED_DURATION_MS,
) -> dict[str, Any]:
    active_thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    normalized_kind = observation_kind.upper().replace("-", "_")
    if normalized_kind == "RETAINED_ROUTE":
        if retained_route_mode is None:
            raise ValueError("retained-route observation requires retained_route_mode")
        return _retained_result(
            events,
            writer_summary,
            clock_bridge,
            expected_mode=retained_route_mode,
            settle_ms=retained_settle_ms,
            duration_ms=retained_window_duration_ms,
            source_artifact_complete=source_artifact_complete,
            ground_truth_case_id=ground_truth_case_id,
            oracle_validation_profile=oracle_validation_profile,
            threshold_profile_id=threshold_profile_id,
            thresholds=active_thresholds,
        )
    if normalized_kind != "TRANSITION":
        raise ValueError(f"unsupported observation kind: {observation_kind}")
    run_id = str(events[0].get("run_id", "unknown")) if events else "unknown"
    transition = _mode_transition(events, transition_source_mode, transition_target_mode)
    evidence_completeness = _default_evidence_completeness(
        events,
        writer_summary,
        clock_bridge,
        transition,
        source_artifact_complete,
    )
    if transition is None:
        clauses = {
            name: _clause("NOT_APPLICABLE", reasons=["no declared mode transition was observed"])
            for name in ("revocation", "installation", "exclusivity", "continuity", "recovery")
        }
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "route_oracle_version": ORACLE_VERSION,
            "run_id": run_id,
            "observation_kind": "TRANSITION",
            "status": "NOT_APPLICABLE",
            "violation_categories": [],
            "transition": None,
            "retained_route": None,
            "clock_bridge": clock_bridge,
            "ground_truth_case_id": ground_truth_case_id,
            "oracle_validation_profile": oracle_validation_profile,
            "threshold_profile_id": threshold_profile_id,
            "evidence_completeness": evidence_completeness,
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
    old_allocators = [
        event
        for event in _events_with_mode(events, source_mode, "allocator_input_published")
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
    last_old_subject_timestamp = (
        float(last_consume_event["observation"]["subject_timestamp"])
        if last_consume_event is not None
        and isinstance(last_consume_event.get("observation"), dict)
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
    last_allocator_event = max(
        old_allocators, key=lambda event: float(event["timestamp"]), default=None
    )
    last_allocator = (
        float(last_allocator_event["timestamp"])
        if last_allocator_event is not None
        else None
    )
    old_allocator_epoch = (
        last_allocator_event.get("route_epoch_id")
        if last_allocator_event is not None
        else None
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
    stale_target_consumptions = (
        [
            event
            for event in events
            if event.get("event_type") == "px4_setpoint_consumed"
            and event.get("timestamp_domain") == "ulog_us"
            and float(event["timestamp"]) > exit_time
            and isinstance(event.get("observation"), dict)
            and float(event["observation"]["subject_timestamp"])
            <= last_old_subject_timestamp
        ]
        if last_old_subject_timestamp is not None
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
    post_allocators = (
        [
            event
            for event in events
            if event.get("event_type") == "allocator_input_published"
            and event.get("timestamp_domain") == "ulog_us"
            and float(event["timestamp"]) > exit_time
            and event.get("route_epoch_id") == old_allocator_epoch
        ]
        if old_allocator_epoch is not None
        else []
    )
    influence_times = [
        value for value in (last_consume, last_allocator, last_writer) if value is not None
    ]
    revocation_latency_ms = (
        (max(influence_times) - exit_time) / 1000.0 if influence_times else None
    )
    revocation_metrics = {
        "declared_route_exit_us": exit_time,
        "last_producer_publish_us": last_producer,
        "last_old_route_consumption_us": last_consume,
        "last_old_allocator_event_us": last_allocator,
        "last_old_writer_event_us": last_writer,
        "revocation_latency_ms": revocation_latency_ms,
        "post_revocation_consumption_count": (
            len(post_consumptions) if old_consume_epoch is not None else None
        ),
        "post_revocation_stale_subject_consumption_count": len(stale_target_consumptions),
        "last_old_consumed_subject_timestamp_us": last_old_subject_timestamp,
        "post_revocation_writer_count": (
            len(post_writers) if old_writer_epoch is not None else None
        ),
        "post_revocation_allocator_count": (
            len(post_allocators) if old_allocator_epoch is not None else None
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
    if not old_allocators:
        revocation_reasons.append("no source-route allocator evidence")
    elif old_allocator_epoch is None:
        revocation_reasons.append(
            "old-route allocator events lack route_epoch_id; later allocator input cannot be attributed to the old route"
        )
    if (old_consume_epoch is not None and post_consumptions) or (
        old_writer_epoch is not None and post_writers
    ) or (
        old_allocator_epoch is not None and post_allocators
    ) or stale_target_consumptions:
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
    installation_completion_candidates = [
        _first_timestamp(target_consumptions),
        _first_timestamp(target_allocators),
        _first_timestamp(target_writers),
    ]
    first_installation_complete = (
        max(timestamp for timestamp in installation_completion_candidates if timestamp is not None)
        if not missing_installation
        else None
    )
    installation_status, installation_reasons = _deadline_status(
        missing=missing_installation,
        first_complete_us=first_installation_complete,
        transition_us=exit_time,
        deadline_ms=float(active_thresholds["installation_deadline_ms"]),
        source_artifact_complete=evidence_completeness["source_artifact"] == "COMPLETE",
        label="target-route installation",
    )
    installation = _clause(
        installation_status,
        {
            "checks": installation_checks,
            "first_target_consumption_us": (
                float(target_consumptions[0]["timestamp"]) if target_consumptions else None
            ),
            "first_target_writer_us": float(target_writers[0]["timestamp"]) if target_writers else None,
            "installation_complete_us": first_installation_complete,
            "installation_latency_ms": (
                (first_installation_complete - exit_time) / 1000.0
                if first_installation_complete is not None
                else None
            ),
            "installation_deadline_ms": active_thresholds["installation_deadline_ms"],
        },
        reasons=installation_reasons,
    )

    local_windows = [
        window
        for window in writer_summary.get("transition_windows", [])
        if window.get("from_mode") == source_mode
        and window.get("to_mode") == target_mode
        and float(window.get("start_us", 0)) <= exit_time <= float(window.get("end_us", 0))
    ]
    local_window = min(
        local_windows,
        key=lambda window: abs(float(window.get("timestamp_us", 0)) - exit_time),
        default=None,
    )
    local_quality = (
        str(local_window.get("coverage_verdict"))
        if local_window is not None
        else "INSUFFICIENT"
    )
    local_writers = list(local_window.get("observed_writers", [])) if local_window else []
    local_competing = len(local_writers) > 1
    target_epochs = {
        event.get("route_epoch_id")
        for event in target_writers
        if event.get("route_epoch_id") is not None
    }
    old_new_epoch_overlap = bool(post_writers and target_epochs)
    if local_competing:
        exclusivity_status = "VIOLATION"
        exclusivity_reasons = ["multiple stable writer IDs occurred in the target critical window"]
    elif old_new_epoch_overlap:
        exclusivity_status = "VIOLATION"
        exclusivity_reasons = [
            "source and target route epochs both produced valid writer influence after target selection"
        ]
    elif local_quality == "COMPLETE" and len(local_writers) == 1:
        exclusivity_status = "PASS"
        exclusivity_reasons: list[str] = []
    elif local_quality == "BOUNDED":
        exclusivity_status = "UNKNOWN"
        exclusivity_reasons = ["critical-window capture is bounded; overlap below the resolution cannot be excluded"]
    else:
        exclusivity_status = "UNKNOWN"
        exclusivity_reasons = ["target critical-window coverage is insufficient"]
    exclusivity = _clause(
        exclusivity_status,
        {
            "candidate_writers": writer_summary.get("candidate_writers", []),
            "observed_writers": writer_summary.get("observed_writers", []),
            "uninstrumented_candidates": writer_summary.get("uninstrumented_candidates", []),
            "sequence_gap_count": len(writer_summary.get("sequence_gaps", [])),
            "competing_window_count": len(writer_summary.get("competing_windows", [])),
            "observation_hole_count": len(writer_summary.get("observation_holes", [])),
            "critical_window_quality": local_quality,
            "old_new_epoch_overlap": old_new_epoch_overlap,
            "critical_window": local_window,
            "detectable_resolution_ms": (
                float(local_window.get("maximum_gap_ms", 0))
                if local_quality == "BOUNDED" and local_window is not None
                else 0.0
            ),
            "resolution_verdict": (
                "PASS_ABOVE_RESOLUTION"
                if local_quality == "BOUNDED" and not local_competing
                else None
            ),
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
    allowed_gap_ms = max(
        float(active_thresholds["minimum_continuity_gap_ms"]),
        float(active_thresholds["continuity_period_multiplier"]) * expected_period_ms,
    )
    sequence_proves_gap = (
        not writer_summary.get("sequence_gaps")
        and not writer_summary.get("uninstrumented_candidates")
        and writer_summary.get("global_capture_quality", {}).get("status") == "COMPLETE"
    )
    if gap_ms is not None and gap_ms > allowed_gap_ms and sequence_proves_gap:
        continuity_status = "VIOLATION"
        continuity_reasons = ["maximum no-owner window exceeds the observation contract"]
    elif local_quality != "COMPLETE" or gap_ms is None:
        continuity_status = "UNKNOWN"
        continuity_reasons = ["complete target critical-window writer evidence is unavailable"]
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
    later_source_reentries = [
        event
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and event.get("event_type") == "vehicle_status"
        and event.get("declared_mode") == source_mode
        and float(event["timestamp"]) > exit_time
        and event.get("route_change_source") == "automatic_reentry"
    ]
    automatic_old_route_reentry = bool(later_source_reentries)
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
    elif (
        post_consumptions
        or post_allocators
        or post_writers
        or stale_target_consumptions
        or automatic_old_route_reentry
    ):
        recovery_status = "VIOLATION"
        recovery_reasons = ["old route influenced or re-entered after fallback selection"]
    else:
        recovery_completion_candidates = [
            _first_timestamp(target_consumptions),
            _first_timestamp(target_allocators),
            _first_timestamp(target_writers),
        ]
        first_recovery_complete = (
            max(
                timestamp
                for timestamp in recovery_completion_candidates
                if timestamp is not None
            )
            if not missing_recovery
            else None
        )
        recovery_status, recovery_reasons = _deadline_status(
            missing=missing_recovery,
            first_complete_us=first_recovery_complete,
            transition_us=exit_time,
            deadline_ms=float(active_thresholds["recovery_deadline_ms"]),
            source_artifact_complete=(
                evidence_completeness["source_artifact"] == "COMPLETE"
                and evidence_completeness["route_epoch"] == "COMPLETE"
                and evidence_completeness["clock_bridge"] in {"VALID", "NOT_REQUIRED"}
            ),
            label="fallback recovery",
        )
    recovery = _clause(
        recovery_status,
        {
            "checks": recovery_checks,
            "automatic_old_route_reentry_observed": automatic_old_route_reentry,
            "recovery_deadline_ms": active_thresholds["recovery_deadline_ms"],
        },
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
        "schema_version": RESULT_SCHEMA_VERSION,
        "route_oracle_version": ORACLE_VERSION,
        "run_id": run_id,
        "observation_kind": "TRANSITION",
        "status": overall,
        "violation_categories": [],
        "transition": transition,
        "retained_route": None,
        "clock_bridge": clock_bridge,
        "ground_truth_case_id": ground_truth_case_id,
        "oracle_validation_profile": oracle_validation_profile,
        "threshold_profile_id": threshold_profile_id,
        "evidence_completeness": evidence_completeness,
        "clauses": clauses,
    }


def run(
    trace: Path,
    clock_bridge: dict[str, Any] | None = None,
    *,
    ground_truth_case_id: str | None = None,
    oracle_validation_profile: str = "production",
    threshold_profile_id: str = DEFAULT_THRESHOLD_PROFILE_ID,
    thresholds: dict[str, float] | None = None,
    source_artifact_complete: bool | None = None,
    candidate_writers: Iterable[str] | None = None,
    instrumented_candidates: Iterable[str] | None = None,
    transition_source_mode: Any | None = None,
    transition_target_mode: Any | None = None,
    observation_kind: str = "transition",
    retained_route_mode: Any | None = None,
    retained_settle_ms: float = DEFAULT_RETAINED_SETTLE_MS,
    retained_window_duration_ms: float = DEFAULT_RETAINED_DURATION_MS,
) -> dict[str, Any]:
    events = [
        json.loads(line)
        for line in trace.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result = evaluate(
        events,
        summarize_writers(
            trace,
            candidate_writers=candidate_writers,
            instrumented_candidates=instrumented_candidates,
        ),
        clock_bridge,
        ground_truth_case_id=ground_truth_case_id,
        oracle_validation_profile=oracle_validation_profile,
        threshold_profile_id=threshold_profile_id,
        thresholds=thresholds,
        source_artifact_complete=source_artifact_complete,
        transition_source_mode=transition_source_mode,
        transition_target_mode=transition_target_mode,
        observation_kind=observation_kind,
        retained_route_mode=retained_route_mode,
        retained_settle_ms=retained_settle_ms,
        retained_window_duration_ms=retained_window_duration_ms,
    )
    Draft202012Validator(RESULT_SCHEMA).validate(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clock-bridge", type=Path)
    parser.add_argument("--ground-truth-case-id")
    parser.add_argument("--validation-profile", default="production")
    parser.add_argument("--threshold-profile-id", default=DEFAULT_THRESHOLD_PROFILE_ID)
    parser.add_argument("--transition-source-mode", type=int)
    parser.add_argument("--transition-target-mode", type=int)
    parser.add_argument(
        "--observation-kind",
        choices=("transition", "retained-route"),
        default="transition",
    )
    parser.add_argument("--retained-route-mode", type=int)
    parser.add_argument(
        "--retained-settle-ms", type=float, default=DEFAULT_RETAINED_SETTLE_MS
    )
    parser.add_argument(
        "--retained-window-duration-ms",
        type=float,
        default=DEFAULT_RETAINED_DURATION_MS,
    )
    parser.add_argument(
        "--source-artifact-complete",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    args = parser.parse_args()
    bridge = (
        json.loads(args.clock_bridge.read_text(encoding="utf-8"))
        if args.clock_bridge is not None
        else None
    )
    result = run(
        args.trace,
        bridge,
        ground_truth_case_id=args.ground_truth_case_id,
        oracle_validation_profile=args.validation_profile,
        threshold_profile_id=args.threshold_profile_id,
        source_artifact_complete=args.source_artifact_complete,
        transition_source_mode=args.transition_source_mode,
        transition_target_mode=args.transition_target_mode,
        observation_kind=args.observation_kind,
        retained_route_mode=args.retained_route_mode,
        retained_settle_ms=args.retained_settle_ms,
        retained_window_duration_ms=args.retained_window_duration_ms,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
