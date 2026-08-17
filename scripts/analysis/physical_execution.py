#!/usr/bin/env python3
"""Audit physical execution and aligned motion windows in frozen Motivation data."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable

from scripts.analysis.corpus import CorpusError, file_digest, load_frozen_corpus
from scripts.evaluator.plan import load_plan
from scripts.evaluator.result_model import load_evaluation
from scripts.model.runtime_route import EFFECT_EVENT_KINDS, read_trace
from scripts.oracles.common import complete_installation
from scripts.oracles.transition_scope import (
    matching_transition_requests,
    transition_window_end_ns,
)


class PhysicalExecutionError(RuntimeError):
    """The physical audit cannot proceed without changing or guessing inputs."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise PhysicalExecutionError(f"non-object JSON at {path}:{line_number}")
        values.append(value)
    if not values:
        raise PhysicalExecutionError(f"empty telemetry input: {path}")
    return values


def _finite_number(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _received_ns(value: dict[str, Any]) -> int | None:
    raw = value.get("received_monotonic_ns")
    return int(raw) if isinstance(raw, int) and raw >= 0 else None


def _within(value: dict[str, Any], start_ns: int | None, end_ns: int | None) -> bool:
    timestamp = _received_ns(value)
    if timestamp is None:
        return False
    return (start_ns is None or timestamp >= start_ns) and (
        end_ns is None or timestamp <= end_ns
    )


def quaternion_tilt_degrees(q: object) -> float | None:
    """Return yaw-independent body-z tilt for a [w, x, y, z] quaternion."""

    if not isinstance(q, list) or len(q) != 4:
        return None
    components = [_finite_number(value) for value in q]
    if any(value is None for value in components):
        return None
    w, x, y, z = (float(value) for value in components)
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if norm <= 0.0:
        return None
    x /= norm
    y /= norm
    cosine = max(-1.0, min(1.0, 1.0 - 2.0 * (x * x + y * y)))
    return math.degrees(math.acos(cosine))


def _position(value: dict[str, Any]) -> tuple[float, float, float] | None:
    if value.get("kind") != "vehicle_local_position":
        return None
    x = _finite_number(value.get("x"))
    y = _finite_number(value.get("y"))
    z = _finite_number(value.get("z"))
    if x is None or y is None or z is None:
        return None
    if not bool(value.get("xy_valid")) or not bool(value.get("z_valid")):
        return None
    return x, y, z


def _vector_norm(values: object) -> float | None:
    if not isinstance(values, list) or len(values) != 3:
        return None
    numbers = [_finite_number(value) for value in values]
    if any(value is None for value in numbers):
        return None
    return math.sqrt(sum(float(value) ** 2 for value in numbers))


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 9)


