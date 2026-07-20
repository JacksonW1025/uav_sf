#!/usr/bin/env python3
"""Evaluate deterministic concurrent authority events against legal serial orders."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "data/schemas/authority_event_linearization_result.schema.json").read_text(
        encoding="utf-8"
    )
)
PAIR_EVENTS = {
    "A": ("external_activation", "gcs_hold"),
    "B": ("external_completion", "gcs_takeover_hold"),
    "C": ("local_process_termination", "gcs_rtl"),
    "D": ("automatic_fallback_installation", "external_reentry_request"),
    "E": ("external_release", "failsafe_clear"),
}
TIMING_MINIMUM_CLEAR_MS = 250.0
TIMING_NEAR_MAXIMUM_MS = 100.0
ROUTE_GAP_MAXIMUM_MS = 24.0


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _ros_to_px4_us(ros_ns: int, bridge: dict[str, Any]) -> float:
    return float(bridge["reference_px4_us"]) + (
        (ros_ns - int(bridge["reference_ros_ns"]))
        / float(bridge["rate_ratio"])
        / 1000.0
    )


def _legal_final_states(pair: str, order: str, external_mode_id: int) -> list[int]:
    hold = 4
    rtl = 5
    if pair == "A":
        return [hold] if order == "A_FIRST" else (
            [external_mode_id] if order == "B_FIRST" else [hold, external_mode_id]
        )
    if pair == "B":
        return [hold]
    if pair == "C":
        return [rtl]
    if pair == "D":
        return [external_mode_id] if order == "A_FIRST" else (
            [rtl] if order == "B_FIRST" else [rtl, external_mode_id]
        )
    if pair == "E":
        return [rtl]
    raise ValueError(f"unknown C1 pair {pair}")


def _clause(status: str, reasons: list[str], metrics: dict[str, Any]) -> dict[str, Any]:
    return {"status": status, "reasons": reasons, "metrics": metrics}


def evaluate(
    runner: dict[str, Any],
    monitor_events: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    bridge: dict[str, Any],
) -> dict[str, Any]:
    pair = str(runner.get("pair"))
    order = str(runner.get("timing_order"))
    run_id = str(runner.get("run_id"))
    external_mode_id = runner.get("external_mode_id")
    clauses: dict[str, dict[str, Any]] = {}
    unknown_reasons: list[str] = []

    if pair not in PAIR_EVENTS or order not in {
        "A_FIRST",
        "NEAR_SIMULTANEOUS",
        "B_FIRST",
    }:
        return {
            "schema_version": "1.0",
            "oracle_name": "Authority Event Linearization Oracle",
            "oracle_version": "0.2",
            "run_id": run_id,
            "pair": pair,
            "timing_order": order,
            "status": "NOT_APPLICABLE",
            "clauses": {},
            "linearization": {},
            "evidence_completeness": {"reason": "unregistered_pair_or_timing_order"},
        }
    if external_mode_id is None:
        unknown_reasons.append("external_mode_id_missing")
    if bridge.get("status") != "VALID":
        unknown_reasons.append("clock_bridge_not_VALID")

    expected_names = PAIR_EVENTS[pair]
    inputs = runner.get("input_events") or []
    by_name = {str(item.get("name")): item for item in inputs}
    missing_inputs = [name for name in expected_names if name not in by_name]
    duplicate_names = len(inputs) != len(by_name)
    observable_status = "PASS" if not missing_inputs and not duplicate_names else "UNKNOWN"
    clauses["input_observability"] = _clause(
        observable_status,
        (["required concurrent lifecycle event is missing"] if missing_inputs else [])
        + (["duplicate pair input events are ambiguous"] if duplicate_names else []),
        {"expected": list(expected_names), "observed": sorted(by_name), "missing": missing_inputs},
    )
    if observable_status == "UNKNOWN":
        unknown_reasons.append("pair_input_evidence_incomplete")

    delta_ms: float | None = None
    timing_status = "UNKNOWN"
    if not missing_inputs and not duplicate_names:
        delta_ms = (
            int(by_name[expected_names[1]]["monotonic_ns"])
            - int(by_name[expected_names[0]]["monotonic_ns"])
        ) / 1_000_000.0
        if order == "A_FIRST":
            timing_status = "PASS" if delta_ms >= TIMING_MINIMUM_CLEAR_MS else "VIOLATION"
        elif order == "B_FIRST":
            timing_status = "PASS" if delta_ms <= -TIMING_MINIMUM_CLEAR_MS else "VIOLATION"
        else:
            timing_status = "PASS" if abs(delta_ms) <= TIMING_NEAR_MAXIMUM_MS else "VIOLATION"
    clauses["relative_timing"] = _clause(
        timing_status,
        [] if timing_status == "PASS" else ["observed input timing does not match the registered slot"],
        {
            "event_b_minus_event_a_ms": delta_ms,
            "clearly_ordered_minimum_ms": TIMING_MINIMUM_CLEAR_MS,
            "near_simultaneous_maximum_ms": TIMING_NEAR_MAXIMUM_MS,
        },
    )
    if timing_status == "VIOLATION":
        # Relative order is a registered scenario precondition. A harness miss
        # is excluded from the SUT denominator instead of becoming a finding.
        unknown_reasons.append("registered_relative_timing_precondition_not_satisfied")

    close_events = [
        event for event in monitor_events if event.get("event_type") == "linearization_window_closed"
    ]
    if len(close_events) != 1:
        unknown_reasons.append("linearization_window_close_missing_or_ambiguous")
    window_start_us: float | None = None
    window_end_us: float | None = None
    if not missing_inputs and bridge.get("status") == "VALID" and len(close_events) == 1:
        window_start_us = _ros_to_px4_us(
            min(int(item["ros_time_ns"]) for item in by_name.values()), bridge
        )
        window_end_us = _ros_to_px4_us(int(close_events[0]["ros_time_ns"]), bridge)
        valid_from = bridge.get("valid_from")
        valid_until = bridge.get("valid_until")
        if valid_from is not None and window_start_us < float(valid_from):
            unknown_reasons.append("pair_window_starts_before_clock_bridge")
        if valid_until is not None and window_end_us > float(valid_until):
            unknown_reasons.append("pair_window_ends_after_clock_bridge")

    final_snapshot = runner.get("linearization_final") or {}
    final_nav_state = final_snapshot.get("nav_state")
    legal_states = (
        _legal_final_states(pair, order, int(external_mode_id))
        if external_mode_id is not None
        else []
    )
    final_status = (
        "UNKNOWN" if final_nav_state is None or not legal_states
        else ("PASS" if int(final_nav_state) in legal_states else "VIOLATION")
    )
    clauses["linearizable_final_route"] = _clause(
        final_status,
        [] if final_status == "PASS" else ["final route is not equivalent to a legal serial order"],
        {"observed_nav_state": final_nav_state, "legal_final_nav_states": legal_states},
    )

    pair_trace: list[dict[str, Any]] = []
    route_context: list[dict[str, Any]] = []
    effective_window_start_us: float | None = None
    effective_window_end_us: float | None = None
    if window_start_us is not None and window_end_us is not None:
        uncertainty_us = float(bridge.get("uncertainty_ns") or 0) / 1000.0
        effective_window_start_us = window_start_us + uncertainty_us
        effective_window_end_us = window_end_us - uncertainty_us
        if effective_window_start_us >= effective_window_end_us:
            unknown_reasons.append("clock_uncertainty_consumes_pair_window")
        pair_trace = [
            event
            for event in trace
            if effective_window_start_us
            <= float(event.get("timestamp", -1))
            <= effective_window_end_us
        ]
        # Some pairs begin after a required precondition has installed the route
        # that remains final (for example C1-E). Retain a bounded precondition
        # window for lineage adjudication without admitting unrelated history.
        route_context = [
            event
            for event in trace
            if window_start_us - 500_000
            <= float(event.get("timestamp", -1))
            <= effective_window_end_us
        ]
    route_changes = [
        event for event in route_context if event.get("event_type") == "route_epoch_changed"
    ]
    outputs = [event for event in pair_trace if event.get("event_type") == "actuator_output_published"]
    if not pair_trace or not route_changes or not outputs:
        unknown_reasons.append("critical_route_or_writer_window_incomplete")

    executor_value = final_snapshot.get("executor_in_charge")
    executor_explainable = (
        executor_value is not None
        and final_nav_state is not None
        and int(executor_value) == 0
    )
    clauses["owner_uniqueness"] = _clause(
        "PASS" if executor_explainable else (
            "UNKNOWN" if executor_value is None or final_nav_state is None else "VIOLATION"
        ),
        [] if executor_explainable else [
            "final authority or executor owner is missing or inconsistent with the public-command probe"
        ],
        {
            "final_nav_state": final_nav_state,
            "executor_in_charge": executor_value,
            "expected_executor_in_charge": 0,
            "probe_registers_mode_executor": False,
        },
    )

    old_lineage_count = 0
    last_final_route_time: float | None = None
    final_epoch: int | None = None
    for event in route_changes:
        if final_nav_state is not None and int(event.get("declared_mode", -1)) == int(final_nav_state):
            last_final_route_time = float(event["timestamp"])
            final_epoch = int(event["route_epoch_id"])
    if last_final_route_time is not None and final_epoch is not None:
        for event in pair_trace:
            if float(event.get("timestamp", -1)) <= last_final_route_time:
                continue
            if event.get("event_type") not in {
                "px4_setpoint_consumed",
                "allocator_input_published",
                "actuator_output_published",
            }:
                continue
            if int(event.get("route_epoch_id", final_epoch)) != final_epoch:
                old_lineage_count += 1
    lineage_status = "UNKNOWN" if last_final_route_time is None else (
        "PASS" if old_lineage_count == 0 else "VIOLATION"
    )
    clauses["final_revocation_lineage"] = _clause(
        lineage_status,
        [] if lineage_status == "PASS" else ["source command lineage crosses final route revocation"],
        {
            "final_route_epoch_id": final_epoch,
            "post_final_old_epoch_control_events": old_lineage_count,
        },
    )

    writers_by_time: dict[int, set[str]] = defaultdict(set)
    for event in outputs:
        writer = event.get("actuator_writer")
        if writer:
            writers_by_time[int(float(event["timestamp"]))].add(str(writer))
    overlap_count = sum(len(writers) > 1 for writers in writers_by_time.values())
    output_times = sorted(writers_by_time)
    maximum_gap_ms = max(
        ((right - left) / 1000.0 for left, right in zip(output_times, output_times[1:])),
        default=None,
    )
    writer_status = "UNKNOWN" if not output_times else (
        "PASS"
        if overlap_count == 0
        and maximum_gap_ms is not None
        and maximum_gap_ms <= ROUTE_GAP_MAXIMUM_MS
        else "VIOLATION"
    )
    clauses["writer_exclusivity_and_continuity"] = _clause(
        writer_status,
        [] if writer_status == "PASS" else ["writer overlap or route gap exceeds the registered bound"],
        {
            "competing_writer_timestamp_count": overlap_count,
            "maximum_writer_gap_ms": maximum_gap_ms,
            "allowed_gap_ms": ROUTE_GAP_MAXIMUM_MS,
            "writer_event_count": len(outputs),
        },
    )

    cleanup = runner.get("cleanup") or {}
    cleanup_status = "PASS" if cleanup.get("landed") and cleanup.get("disarmed") else "UNKNOWN"
    clauses["cleanup"] = _clause(
        cleanup_status,
        [] if cleanup_status == "PASS" else ["Land/Disarm cleanup evidence is incomplete"],
        {"landed": cleanup.get("landed"), "disarmed": cleanup.get("disarmed")},
    )
    if runner.get("status") != "PASS":
        unknown_reasons.append("scenario_monitor_not_PASS")

    statuses = [clause["status"] for clause in clauses.values()]
    if "UNKNOWN" in statuses or unknown_reasons:
        status = "UNKNOWN"
    elif "VIOLATION" in statuses:
        status = "VIOLATION"
    else:
        status = "PASS"
    result = {
        "schema_version": "1.0",
        "oracle_name": "Authority Event Linearization Oracle",
        "oracle_version": "0.2",
        "run_id": run_id,
        "pair": pair,
        "timing_order": order,
        "status": status,
        "clauses": clauses,
        "linearization": {
            "event_a": expected_names[0],
            "event_b": expected_names[1],
            "event_b_minus_event_a_ms": delta_ms,
            "observed_final_nav_state": final_nav_state,
            "legal_final_nav_states": legal_states,
        },
        "evidence_completeness": {
            "clock_bridge": bridge.get("status"),
            "window_start_us": window_start_us,
            "window_end_us": window_end_us,
            "clock_uncertainty_us": (
                float(bridge.get("uncertainty_ns") or 0) / 1000.0
                if bridge.get("status") == "VALID"
                else None
            ),
            "effective_window_start_us": effective_window_start_us,
            "effective_window_end_us": effective_window_end_us,
            "route_change_count": len(route_changes),
            "writer_event_count": len(outputs),
            "unknown_reasons": sorted(set(unknown_reasons)),
        },
    }
    Draft202012Validator(SCHEMA).validate(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-result", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--clock-bridge", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.runner_result.read_text(encoding="utf-8")),
        _jsonl(args.events),
        _jsonl(args.trace),
        json.loads(args.clock_bridge.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
