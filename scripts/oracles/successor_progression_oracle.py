#!/usr/bin/env python3
"""Evaluate External Mode ownership, completion, successor, and terminal progress."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
EVENT_SCHEMA_PATH = ROOT / "data" / "schemas" / "successor_lifecycle_event.schema.json"
RESULT_SCHEMA_PATH = ROOT / "data" / "schemas" / "successor_oracle_result.schema.json"
STRUCTURED_LOG_EVENT = re.compile(
    r"\[(?P<timestamp>[0-9]+(?:\.[0-9]+)?)\].*?(?P<json>\{\"event_type\".*\})"
)
STATUSES = {"PASS", "VIOLATION", "UNKNOWN", "NOT_APPLICABLE"}


def _clause(
    status: str,
    *reasons: str,
    evidence: dict[str, object] | None = None,
) -> dict[str, object]:
    assert status in STATUSES
    return {"status": status, "reasons": list(reasons), "evidence": evidence or {}}


def load_lifecycle_events(path: Path) -> list[dict[str, Any]]:
    schema = json.loads(EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            event = json.loads(line)
            errors = sorted(validator.iter_errors(event), key=lambda error: list(error.path))
            if errors:
                raise ValueError(f"invalid lifecycle event line {line_number}: {errors[0].message}")
            events.append(event)
    return sorted(events, key=lambda event: int(event["ros_time_ns"]))


def load_executor_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = STRUCTURED_LOG_EVENT.search(line)
            if not match:
                continue
            payload = json.loads(match.group("json"))
            payload["ros_time_ns"] = int(float(match.group("timestamp")) * 1_000_000_000)
            events.append(payload)
    return sorted(events, key=lambda event: int(event["ros_time_ns"]))


def load_route_events(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _first(
    events: Iterable[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]
) -> dict[str, Any] | None:
    return next((event for event in events if predicate(event)), None)


def _event_type(event: dict[str, Any], expected: str) -> bool:
    return str(event.get("event_type")) == expected


def _details(event: dict[str, Any]) -> dict[str, Any]:
    details = event.get("details")
    return details if isinstance(details, dict) else {}


def _after(events: Iterable[dict[str, Any]], timestamp_ns: int) -> list[dict[str, Any]]:
    return [event for event in events if int(event["ros_time_ns"]) >= timestamp_ns]


def _monitor_complete(events: list[dict[str, Any]]) -> tuple[bool, str | None]:
    finished = _first(events, lambda event: _event_type(event, "monitor_finished"))
    if finished is None:
        return False, None
    status = _details(finished).get("status")
    return True, str(status) if status is not None else None


def evaluate(
    profile: dict[str, Any],
    lifecycle_events: list[dict[str, Any]],
    executor_events: list[dict[str, Any]],
    route_events: list[dict[str, Any]],
    route_oracle: dict[str, Any] | None,
    clock_bridge: dict[str, Any] | None,
    *,
    inputs: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    if profile.get("applicability") == "NOT_APPLICABLE":
        clauses = {
            name: _clause("NOT_APPLICABLE", "profile is explicitly not applicable")
            for name in (
                "ownership",
                "completion",
                "successor_request",
                "successor_installation",
                "mission_progression",
            )
        }
        return _result(profile, lifecycle_events, clauses, [], {}, inputs)

    run_ids = {str(event["run_id"]) for event in lifecycle_events}
    run_id = next(iter(run_ids)) if len(run_ids) == 1 else "unknown"
    monitor_complete, monitor_status = _monitor_complete(lifecycle_events)
    registration = _first(
        lifecycle_events, lambda event: _event_type(event, "registration_observed")
    )
    registered_mode_id = (
        int(registration["registered_mode_id"])
        if registration is not None and registration.get("registered_mode_id") is not None
        else None
    )
    registered_executor_id = (
        int(registration["registered_executor_id"])
        if registration is not None and registration.get("registered_executor_id") is not None
        else None
    )
    active_external = _first(
        lifecycle_events,
        lambda event: _event_type(event, "vehicle_status_observed")
        and registered_mode_id is not None
        and event.get("active_mode") == registered_mode_id,
    )

    categories: list[str] = []
    if registration is None or registered_mode_id is None or registered_executor_id is None:
        ownership = _clause("UNKNOWN", "successful mode/executor registration evidence is missing")
    elif active_external is None:
        ownership = _clause("UNKNOWN", "registered owned external mode activation was not observed")
    elif active_external.get("executor_in_charge") != registered_executor_id:
        ownership = _clause(
            "VIOLATION",
            "active owned external mode does not have its registered executor in charge",
            evidence={
                "active_mode": registered_mode_id,
                "expected_executor": registered_executor_id,
                "observed_executor": active_external.get("executor_in_charge"),
                "timestamp_ns": active_external["ros_time_ns"],
            },
        )
        categories.append("EXECUTOR_NOT_IN_CHARGE")
    else:
        ownership = _clause(
            "PASS",
            evidence={
                "active_mode": registered_mode_id,
                "executor_in_charge": registered_executor_id,
                "timestamp_ns": active_external["ros_time_ns"],
            },
        )

    completion_profile = profile["completion"]
    generated = _first(
        executor_events,
        lambda event: _event_type(event, str(completion_profile["generated_event_type"])),
    )
    public_completion = _first(
        lifecycle_events,
        lambda event: _event_type(event, str(completion_profile["public_event_type"]))
        and registered_mode_id is not None
        and _details(event).get("nav_state") == registered_mode_id
        and _details(event).get("result") == completion_profile["public_success_result"],
    )
    receiver = _first(
        executor_events,
        lambda event: _event_type(event, str(completion_profile["receiver_event_type"]))
        and event.get("stage") == completion_profile["receiver_stage"]
        and event.get("result") == completion_profile["receiver_result"],
    )
    if generated is not None and public_completion is not None and receiver is not None:
        completion = _clause(
            "PASS",
            evidence={
                "generated_timestamp_ns": generated["ros_time_ns"],
                "public_timestamp_ns": public_completion["ros_time_ns"],
                "receiver_timestamp_ns": receiver["ros_time_ns"],
            },
        )
    elif generated is not None and monitor_complete and receiver is None:
        completion = _clause(
            "VIOLATION", "completion was generated but not delivered to the expected executor"
        )
        categories.append("COMPLETION_NOT_DELIVERED")
    else:
        completion = _clause(
            "UNKNOWN", "completion generation, public delivery, and receiver evidence are incomplete"
        )

    successor_profile = profile["expected_successor"]
    completion_anchor_ns = (
        int(public_completion["ros_time_ns"]) if public_completion is not None else None
    )
    commands_after_completion = (
        _after(lifecycle_events, completion_anchor_ns) if completion_anchor_ns is not None else []
    )
    request = _first(
        commands_after_completion,
        lambda event: _event_type(event, str(successor_profile["request_event_type"]))
        and _details(event).get("command") == successor_profile["command"]
        and (
            "command_param1" not in successor_profile
            or _details(event).get("param1") == successor_profile["command_param1"]
        )
        and registered_executor_id is not None
        and _details(event).get("source_component")
        == successor_profile["requester_source_component_base"] + registered_executor_id,
    )
    request_deadline_ns = int(successor_profile["request_after_completion_deadline_ms"]) * 1_000_000
    if completion_anchor_ns is None:
        successor_request = _clause("UNKNOWN", "successful completion anchor is missing")
    elif request is None and monitor_complete:
        successor_request = _clause(
            "VIOLATION", "expected successor command was not observed after completion"
        )
        categories.extend(["EXPECTED_SUCCESSOR_NOT_REQUESTED", "LIFECYCLE_DEAD_END"])
    elif request is None:
        successor_request = _clause("UNKNOWN", "successor request observation window is incomplete")
    else:
        request_latency_ns = int(request["ros_time_ns"]) - completion_anchor_ns
        if request_latency_ns > request_deadline_ns:
            successor_request = _clause(
                "VIOLATION",
                "expected successor command exceeded its deadline",
                evidence={"latency_ms": request_latency_ns / 1_000_000.0},
            )
            categories.append("EXPECTED_SUCCESSOR_NOT_REQUESTED")
        else:
            successor_request = _clause(
                "PASS",
                evidence={
                    "command": successor_profile["command"],
                    "command_param1": successor_profile.get("command_param1"),
                    "timestamp_ns": request["ros_time_ns"],
                    "latency_ms": request_latency_ns / 1_000_000.0,
                },
            )

    request_timestamp_ns = int(request["ros_time_ns"]) if request is not None else None
    status_after_request = (
        _after(lifecycle_events, request_timestamp_ns) if request_timestamp_ns is not None else []
    )
    selected = _first(
        status_after_request,
        lambda event: _event_type(event, "vehicle_status_observed")
        and event.get("active_mode") == successor_profile["selected_nav_state"],
    )
    route_installation = None
    route_transition = None
    if route_oracle is not None:
        route_installation = route_oracle.get("clauses", {}).get("installation", {}).get("status")
        route_transition = route_oracle.get("transition")
    route_transition_timestamp_us = (
        float(route_transition["timestamp_us"])
        if isinstance(route_transition, dict) and route_transition.get("timestamp_us") is not None
        else None
    )
    target_epoch_event = _first(
        route_events,
        lambda event: event.get("event_type") == "route_epoch_changed"
        and event.get("declared_mode") == successor_profile["selected_nav_state"]
        and event.get("route_epoch_id") is not None
        and (
            route_transition_timestamp_us is None
            or float(event.get("timestamp", -1)) >= route_transition_timestamp_us
        ),
    )
    clock_required = bool(profile.get("evidence", {}).get("require_valid_clock_bridge", False))
    clock_valid = clock_bridge is not None and clock_bridge.get("status") == "VALID"
    if request is None and completion_anchor_ns is not None and monitor_complete:
        successor_installation = _clause(
            "VIOLATION",
            "the complete post-completion window contains no Land request, selection, or route installation",
            evidence={
                "route_oracle_status": route_oracle.get("status") if route_oracle else None,
                "route_transition": route_transition,
                "selected_nav_state": None,
            },
        )
        categories.append("EXPECTED_SUCCESSOR_NOT_INSTALLED")
    elif request is None:
        successor_installation = _clause("UNKNOWN", "successor request anchor is missing")
    elif selected is None and monitor_complete:
        successor_installation = _clause(
            "VIOLATION", "Commander did not select the expected successor"
        )
        categories.append("EXPECTED_SUCCESSOR_NOT_SELECTED")
    elif selected is None:
        successor_installation = _clause("UNKNOWN", "successor selection window is incomplete")
    else:
        selection_latency_ns = int(selected["ros_time_ns"]) - int(request["ros_time_ns"])
        selection_deadline_ns = (
            int(successor_profile["selection_after_request_deadline_ms"]) * 1_000_000
        )
        transition_matches = (
            isinstance(route_transition, dict)
            and route_transition.get("source_mode") == registered_mode_id
            and route_transition.get("target_mode") == successor_profile["selected_nav_state"]
        )
        distinct_epoch = (
            not successor_profile.get("require_distinct_route_epoch", False)
            or (
                isinstance(route_transition, dict)
                and route_transition.get("source_route_epoch_id") is not None
                and target_epoch_event is not None
                and route_transition.get("source_route_epoch_id")
                != target_epoch_event.get("route_epoch_id")
            )
        )
        if selection_latency_ns > selection_deadline_ns:
            successor_installation = _clause(
                "VIOLATION",
                "Commander selected the expected successor after its deadline",
                evidence={"selection_latency_ms": selection_latency_ns / 1_000_000.0},
            )
            categories.append("EXPECTED_SUCCESSOR_NOT_SELECTED")
        elif clock_required and not clock_valid:
            successor_installation = _clause(
                "UNKNOWN", "a VALID clock bridge is required for route installation evidence"
            )
        elif not transition_matches:
            successor_installation = _clause(
                "UNKNOWN", "selected External-to-successor Route Oracle transition is missing"
            )
        elif not distinct_epoch:
            successor_installation = _clause(
                "VIOLATION", "successor did not install on a distinct route epoch"
            )
            categories.append("SUCCESSOR_INSTALLED_WITH_WRONG_ROUTE")
        elif route_installation == "VIOLATION":
            successor_installation = _clause(
                "VIOLATION", "Route Oracle reports incomplete successor installation"
            )
            categories.append("EXPECTED_SUCCESSOR_NOT_INSTALLED")
        elif route_installation != "PASS":
            successor_installation = _clause(
                "UNKNOWN", "Route Oracle installation evidence is not PASS"
            )
        else:
            successor_installation = _clause(
                "PASS",
                evidence={
                    "selected_mode": selected["active_mode"],
                    "selection_latency_ms": selection_latency_ns / 1_000_000.0,
                    "route_installation": route_installation,
                    "transition": route_transition,
                    "target_route_epoch_id": target_epoch_event.get("route_epoch_id"),
                },
            )

    completion_generated_ns = int(generated["ros_time_ns"]) if generated is not None else None
    deactivated = _first(
        executor_events,
        lambda event: _event_type(event, "external_mode_deactivated")
        and (
            completion_generated_ns is None
            or int(event["ros_time_ns"]) >= completion_generated_ns
        ),
    )
    landed = _first(
        lifecycle_events,
        lambda event: _event_type(event, "land_detected_observed")
        and event.get("landed") is True
        and public_completion is not None
        and int(event["ros_time_ns"]) >= int(public_completion["ros_time_ns"]),
    )
    disarmed = _first(
        lifecycle_events,
        lambda event: _event_type(event, "vehicle_status_observed")
        and event.get("armed") is False
        and active_external is not None
        and int(event["ros_time_ns"]) > int(active_external["ros_time_ns"]),
    )
    mission_reasons: list[str] = []
    mission_categories: list[str] = []
    monitor_finished = _first(
        lifecycle_events, lambda event: _event_type(event, "monitor_finished")
    )
    hover_after_completion_ms = int(
        profile.get("terminal_condition", {}).get("hover_after_completion_ms", 0)
    )
    hover_observed = bool(
        public_completion is not None
        and monitor_finished is not None
        and hover_after_completion_ms > 0
        and int(monitor_finished["ros_time_ns"])
        - int(public_completion["ros_time_ns"])
        >= hover_after_completion_ms * 1_000_000
        and monitor_finished.get("active_mode") == registered_mode_id
        and monitor_finished.get("armed") is True
        and monitor_finished.get("landed") is False
        and selected is None
    )
    if deactivated is None:
        mission_reasons.append("external mode deactivation was not observed")
        mission_categories.append("EXTERNAL_ROUTE_NOT_RELEASED")
    if landed is None:
        mission_reasons.append("landed state was not observed")
        mission_categories.append("LAND_NOT_REACHED")
    if disarmed is None:
        mission_reasons.append("terminal disarm was not observed")
        mission_categories.append("DISARM_NOT_REACHED")
    elif selected is not None:
        disarm_latency_ns = int(disarmed["ros_time_ns"]) - int(selected["ros_time_ns"])
        disarm_deadline_ns = (
            int(profile["terminal_condition"]["disarm_after_land_selection_deadline_ms"])
            * 1_000_000
        )
        if disarm_latency_ns > disarm_deadline_ns:
            mission_reasons.append("terminal disarm exceeded its deadline")
            mission_categories.append("DISARM_NOT_REACHED")
    if hover_observed:
        mission_reasons.append(
            f"vehicle remained armed and airborne in the external mode for at least {hover_after_completion_ms} ms after completion"
        )
        mission_categories.append("UNEXPECTED_HOVER_AFTER_COMPLETION")
    required_monitor_status = str(profile.get("evidence", {}).get("require_monitor_status", "PASS"))
    if not mission_reasons and monitor_complete and monitor_status == required_monitor_status:
        mission_progression = _clause(
            "PASS",
            evidence={
                "deactivated_timestamp_ns": deactivated["ros_time_ns"],
                "landed_timestamp_ns": landed["ros_time_ns"],
                "disarmed_timestamp_ns": disarmed["ros_time_ns"],
                "disarm_after_land_selection_ms": (
                    (int(disarmed["ros_time_ns"]) - int(selected["ros_time_ns"]))
                    / 1_000_000.0
                    if selected is not None
                    else None
                ),
            },
        )
    elif monitor_complete:
        mission_progression = _clause(
            "VIOLATION",
            *(mission_reasons or [f"monitor finished with status {monitor_status}"]),
        )
        categories.extend(mission_categories)
    else:
        mission_progression = _clause(
            "UNKNOWN", *(mission_reasons or ["terminal monitor window is incomplete"])
        )

    clauses = {
        "ownership": ownership,
        "completion": completion,
        "successor_request": successor_request,
        "successor_installation": successor_installation,
        "mission_progression": mission_progression,
    }
    timeline = {
        "registration_ros_time_ns": registration.get("ros_time_ns") if registration else None,
        "external_active_ros_time_ns": active_external.get("ros_time_ns") if active_external else None,
        "completion_ros_time_ns": public_completion.get("ros_time_ns") if public_completion else None,
        "successor_request_ros_time_ns": request.get("ros_time_ns") if request else None,
        "successor_selected_ros_time_ns": selected.get("ros_time_ns") if selected else None,
        "landed_ros_time_ns": landed.get("ros_time_ns") if landed else None,
        "disarmed_ros_time_ns": disarmed.get("ros_time_ns") if disarmed else None,
    }
    evidence_completeness = {
        "single_run_id": len(run_ids) == 1,
        "registration": registration is not None,
        "external_activation": active_external is not None,
        "completion_generated": generated is not None,
        "completion_public": public_completion is not None,
        "completion_receiver": receiver is not None,
        "successor_request": request is not None,
        "successor_selection": selected is not None,
        "route_oracle": route_oracle is not None,
        "route_trace_target_epoch": target_epoch_event is not None,
        "clock_bridge_valid": clock_valid,
        "terminal_monitor": monitor_complete,
    }
    return _result(
        profile,
        lifecycle_events,
        clauses,
        categories,
        timeline,
        inputs,
        run_id=run_id,
        evidence_completeness=evidence_completeness,
    )


def _result(
    profile: dict[str, Any],
    lifecycle_events: list[dict[str, Any]],
    clauses: dict[str, dict[str, object]],
    categories: list[str],
    timeline: dict[str, int | None],
    inputs: dict[str, str | None] | None,
    *,
    run_id: str | None = None,
    evidence_completeness: dict[str, bool] | None = None,
) -> dict[str, Any]:
    statuses = [str(clause["status"]) for clause in clauses.values()]
    if any(status == "VIOLATION" for status in statuses):
        overall = "VIOLATION"
    elif statuses and all(status == "PASS" for status in statuses):
        overall = "PASS"
    elif statuses and all(status == "NOT_APPLICABLE" for status in statuses):
        overall = "NOT_APPLICABLE"
    else:
        overall = "UNKNOWN"
    if run_id is None:
        run_ids = {str(event["run_id"]) for event in lifecycle_events}
        run_id = next(iter(run_ids)) if len(run_ids) == 1 else "unknown"
    result = {
        "schema_version": "1.0",
        "successor_oracle_version": "0.1",
        "run_id": run_id,
        "profile_id": str(profile["profile_id"]),
        "status": overall,
        "clauses": clauses,
        "violation_categories": sorted(set(categories)),
        "timeline": timeline,
        "evidence_completeness": evidence_completeness or {},
        "inputs": inputs
        or {
            "lifecycle_events": None,
            "executor_log": None,
            "route_trace": None,
            "route_oracle": None,
            "clock_bridge": None,
            "profile": None,
        },
    }
    schema = json.loads(RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lifecycle-events", type=Path, required=True)
    parser.add_argument("--executor-log", type=Path, required=True)
    parser.add_argument("--route-trace", type=Path, required=True)
    parser.add_argument("--route-oracle", type=Path, required=True)
    parser.add_argument("--clock-bridge", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    profile = yaml.safe_load(args.profile.read_text(encoding="utf-8"))
    route_oracle = json.loads(args.route_oracle.read_text(encoding="utf-8"))
    clock_bridge = json.loads(args.clock_bridge.read_text(encoding="utf-8"))
    result = evaluate(
        profile,
        load_lifecycle_events(args.lifecycle_events),
        load_executor_events(args.executor_log),
        load_route_events(args.route_trace),
        route_oracle,
        clock_bridge,
        inputs={
            "lifecycle_events": str(args.lifecycle_events),
            "executor_log": str(args.executor_log),
            "route_trace": str(args.route_trace),
            "route_oracle": str(args.route_oracle),
            "clock_bridge": str(args.clock_bridge),
            "profile": str(args.profile),
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return 0 if result["status"] in {"PASS", "VIOLATION", "NOT_APPLICABLE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