def physical_metrics(
    telemetry: list[dict[str, Any]],
    *,
    start_ns: int | None = None,
    end_ns: int | None = None,
) -> dict[str, Any]:
    """Compute continuous physical measurements in a host-monotonic window."""

    selected = [value for value in telemetry if _within(value, start_ns, end_ns)]
    positions = [
        (_received_ns(value), _position(value), value)
        for value in selected
        if _position(value) is not None
    ]
    positions = [
        (int(timestamp), position, value)
        for timestamp, position, value in positions
        if timestamp is not None and position is not None
    ]
    positions.sort(key=lambda item: item[0])

    attitudes = [
        quaternion_tilt_degrees(value.get("q"))
        for value in selected
        if value.get("kind") == "vehicle_attitude"
    ]
    tilts = [value for value in attitudes if value is not None]
    body_rates = [
        _vector_norm(value.get("xyz"))
        for value in selected
        if value.get("kind") == "vehicle_angular_velocity"
    ]
    rates = [value for value in body_rates if value is not None]
    landed = [
        value
        for value in selected
        if value.get("kind") == "vehicle_land_detected"
        and isinstance(value.get("landed"), bool)
    ]

    if not positions:
        return {
            "status": "UNKNOWN",
            "window_start_ns": start_ns,
            "window_end_ns": end_ns,
            "duration_ns": (
                end_ns - start_ns
                if start_ns is not None and end_ns is not None and end_ns >= start_ns
                else None
            ),
            "position_sample_count": 0,
            "attitude_sample_count": len(tilts),
            "body_rate_sample_count": len(rates),
            "land_detected_sample_count": len(landed),
            "reason": "no valid local-position sample in the window",
        }

    first_ns, first, _ = positions[0]
    last_ns, last, _ = positions[-1]
    heights = [-position[2] for _, position, _ in positions]
    horizontal_from_origin = [
        math.hypot(position[0], position[1]) for _, position, _ in positions
    ]
    distances_from_start = [
        math.sqrt(
            (position[0] - first[0]) ** 2
            + (position[1] - first[1]) ** 2
            + (position[2] - first[2]) ** 2
        )
        for _, position, _ in positions
    ]
    horizontal_speeds = []
    vertical_speeds = []
    for _, _, value in positions:
        vx = _finite_number(value.get("vx"))
        vy = _finite_number(value.get("vy"))
        vz = _finite_number(value.get("vz"))
        if vx is not None and vy is not None:
            horizontal_speeds.append(math.hypot(vx, vy))
        if vz is not None:
            vertical_speeds.append(abs(vz))

    path_length = 0.0
    for (_, previous, _), (_, current, _) in zip(positions, positions[1:]):
        path_length += math.sqrt(
            (current[0] - previous[0]) ** 2
            + (current[1] - previous[1]) ** 2
            + (current[2] - previous[2]) ** 2
        )
    straight_line = math.sqrt(
        (last[0] - first[0]) ** 2
        + (last[1] - first[1]) ** 2
        + (last[2] - first[2]) ** 2
    )
    return {
        "status": "CALCULABLE",
        "window_start_ns": start_ns,
        "window_end_ns": end_ns,
        "duration_ns": (
            end_ns - start_ns
            if start_ns is not None and end_ns is not None and end_ns >= start_ns
            else last_ns - first_ns
        ),
        "first_position_sample_ns": first_ns,
        "last_position_sample_ns": last_ns,
        "position_sample_count": len(positions),
        "attitude_sample_count": len(tilts),
        "body_rate_sample_count": len(rates),
        "land_detected_sample_count": len(landed),
        "landed_false_sample_count": sum(not bool(value["landed"]) for value in landed),
        "start_position_ned_m": [_round(value) for value in first],
        "end_position_ned_m": [_round(value) for value in last],
        "maximum_height_above_local_origin_m": _round(max(heights)),
        "minimum_height_above_local_origin_m": _round(min(heights)),
        "maximum_horizontal_distance_from_origin_m": _round(
            max(horizontal_from_origin)
        ),
        "maximum_distance_from_window_start_m": _round(max(distances_from_start)),
        "straight_line_displacement_m": _round(straight_line),
        "horizontal_displacement_m": _round(
            math.hypot(last[0] - first[0], last[1] - first[1])
        ),
        "vertical_displacement_m": _round(-(last[2] - first[2])),
        "sampled_path_length_m": _round(path_length),
        "peak_horizontal_speed_m_s": _round(
            max(horizontal_speeds) if horizontal_speeds else None
        ),
        "peak_absolute_vertical_speed_m_s": _round(
            max(vertical_speeds) if vertical_speeds else None
        ),
        "peak_tilt_deg": _round(max(tilts) if tilts else None),
        "peak_body_rate_rad_s": _round(max(rates) if rates else None),
    }


def _first_event(
    events: Iterable[dict[str, Any]],
    *,
    kind: str,
    start_ns: int,
    end_ns: int,
    route: str | None = None,
) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in sorted(
                events,
                key=lambda value: (
                    int(value["timestamp_ns"]),
                    int(value["sequence"]),
                ),
            )
            if event.get("kind") == kind
            and start_ns <= int(event["timestamp_ns"]) <= end_ns
            and (route is None or event.get("route") == route)
        ),
        None,
    )


