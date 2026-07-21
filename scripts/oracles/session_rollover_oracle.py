#!/usr/bin/env python3
"""Evaluate old/new External Mode session isolation from offline evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "data/schemas/session_rollover_result.schema.json").read_text(encoding="utf-8")
)
STRUCTURED = re.compile(r"\[(?P<timestamp>[0-9]+(?:\.[0-9]+)?)\].*?(?P<json>\{\"event_type\".*\})")
CONTROL_EVENTS = {
    "px4_setpoint_consumed",
    "allocator_input_published",
    "actuator_output_published",
}
IDENTITY_KEYS = (
    "registration_request_id",
    "registration_reply_request_id",
    "registration_instance_id",
    "producer_session_id",
    "activation_id",
    "activation_key",
    "mode_id",
    "executor_id",
)
CONTRACT_CLASSIFICATION = "B_IMPLIED_OWNERSHIP_PROGRESSION_CONTRACT"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _lifecycle(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = STRUCTURED.search(line)
        if not match:
            continue
        payload = json.loads(match.group("json"))
        payload["ros_time_ns"] = int(float(match.group("timestamp")) * 1_000_000_000)
        records.append(payload)
    return records


def _ros_to_px4_us(ros_ns: int, bridge: dict[str, Any]) -> float:
    return float(bridge["reference_px4_us"]) + (
        (ros_ns - int(bridge["reference_ros_ns"]))
        / float(bridge["rate_ratio"])
        / 1000.0
    )


def _clause(status: str, reasons: list[str], metrics: dict[str, Any]) -> dict[str, Any]:
    return {"status": status, "reasons": sorted(set(reasons)), "metrics": metrics}


def _events(
    records: list[dict[str, Any]], event_type: str, role: str | None = None
) -> list[dict[str, Any]]:
    matches = [record for record in records if record.get("event_type") == event_type]
    if role is not None:
        matches = [record for record in matches if record.get("session_role") == role]
    return matches


def _last(
    records: list[dict[str, Any]], event_type: str, role: str | None = None
) -> dict[str, Any] | None:
    matches = _events(records, event_type, role)
    return matches[-1] if matches else None


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _epoch_at(trace: list[dict[str, Any]], timestamp_us: float | None) -> int | None:
    if timestamp_us is None:
        return None
    changes = [
        event
        for event in trace
        if event.get("event_type") == "route_epoch_changed"
        and float(event.get("timestamp", -1)) <= timestamp_us
        and event.get("route_epoch_id") is not None
    ]
    if not changes:
        return None
    return int(max(changes, key=lambda event: float(event["timestamp"]))["route_epoch_id"])


def _successor_epoch(
    trace: list[dict[str, Any]], after_us: float | None, expected_nav_state: int
) -> int | None:
    if after_us is None:
        return None
    changes = [
        event
        for event in trace
        if event.get("event_type") == "route_epoch_changed"
        and float(event.get("timestamp", -1)) >= after_us
        and _as_int(event.get("declared_mode")) == expected_nav_state
        and event.get("route_epoch_id") is not None
    ]
    if not changes:
        return None
    return int(min(changes, key=lambda event: float(event["timestamp"]))["route_epoch_id"])


def _session_identity(
    role: str,
    runner: dict[str, Any],
    monitor_events: list[dict[str, Any]],
    lifecycle: list[dict[str, Any]],
) -> dict[str, Any]:
    session = runner.get(f"{role}_session") or {}
    request = _last(monitor_events, "r1_registration_request_observed", role)
    reply = _last(monitor_events, "r1_registration_observed", role)
    registered = _last(lifecycle, "external_mode_registered")
    activated = _last(lifecycle, "external_mode_activated")

    producer_session_id = (
        registered.get("producer_session_id") if registered else session.get("producer_session_id")
    )
    registration_instance_id = (
        _as_int(registered.get("registration_instance_id"))
        if registered
        else _as_int(session.get("registration_instance_id"))
    )
    activation_id = (
        _as_int(activated.get("activation_id"))
        if activated
        else _as_int(session.get("activation_id"))
    )
    activation_key = None
    if (
        producer_session_id is not None
        and registration_instance_id is not None
        and activation_id is not None
    ):
        activation_key = f"{producer_session_id}:{registration_instance_id}:{activation_id}"

    identity = {
        "registration_request_id": _as_int(
            request.get("request_id") if request else session.get("registration_request_id")
        ),
        "registration_reply_request_id": _as_int(
            reply.get("request_id") if reply else session.get("registration_reply_request_id")
        ),
        "registration_instance_id": registration_instance_id,
        "producer_session_id": str(producer_session_id) if producer_session_id is not None else None,
        "activation_id": activation_id,
        "activation_key": activation_key,
        "mode_id": _as_int(
            registered.get("mode_id")
            if registered
            else (reply.get("mode_id") if reply else session.get("mode_id"))
        ),
        "executor_id": _as_int(
            reply.get("executor_id") if reply else session.get("executor_id")
        ),
    }
    assert set(identity) == set(IDENTITY_KEYS)
    return identity


def _not_applicable_result(
    run_id: str,
    bridge: dict[str, Any],
    trace: list[dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    empty_identity = {key: None for key in IDENTITY_KEYS}
    result = {
        "schema_version": "1.0",
        "oracle_name": "Session Rollover Oracle",
        "oracle_version": "0.1",
        "contract_classification": CONTRACT_CLASSIFICATION,
        "run_id": run_id,
        "scenario": "A",
        "selected_semantic": None,
        "status": "NOT_APPLICABLE",
        "clauses": {
            "session_relation": _clause("NOT_APPLICABLE", [reason], {})
        },
        "identities": {"old": empty_identity, "new": dict(empty_identity), "relation_established": False},
        "route_epochs": {"old": None, "new": None, "successor": None},
        "completion": {
            "provenance": "NONE",
            "wire_fields": ["timestamp", "result", "nav_state"],
            "wire_instance_or_generation_fields": [],
            "released_once": None,
            "observed": None,
            "new_lifecycle_progressed": None,
            "successor_request_observed": None,
            "successor_installation_epoch": None,
        },
        "evidence_completeness": {
            "clock_bridge": bridge.get("status"),
            "clock_sample_count": 0,
            "new_window_start_us": None,
            "window_end_us": None,
            "trace_event_count": len(trace),
            "observations": {},
            "unknown_reasons": [],
        },
    }
    Draft202012Validator(SCHEMA).validate(result)
    return result


def evaluate(
    runner: dict[str, Any],
    monitor_events: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    bridge: dict[str, Any],
    old_lifecycle: list[dict[str, Any]],
    new_lifecycle: list[dict[str, Any]],
) -> dict[str, Any]:
    scenario = str(runner.get("scenario"))
    run_id = str(runner.get("run_id"))
    if scenario not in {"A", "B", "C"}:
        return _not_applicable_result(run_id, bridge, trace, "unregistered_scenario")

    selected_semantic = "ModeCompleted" if scenario == "C" else None
    clauses: dict[str, dict[str, Any]] = {}
    unknown_reasons: list[str] = []

    old_identity = _session_identity("old", runner, monitor_events, old_lifecycle)
    new_identity = _session_identity("new", runner, monitor_events, new_lifecycle)
    identity_complete = all(
        identity[key] is not None
        for identity in (old_identity, new_identity)
        for key in IDENTITY_KEYS
    )
    old_correlated = (
        old_identity["registration_request_id"] is not None
        and old_identity["registration_request_id"]
        == old_identity["registration_reply_request_id"]
    )
    new_correlated = (
        new_identity["registration_request_id"] is not None
        and new_identity["registration_request_id"]
        == new_identity["registration_reply_request_id"]
    )
    if not identity_complete:
        registration_status = "UNKNOWN"
        registration_reasons = ["old/new registration, activation, or producer-session identity is incomplete"]
    elif not old_correlated or not new_correlated:
        registration_status = "VIOLATION"
        registration_reasons = ["a registration reply does not correlate to its request_id"]
    else:
        registration_status = "PASS"
        registration_reasons = []
    clauses["registration_and_activation_identity"] = _clause(
        registration_status,
        registration_reasons,
        {
            "identity_complete": identity_complete,
            "old_request_reply_correlated": old_correlated,
            "new_request_reply_correlated": new_correlated,
            "numeric_mode_id_reused": old_identity["mode_id"] == new_identity["mode_id"],
            "numeric_executor_id_reused": old_identity["executor_id"] == new_identity["executor_id"],
        },
    )

    relation_established: bool | None = None
    if identity_complete and old_correlated and new_correlated:
        relation_established = all(
            old_identity[key] != new_identity[key]
            for key in (
                "registration_request_id",
                "registration_instance_id",
                "producer_session_id",
                "activation_key",
            )
        )
    if relation_established is None:
        relation_status = "UNKNOWN"
        relation_reasons = ["the required earlier/new session relation is incomplete"]
    elif not relation_established:
        relation_status = "NOT_APPLICABLE"
        relation_reasons = ["complete evidence does not establish distinct earlier and new sessions"]
    else:
        relation_status = "PASS"
        relation_reasons = []
    clauses["session_relation"] = _clause(
        relation_status,
        relation_reasons,
        {"distinct_session_relation_established": relation_established},
    )

    old_snapshot = _last(monitor_events, "old_session_active_snapshot")
    new_snapshot = _last(monitor_events, "new_session_active_snapshot")
    close_event = _last(monitor_events, "r1_isolation_window_closed")
    release_event = _last(monitor_events, "old_session_message_released_once")
    old_snapshot_us: float | None = None
    new_snapshot_us: float | None = None
    close_us: float | None = None
    release_us: float | None = None
    if bridge.get("status") == "VALID" and old_snapshot and new_snapshot and close_event:
        old_snapshot_us = _ros_to_px4_us(int(old_snapshot["ros_time_ns"]), bridge)
        new_snapshot_us = _ros_to_px4_us(int(new_snapshot["ros_time_ns"]), bridge)
        close_us = _ros_to_px4_us(int(close_event["ros_time_ns"]), bridge)
        if release_event is not None:
            release_us = _ros_to_px4_us(int(release_event["ros_time_ns"]), bridge)
    else:
        unknown_reasons.append("clock_bridge_or_rollover_markers_incomplete")

    old_epoch = _epoch_at(trace, old_snapshot_us)
    new_epoch = _epoch_at(trace, new_snapshot_us)
    if old_epoch is None or new_epoch is None:
        epoch_status = "UNKNOWN"
        epoch_reasons = ["source or target route epoch is missing"]
    elif old_epoch == new_epoch:
        epoch_status = "VIOLATION"
        epoch_reasons = ["new activation did not enter a distinct route epoch"]
    else:
        epoch_status = "PASS"
        epoch_reasons = []
    clauses["route_epoch_rollover"] = _clause(
        epoch_status,
        epoch_reasons,
        {"source_route_epoch_id": old_epoch, "target_route_epoch_id": new_epoch},
    )

    old_stop_ns = (runner.get("old_session") or {}).get("stop_monotonic_ns")
    if old_stop_ns is None:
        stopped = _last(monitor_events, "r1_component_stopped", "old")
        old_stop_ns = stopped.get("monotonic_ns") if stopped else None
    new_active_ns = (runner.get("new_session") or {}).get("active_monotonic_ns")
    if new_active_ns is None and new_snapshot is not None:
        new_active_ns = new_snapshot.get("monotonic_ns")
    old_post_new_events = [
        record
        for record in old_lifecycle
        if new_snapshot is not None
        and int(record.get("ros_time_ns", 0)) > int(new_snapshot["ros_time_ns"])
        and record.get("event_type")
        in {"external_mode_activated", "external_mode_setpoint", "executor_result"}
    ]
    new_owner_at_activation = (
        new_snapshot is not None
        and new_identity["mode_id"] is not None
        and _as_int(new_snapshot.get("mode_id")) == new_identity["mode_id"]
        and new_identity["executor_id"] is not None
        and _as_int(new_snapshot.get("executor_in_charge")) == new_identity["executor_id"]
    )
    owner_evidence_complete = old_stop_ns is not None and new_active_ns is not None and new_snapshot is not None
    if not owner_evidence_complete or not new_owner_at_activation:
        owner_status = "UNKNOWN"
        owner_reasons = ["old revocation or new lifecycle/executor ownership evidence is incomplete"]
    elif old_post_new_events:
        owner_status = "VIOLATION"
        owner_reasons = ["the earlier producer emitted authority-bearing lifecycle events after new activation"]
    else:
        owner_status = "PASS"
        owner_reasons = []
    clauses["lifecycle_owner_rollover"] = _clause(
        owner_status,
        owner_reasons,
        {
            "old_stop_observed": old_stop_ns is not None,
            "new_activation_observed": new_active_ns is not None,
            "new_owner_at_activation": new_owner_at_activation,
            "old_authority_events_after_new_activation": len(old_post_new_events),
        },
    )

    raw_completion = runner.get("completion_event") or runner.get("old_session_message") or {}
    provenance = str(raw_completion.get("provenance", "NONE"))
    if scenario == "C" and provenance == "NONE":
        associated_session = raw_completion.get("producer_session_id")
        if associated_session == old_identity["producer_session_id"]:
            provenance = "EARLIER_SESSION"
        elif associated_session == new_identity["producer_session_id"]:
            provenance = "NEW_SESSION"
    if provenance not in {"EARLIER_SESSION", "NEW_SESSION", "AMBIGUOUS", "NONE"}:
        provenance = "AMBIGUOUS"

    released_once: bool | None
    if scenario == "C":
        released_once = bool(
            raw_completion.get("released_once")
            or raw_completion.get("release_count") == 1
        )
        observed = bool(
            raw_completion.get("observed", raw_completion.get("relayed_observation", False))
        )
        progressed = bool(raw_completion.get("new_lifecycle_progressed", False))
    else:
        released_once = observed = progressed = None

    successor_requested = bool(raw_completion.get("successor_request_observed", False))
    if _last(new_lifecycle, "executor_successor_requested") is not None:
        successor_requested = True
    expected_successor = _as_int(runner.get("expected_successor_nav_state")) or 5
    successor_epoch = (
        _successor_epoch(trace, release_us, expected_successor)
        if scenario == "C" and progressed
        else None
    )

    if scenario != "C":
        completion_status = "NOT_APPLICABLE"
        completion_reasons = ["ModeCompleted is preregistered only for R1-C"]
    elif not released_once or not observed or provenance == "NONE":
        completion_status = "UNKNOWN"
        completion_reasons = ["completion release, observation, or generation provenance is incomplete"]
    elif progressed and (not successor_requested or successor_epoch is None):
        completion_status = "UNKNOWN"
        completion_reasons = ["lifecycle progression lacks complete successor request/installation evidence"]
    elif provenance == "AMBIGUOUS":
        completion_status = "EXPOSURE"
        completion_reasons = [
            "ModeCompleted lacks instance/generation identity and provenance remains ambiguous"
        ]
    elif provenance == "EARLIER_SESSION" and progressed:
        completion_status = "VIOLATION"
        completion_reasons = [
            "a completion associated with the earlier producer session progressed the new lifecycle"
        ]
    else:
        completion_status = "PASS"
        completion_reasons = []
    clauses["completion_session_isolation"] = _clause(
        completion_status,
        completion_reasons,
        {
            "generation_provenance": provenance,
            "wire_fields": ["timestamp", "result", "nav_state"],
            "wire_instance_or_generation_fields": [],
            "released_once": released_once,
            "observed": observed,
            "new_lifecycle_progressed": progressed,
        },
    )

    if scenario != "C" or not progressed:
        successor_status = "NOT_APPLICABLE"
        successor_reasons = ["no completion-driven successor progression is applicable"]
    elif successor_requested and successor_epoch is not None:
        successor_status = "PASS"
        successor_reasons = []
    else:
        successor_status = "UNKNOWN"
        successor_reasons = ["successor request or installation evidence is missing"]
    clauses["successor_progression"] = _clause(
        successor_status,
        successor_reasons,
        {
            "expected_successor_nav_state": expected_successor,
            "successor_request_observed": successor_requested,
            "successor_installation_epoch": successor_epoch,
        },
    )

    new_window_trace = [
        event
        for event in trace
        if new_snapshot_us is not None
        and close_us is not None
        and new_snapshot_us <= float(event.get("timestamp", -1)) <= close_us
        and event.get("event_type") in CONTROL_EVENTS
    ]
    old_lineage = [
        event
        for event in new_window_trace
        if old_epoch is not None and _as_int(event.get("route_epoch_id")) == old_epoch
    ]
    event_kinds = {str(event.get("event_type")) for event in new_window_trace}
    active_graph = new_snapshot.get("controller_graph") if new_snapshot else None
    close_graph = runner.get("controller_graph_at_close")
    if close_graph is None and close_event is not None:
        close_graph = close_event.get("controller_graph")
    graph_complete = isinstance(active_graph, dict) and isinstance(close_graph, dict)
    controller_events_present = "px4_setpoint_consumed" in event_kinds
    if not graph_complete or not controller_events_present:
        controller_status = "UNKNOWN"
        controller_reasons = ["controller graph or controller-consumption lineage is incomplete"]
    elif old_lineage:
        controller_status = "VIOLATION"
        controller_reasons = ["old route epoch appears in the new controller window"]
    elif not progressed and active_graph != close_graph:
        controller_status = "VIOLATION"
        controller_reasons = ["new controller graph changed without lifecycle progression"]
    else:
        controller_status = "PASS"
        controller_reasons = []
    clauses["controller_lineage_isolation"] = _clause(
        controller_status,
        controller_reasons,
        {
            "new_active_graph": active_graph,
            "window_close_graph": close_graph,
            "controller_events": sum(
                event.get("event_type") == "px4_setpoint_consumed" for event in new_window_trace
            ),
            "old_epoch_control_events": len(old_lineage),
        },
    )

    allocator_present = "allocator_input_published" in event_kinds
    writer_present = "actuator_output_published" in event_kinds
    if not allocator_present or not writer_present:
        lineage_status = "UNKNOWN"
        lineage_reasons = ["allocator or writer lineage is incomplete"]
    elif old_lineage:
        lineage_status = "VIOLATION"
        lineage_reasons = ["old route epoch appears in the new allocator/writer window"]
    else:
        lineage_status = "PASS"
        lineage_reasons = []
    clauses["allocator_writer_lineage_isolation"] = _clause(
        lineage_status,
        lineage_reasons,
        {
            "new_window_control_events": len(new_window_trace),
            "allocator_events_present": allocator_present,
            "writer_events_present": writer_present,
            "old_epoch_control_events": len(old_lineage),
        },
    )

    cleanup = runner.get("cleanup") or {}
    cleanup_complete = cleanup.get("landed") is True and cleanup.get("disarmed") is True
    clauses["cleanup"] = _clause(
        "PASS" if cleanup_complete else "UNKNOWN",
        [] if cleanup_complete else ["Land/Disarm cleanup is incomplete"],
        {"landed": cleanup.get("landed"), "disarmed": cleanup.get("disarmed")},
    )

    if runner.get("status") != "PASS":
        unknown_reasons.append("scenario_monitor_not_PASS")
    if bridge.get("status") != "VALID":
        unknown_reasons.append("clock_bridge_not_VALID")
    if int(runner.get("clock_sample_count", 0)) < 20:
        unknown_reasons.append("clock_sample_count_below_20")
    valid_from = bridge.get("valid_from")
    valid_until = bridge.get("valid_until")
    if new_snapshot_us is not None and valid_from is not None and new_snapshot_us < float(valid_from):
        unknown_reasons.append("new_window_starts_before_clock_bridge")
    if close_us is not None and valid_until is not None and close_us > float(valid_until):
        unknown_reasons.append("window_ends_after_clock_bridge")

    applicable = [clause["status"] for clause in clauses.values() if clause["status"] != "NOT_APPLICABLE"]
    if relation_established is False:
        status = "NOT_APPLICABLE"
    elif "UNKNOWN" in applicable or unknown_reasons:
        status = "UNKNOWN"
    elif "VIOLATION" in applicable:
        status = "VIOLATION"
    elif "EXPOSURE" in applicable:
        status = "EXPOSURE"
    else:
        status = "PASS"

    observations = {
        "old_registration_identity": all(old_identity[key] is not None for key in IDENTITY_KEYS[:4]),
        "new_registration_identity": all(new_identity[key] is not None for key in IDENTITY_KEYS[:4]),
        "old_activation_identity": old_identity["activation_key"] is not None,
        "new_activation_identity": new_identity["activation_key"] is not None,
        "producer_session_identity": (
            old_identity["producer_session_id"] is not None
            and new_identity["producer_session_id"] is not None
        ),
        "source_and_target_route_epoch": old_epoch is not None and new_epoch is not None,
        "completion_generation_provenance": scenario != "C" or provenance != "NONE",
        "completion_observation": scenario != "C" or observed is True,
        "executor_lifecycle_progression": scenario != "C" or progressed is not None,
        "successor_request_and_installation": (
            scenario != "C" or not progressed or (successor_requested and successor_epoch is not None)
        ),
        "controller_lineage": graph_complete and controller_events_present,
        "allocator_lineage": allocator_present,
        "writer_lineage": writer_present,
        "land_disarm_cleanup": cleanup_complete,
    }
    result = {
        "schema_version": "1.0",
        "oracle_name": "Session Rollover Oracle",
        "oracle_version": "0.1",
        "contract_classification": CONTRACT_CLASSIFICATION,
        "run_id": run_id,
        "scenario": scenario,
        "selected_semantic": selected_semantic,
        "status": status,
        "clauses": clauses,
        "identities": {
            "old": old_identity,
            "new": new_identity,
            "relation_established": relation_established,
        },
        "route_epochs": {"old": old_epoch, "new": new_epoch, "successor": successor_epoch},
        "completion": {
            "provenance": provenance,
            "wire_fields": ["timestamp", "result", "nav_state"],
            "wire_instance_or_generation_fields": [],
            "released_once": released_once,
            "observed": observed,
            "new_lifecycle_progressed": progressed,
            "successor_request_observed": successor_requested if scenario == "C" else None,
            "successor_installation_epoch": successor_epoch,
        },
        "evidence_completeness": {
            "clock_bridge": bridge.get("status"),
            "clock_sample_count": int(runner.get("clock_sample_count", 0)),
            "new_window_start_us": new_snapshot_us,
            "window_end_us": close_us,
            "trace_event_count": len(trace),
            "observations": observations,
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
    parser.add_argument("--old-lifecycle-log", type=Path, required=True)
    parser.add_argument("--new-lifecycle-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.runner_result.read_text(encoding="utf-8")),
        _jsonl(args.events),
        _jsonl(args.trace),
        json.loads(args.clock_bridge.read_text(encoding="utf-8")),
        _lifecycle(args.old_lifecycle_log),
        _lifecycle(args.new_lifecycle_log),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