def _window(
    kind: str,
    status: str,
    start_ns: int | None,
    end_ns: int | None,
    anchor_sequence: int | None,
    telemetry: list[dict[str, Any]],
) -> dict[str, Any]:
    calculable = (
        start_ns is not None and end_ns is not None and int(end_ns) >= int(start_ns)
    )
    return {
        "window_kind": kind,
        "window_status": status,
        "anchor_sequence": anchor_sequence,
        "start_ns": start_ns,
        "end_ns": end_ns,
        "physical_metrics": (
            physical_metrics(telemetry, start_ns=start_ns, end_ns=end_ns)
            if calculable
            else None
        ),
    }


def aligned_windows(
    events: list[dict[str, Any]],
    plan: dict[str, Any],
    telemetry: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Align physical samples to transition, authority, freshness, fault, and successor."""

    transition = plan["transition"]
    target = str(transition["target_route"])
    expected_route = str(
        transition["expected_fallback"]
        if transition["fault_expected"] and transition["fallback_expected"]
        else transition["expected_successor"]
    )
    windows: list[dict[str, Any]] = []
    for request in matching_transition_requests(events, plan):
        request_ns = int(request["timestamp_ns"])
        request_sequence = int(request["sequence"])
        scope_end_ns = transition_window_end_ns(events, plan, request)
        installation = complete_installation(
            events, route=target, anchor_ns=request_ns, deadline_ns=scope_end_ns
        )
        installation_end_ns = (
            int(installation["completed_at_ns"])
            if installation.get("complete")
            else min(
                scope_end_ns,
                request_ns + int(plan["thresholds"]["installation_deadline_ns"]),
            )
        )
        transition_windows = [
            _window(
                "transition_installation",
                "COMPLETE" if installation.get("complete") else "INCOMPLETE",
                request_ns,
                installation_end_ns,
                request_sequence,
                telemetry,
            )
        ]

        activation = _first_event(
            events,
            kind="activation",
            start_ns=request_ns,
            end_ns=scope_end_ns,
            route=target,
        )
        activation_ns = int(activation["timestamp_ns"]) if activation else None
        revocation = (
            _first_event(
                events,
                kind="revocation",
                start_ns=activation_ns,
                end_ns=scope_end_ns,
                route=target,
            )
            if activation_ns is not None
            else None
        )
        authority_end_ns = (
            int(revocation["timestamp_ns"]) if revocation is not None else scope_end_ns
        )
        transition_windows.append(
            _window(
                "target_authority",
                "OBSERVED" if activation_ns is not None else "NOT_OBSERVED",
                activation_ns,
                authority_end_ns if activation_ns is not None else None,
                int(activation["sequence"]) if activation else None,
                telemetry,
            )
        )

        stale_effects = [
            event
            for event in events
            if activation_ns is not None
            and event.get("kind") in EFFECT_EVENT_KINDS
            and event.get("route") == target
            and activation_ns <= int(event["timestamp_ns"]) <= authority_end_ns
            and isinstance(event.get("command_subject_ns"), int)
            and int(event["timestamp_ns"]) - int(event["command_subject_ns"])
            > int(plan["thresholds"]["maximum_command_age_ns"])
        ]
        stale_effects.sort(
            key=lambda value: (int(value["timestamp_ns"]), int(value["sequence"]))
        )
        freshness_start_ns = (
            int(stale_effects[0]["timestamp_ns"]) if stale_effects else None
        )
        transition_windows.append(
            _window(
                "freshness_exposure",
                "OBSERVED" if stale_effects else "NOT_OBSERVED",
                freshness_start_ns,
                authority_end_ns if stale_effects else None,
                int(stale_effects[0]["sequence"]) if stale_effects else None,
                telemetry,
            )
        )

        fault = _first_event(
            events,
            kind="fault_detected",
            start_ns=activation_ns if activation_ns is not None else request_ns,
            end_ns=scope_end_ns,
            route=target,
        )
        fault_ns = int(fault["timestamp_ns"]) if fault else None
        completion = _first_event(
            events,
            kind="completion",
            start_ns=activation_ns if activation_ns is not None else request_ns,
            end_ns=scope_end_ns,
            route=target,
        )
        completion_ns = int(completion["timestamp_ns"]) if completion else None
        successor_anchor = fault_ns if transition["fault_expected"] else completion_ns
        successor = (
            complete_installation(
                events,
                route=expected_route,
                anchor_ns=successor_anchor,
                deadline_ns=scope_end_ns,
            )
            if successor_anchor is not None
            else {"complete": False}
        )
        successor_end_ns = (
            int(successor["completed_at_ns"]) if successor.get("complete") else None
        )
        fault_end_ns = successor_end_ns or (
            authority_end_ns if fault_ns is not None else None
        )
        fault_status = (
            "OBSERVED"
            if fault is not None
            else "MISSING_EXPECTED"
            if transition["fault_expected"]
            else "NOT_APPLICABLE"
        )
        transition_windows.append(
            _window(
                "fault_exposure",
                fault_status,
                fault_ns,
                fault_end_ns,
                int(fault["sequence"]) if fault else None,
                telemetry,
            )
        )
        successor_status = (
            "COMPLETE"
            if successor.get("complete")
            else "INCOMPLETE"
            if successor_anchor is not None
            else "NOT_APPLICABLE"
        )
        transition_windows.append(
            _window(
                "successor_installation",
                successor_status,
                successor_anchor,
                successor_end_ns,
                (
                    int(fault["sequence"])
                    if fault is not None and transition["fault_expected"]
                    else int(completion["sequence"])
                    if completion is not None
                    else None
                ),
                telemetry,
            )
        )
        for item in transition_windows:
            item["transition_sequence"] = request_sequence
            item["target_route"] = target
        windows.extend(transition_windows)
    return windows


def _setpoint_kind(cell_id: str) -> str:
    if "attitude" in cell_id:
        return "attitude"
    if "body-rate" in cell_id:
        return "body_rate"
    return "trajectory"


def _violation_clauses(evaluation: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"oracle": str(oracle["oracle"]), "clause": str(name)}
        for oracle in evaluation["oracles"]
        for name, clause in oracle["clauses"].items()
        if clause.get("status") == "VIOLATION"
    ]


def analyze_record(
    record: Any,
    root: Path,
    *,
    airborne_minimum_height_m: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    telemetry_path = (
        root
        / "runs"
        / record.study_id
        / record.attempt_id
        / "raw"
        / "telemetry.sidecar.jsonl"
    )
    if not telemetry_path.is_file():
        raise PhysicalExecutionError(f"missing telemetry input: {telemetry_path}")
    telemetry = _read_jsonl(telemetry_path)
    wrong_run_ids = sorted(
        {
            str(value.get("run_id"))
            for value in telemetry
            if value.get("run_id") != record.attempt_id
        }
    )
    if wrong_run_ids:
        raise PhysicalExecutionError(
            f"{record.attempt_id} telemetry has inconsistent run IDs: {wrong_run_ids}"
        )
    plan = load_plan(record.plan_path)
    events = read_trace(record.trace_path)
    frozen = load_evaluation(record.frozen_evaluation_path)
    whole_run = physical_metrics(telemetry)
    maximum_height = whole_run.get("maximum_height_above_local_origin_m")
    if maximum_height is None:
        execution_status = "UNKNOWN"
    elif float(maximum_height) >= airborne_minimum_height_m:
        execution_status = "AIRBORNE"
    else:
        execution_status = "NON_AIRBORNE"
    windows = aligned_windows(events, plan, telemetry)
    setpoint_kind = _setpoint_kind(record.cell_id)
    result = {
        "schema_version": "1.0",
        "analysis_kind": "read_only_physical_execution_validity",
        "study_id": record.study_id,
        "attempt_id": record.attempt_id,
        "cell_id": record.cell_id,
        "setpoint_kind": setpoint_kind,
        "physical_execution_status": execution_status,
        "airborne_minimum_height_m": airborne_minimum_height_m,
        "frozen_status": frozen["status"],
        "frozen_violation_clauses": _violation_clauses(frozen),
        "whole_run_physical_metrics": whole_run,
        "transition_instance_count": len(
            {item["transition_sequence"] for item in windows}
        ),
        "aligned_window_count": len(windows),
        "motion_identifiability": (
            "CONSTANT_POSITION_MASKS_REFERENCE_DIFFERENCE_NOT_UPDATE_STARVATION_EFFECT"
            if setpoint_kind == "trajectory"
            else "RETAINED_ATTITUDE_OR_RATE_COMMAND_CAN_CHANGE_PHYSICAL_STATE"
        ),
        "input_digests": {
            "plan": record.plan_digest,
            "trace": record.trace_digest,
            "frozen_evaluation": record.frozen_evaluation_digest,
            "telemetry": file_digest(telemetry_path),
        },
    }
    expanded_windows = [
        {
            "schema_version": "1.0",
            "study_id": record.study_id,
            "attempt_id": record.attempt_id,
            "cell_id": record.cell_id,
            "setpoint_kind": setpoint_kind,
            "physical_execution_status": execution_status,
            **item,
        }
        for item in windows
    ]
    return result, expanded_windows


def _distribution(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "minimum": _round(ordered[0]),
        "median": _round(statistics.median(ordered)),
        "p90_nearest_rank": _round(ordered[math.ceil(0.9 * len(ordered)) - 1]),
        "maximum": _round(ordered[-1]),
    }


def _metric_distribution(
    windows: list[dict[str, Any]], field: str
) -> dict[str, float] | None:
    values = [
        float(item["physical_metrics"][field])
        for item in windows
        if isinstance(item.get("physical_metrics"), dict)
        and item["physical_metrics"].get(field) is not None
    ]
    return _distribution(values)


def summarize(
    results: list[dict[str, Any]],
    windows: list[dict[str, Any]],
    *,
    airborne_minimum_height_m: float,
) -> dict[str, Any]:
    execution_counts = Counter(item["physical_execution_status"] for item in results)
    frozen_counts = Counter(item["frozen_status"] for item in results)
    cross_counts = Counter(
        f"{item['physical_execution_status']}->{item['frozen_status']}"
        for item in results
    )
    non_airborne = [
        item for item in results if item["physical_execution_status"] == "NON_AIRBORNE"
    ]
    airborne = [item for item in results if item["physical_execution_status"] == "AIRBORNE"]
    non_airborne_heights = [
        float(item["whole_run_physical_metrics"]["maximum_height_above_local_origin_m"])
        for item in non_airborne
    ]
    airborne_heights = [
        float(item["whole_run_physical_metrics"]["maximum_height_above_local_origin_m"])
        for item in airborne
    ]
    violation_counts: Counter[str] = Counter()
    for item in non_airborne:
        violation_counts.update(
            f"{clause['oracle']}/{clause['clause']}"
            for clause in item["frozen_violation_clauses"]
        )
    window_summary: dict[str, Any] = {}
    metric_fields = (
        "horizontal_displacement_m",
        "vertical_displacement_m",
        "maximum_distance_from_window_start_m",
        "sampled_path_length_m",
        "peak_horizontal_speed_m_s",
        "peak_absolute_vertical_speed_m_s",
        "peak_tilt_deg",
        "peak_body_rate_rad_s",
    )
    for kind in sorted({item["window_kind"] for item in windows}):
        selected = [item for item in windows if item["window_kind"] == kind]
        airborne_selected = [
            item
            for item in selected
            if item["physical_execution_status"] == "AIRBORNE"
        ]
        window_summary[kind] = {
            "window_count": len(selected),
            "status_counts": dict(Counter(item["window_status"] for item in selected)),
            "airborne_window_count": len(airborne_selected),
            "airborne_calculable_physical_window_count": sum(
                isinstance(item.get("physical_metrics"), dict)
                and item["physical_metrics"].get("status") == "CALCULABLE"
                for item in airborne_selected
            ),
            "airborne_only_metric_distributions": {
                field: _metric_distribution(airborne_selected, field)
                for field in metric_fields
            },
        }
    freshness_by_setpoint: dict[str, Any] = {}
    for setpoint_kind in ("trajectory", "attitude", "body_rate"):
        selected = [
            item
            for item in windows
            if item["window_kind"] == "freshness_exposure"
            and item["window_status"] == "OBSERVED"
            and item["setpoint_kind"] == setpoint_kind
            and item["physical_execution_status"] == "AIRBORNE"
        ]
        freshness_by_setpoint[setpoint_kind] = {
            "observed_window_count": len(selected),
            "maximum_distance_from_window_start_m": _metric_distribution(
                selected, "maximum_distance_from_window_start_m"
            ),
            "horizontal_displacement_m": _metric_distribution(
                selected, "horizontal_displacement_m"
            ),
            "vertical_displacement_m": _metric_distribution(
                selected, "vertical_displacement_m"
            ),
            "peak_horizontal_speed_m_s": _metric_distribution(
                selected, "peak_horizontal_speed_m_s"
            ),
        }
    freshness_by_cell: dict[str, Any] = {}
    observed_airborne_freshness = [
        item
        for item in windows
        if item["window_kind"] == "freshness_exposure"
        and item["window_status"] == "OBSERVED"
        and item["physical_execution_status"] == "AIRBORNE"
    ]
    for cell_id in sorted({item["cell_id"] for item in observed_airborne_freshness}):
        selected = [
            item for item in observed_airborne_freshness if item["cell_id"] == cell_id
        ]
        freshness_by_cell[cell_id] = {
            "observed_window_count": len(selected),
            "maximum_distance_from_window_start_m": _metric_distribution(
                selected, "maximum_distance_from_window_start_m"
            ),
            "horizontal_displacement_m": _metric_distribution(
                selected, "horizontal_displacement_m"
            ),
            "vertical_displacement_m": _metric_distribution(
                selected, "vertical_displacement_m"
            ),
            "peak_absolute_vertical_speed_m_s": _metric_distribution(
                selected, "peak_absolute_vertical_speed_m_s"
            ),
        }
    return {
        "schema_version": "1.0",
        "analysis_kind": "read_only_physical_execution_validity",
        "input_trace_count": len(results),
        "study_counts": dict(Counter(item["study_id"] for item in results)),
        "frozen_status_counts": dict(frozen_counts),
        "physical_execution_status_counts": dict(execution_counts),
        "physical_to_frozen_status_counts": dict(cross_counts),
        "airborne_rule": {
            "metric": "maximum_height_above_local_NED_origin_m",
            "minimum_height_m": airborne_minimum_height_m,
            "requires_rewriting_frozen_gate": False,
        },
        "classification_separation": {
            "largest_non_airborne_height_m": _round(max(non_airborne_heights)),
            "smallest_airborne_height_m": _round(min(airborne_heights)),
            "stable_cutoff_interval_m": {
                "exclusive_lower_bound_m": _round(max(non_airborne_heights)),
                "inclusive_upper_bound_m": _round(min(airborne_heights)),
            },
        },
        "non_airborne": {
            "attempt_count": len(non_airborne),
            "attempts": [
                {
                    "study_id": item["study_id"],
                    "attempt_id": item["attempt_id"],
                    "cell_id": item["cell_id"],
                    "setpoint_kind": item["setpoint_kind"],
                    "maximum_height_m": item["whole_run_physical_metrics"][
                        "maximum_height_above_local_origin_m"
                    ],
                    "frozen_status": item["frozen_status"],
                    "frozen_violation_clauses": item["frozen_violation_clauses"],
                }
                for item in non_airborne
            ],
            "frozen_violation_clause_count": sum(
                len(item["frozen_violation_clauses"]) for item in non_airborne
            ),
            "frozen_violation_clause_counts": dict(violation_counts),
            "cell_counts": dict(Counter(item["cell_id"] for item in non_airborne)),
        },
        "window_summaries": window_summary,
        "freshness_exposure_by_setpoint_kind": freshness_by_setpoint,
        "freshness_exposure_by_cell": freshness_by_cell,
        "interpretation": {
            "changes_frozen_verdict": False,
            "changes_frozen_denominator": False,
            "physical_metrics_are_a_fifth_oracle": False,
            "constant_trajectory_freshness_consequence": (
                "NUMERIC_REFERENCE_DIFFERENCE_MASKED_BUT_UPDATE_STARVATION_EFFECT_OBSERVABLE"
            ),
            "non_airborne_traces_enter_future_physical_effect_estimates": False,
        },
    }


def _write_new(path: Path, value: str) -> None:
    if path.exists():
        raise PhysicalExecutionError(f"refusing to overwrite physical audit output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _load_analysis_plan(path: Path) -> dict[str, Any]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("schema_version") != "1.0":
        raise PhysicalExecutionError("physical audit plan must use schema_version 1.0")
    if plan.get("analysis_kind") != "read_only_physical_execution_validity":
        raise PhysicalExecutionError("unexpected physical audit analysis_kind")
    if int(plan.get("input_trace_count", -1)) != 151:
        raise PhysicalExecutionError("physical audit must bind all 151 admissible traces")
    threshold = plan.get("physical_execution_rule", {}).get(
        "airborne_minimum_height_m"
    )
    if not isinstance(threshold, (int, float)) or float(threshold) <= 0.0:
        raise PhysicalExecutionError("invalid airborne_minimum_height_m")
    return plan


def run(root: Path, output_root: Path, analysis_plan_path: Path) -> dict[str, Any]:
    root = root.resolve()
    output_root = output_root.resolve()
    analysis_plan_path = analysis_plan_path.resolve()
    plan = _load_analysis_plan(analysis_plan_path)
    airborne_minimum_height_m = float(
        plan["physical_execution_rule"]["airborne_minimum_height_m"]
    )
    records = load_frozen_corpus(root)
    results: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []
    for record in records:
        result, aligned = analyze_record(
            record,
            root,
            airborne_minimum_height_m=airborne_minimum_height_m,
        )
        results.append(result)
        windows.extend(aligned)
    summary = summarize(
        results,
        windows,
        airborne_minimum_height_m=airborne_minimum_height_m,
    )
    frozen_studies = {
        "primary_matrix": root / "experiments/motivation_thor_v1/matrix.json",
        "primary_ledger": root / "experiments/motivation_thor_v1/attempt-ledger.jsonl",
        "supplemental_matrix": root
        / "experiments/motivation_thor_remediation_v1/matrix.json",
        "supplemental_ledger": root
        / "experiments/motivation_thor_remediation_v1/attempt-ledger.jsonl",
    }
    manifest_entries = []
    for record in records:
        entry = record.manifest_entry(root)
        telemetry_path = (
            root
            / "runs"
            / record.study_id
            / record.attempt_id
            / "raw"
            / "telemetry.sidecar.jsonl"
        )
        entry["telemetry"] = str(telemetry_path.relative_to(root))
        entry["digests"]["telemetry"] = file_digest(telemetry_path)
        manifest_entries.append(entry)
    manifest = {
        "schema_version": "1.0",
        "analysis_plan": {
            "path": str(analysis_plan_path.relative_to(root)),
            "sha256": file_digest(analysis_plan_path),
        },
        "input_count": len(records),
        "entries": manifest_entries,
        "frozen_study_digests": {
            name: file_digest(path) for name, path in frozen_studies.items()
        },
    }
    _write_new(
        output_root / "input-manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    _write_new(
        output_root / "per-trace.jsonl",
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in results),
    )
    _write_new(
        output_root / "aligned-windows.jsonl",
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in windows),
    )
    _write_new(
        output_root / "summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--analysis-plan", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = run(args.root, args.output_root, args.analysis_plan)
    except (
        CorpusError,
        PhysicalExecutionError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": "PASS", "summary": summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
