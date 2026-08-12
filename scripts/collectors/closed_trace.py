#!/usr/bin/env python3
"""Close ULog and ROS sidecars into one normalized, hash-chained trace."""

from __future__ import annotations

import argparse
import json
from bisect import bisect_right
from pathlib import Path
from typing import Any, Iterable

from scripts.collectors.clock_bridge import ClockBridge, fit_clock_bridge
from scripts.collectors.trace_collector import TraceCollector
from scripts.evaluator.plan import load_plan


EVENT_SETPOINT_CONSUMED = 1
EVENT_ALLOCATOR_INPUT_PUBLISHED = 2
EVENT_ACTUATOR_OUTPUT_PUBLISHED = 3
EVENT_ROUTE_EPOCH_CHANGED = 4
EVENT_UNREGISTER_REQUEST_PROCESSED = 5
EVENT_EXTERNAL_MODE_SLOT_REMOVED = 6
EVENT_EXECUTOR_SLOT_REMOVED = 7
EVENT_ARMING_CHECK_SLOT_REMOVED = 8
EVENT_ARMING_REQUEST_REJECTED = 9
EVENT_REGISTRATION_PROCESSED = 10

SOURCE_CONTROLLER = {
    1: "mc_position_control",
    12: "mc_attitude_control",
    13: "mc_rate_control",
}
NAV_ROUTE = {
    4: "internal_hold",
    5: "internal_rtl",
    14: "legacy_offboard",
    18: "internal_land",
}


class TraceClosureError(ValueError):
    """The retained sources cannot be closed without inventing evidence."""


EVENT_ORDER = {
    "revocation": 10,
    "transition_requested": 20,
    "activation": 30,
    "owner_changed": 40,
    "command_published": 50,
    "command_consumed": 60,
    "controller_output": 70,
    "allocator_output": 80,
    "actuator_write": 90,
    "completion": 100,
    "fault_detected": 110,
    "fallback_triggered": 120,
    "terminal_state": 130,
    "cleanup_completed": 140,
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(paths: Iterable[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TraceClosureError(f"{path}:{line_number}: record is not an object")
            records.append(value)
    return records


def _clock_bridge(sidecar: list[dict[str, Any]], maximum_uncertainty_ns: int) -> ClockBridge:
    by_source: dict[int, dict[str, int | str]] = {}
    for record in sidecar:
        if record.get("kind") != "timesync_sample":
            continue
        if "source_us" not in record or "analysis_projection_ns" not in record:
            continue
        source_ns = int(record["source_us"]) * 1000
        by_source[source_ns] = {
            "source_domain": "px4_boot_ns",
            "source_ns": source_ns,
            "analysis_ns": int(record["analysis_projection_ns"]),
            "round_trip_ns": max(0, int(record.get("round_trip_us", 0))) * 1000,
        }
    return fit_clock_bridge(
        [by_source[key] for key in sorted(by_source)],
        maximum_uncertainty_ns=maximum_uncertainty_ns,
    )


def _route(nav_state: int, plan: dict[str, Any]) -> str:
    if 23 <= nav_state <= 30:
        for candidate in (
            plan["transition"]["target_route"],
            plan["transition"]["source_route"],
        ):
            if candidate in {"dynamic_external_mode", "mode_executor"}:
                return str(candidate)
        return "dynamic_external_mode"
    return NAV_ROUTE.get(nav_state, "px4_internal")


def _owner(route: str) -> tuple[str, str]:
    if route == "mode_executor":
        return "family_a_mode_executor", "family_a_mode_executor"
    if route == "dynamic_external_mode":
        return "family_a_external_mode", "none"
    if route == "legacy_offboard":
        return "family_a_offboard_controller", "none"
    return "px4_commander", "none"


def _identity(
    *, route: str, epoch: int, nav_state: int, source_id: int, run_id: str
) -> dict[str, str]:
    lifecycle_owner, executor_owner = _owner(route)
    controller = SOURCE_CONTROLLER.get(source_id, "mc_rate_control")
    registration = (
        f"external-nav-{nav_state}"
        if route in {"dynamic_external_mode", "mode_executor"}
        else ("dds-offboard" if route == "legacy_offboard" else "px4-built-in")
    )
    producer = (
        f"offboard-{run_id}"
        if route == "legacy_offboard"
        else (lifecycle_owner if route in {"dynamic_external_mode", "mode_executor"} else "px4-internal")
    )
    return {
        "route": route,
        "route_epoch": f"px4-epoch-{epoch}",
        "producer_session": producer,
        "registration_id": registration,
        "activation_id": f"nav-{nav_state}-epoch-{epoch}",
        "controller_id": controller,
        "allocator_id": "px4-control-allocator",
        "writer_id": "px4-control-allocator-actuator-motors",
        "lifecycle_owner": lifecycle_owner,
        "executor_owner": executor_owner,
    }


def _map_ulog(
    observations: list[dict[str, Any]], bridge: ClockBridge, plan: dict[str, Any]
) -> list[dict[str, Any]]:
    mapped: list[tuple[int, dict[str, Any]]] = []
    carried_epoch: dict[str, Any] | None = None
    for raw in observations:
        source_ns = int(raw["timestamp"]) * 1000
        if (
            int(raw["event_type"]) == EVENT_ROUTE_EPOCH_CHANGED
            and source_ns <= bridge.valid_from_ns
        ):
            carried_epoch = raw
        if not bridge.valid_from_ns <= source_ns <= bridge.valid_until_ns:
            continue
        mapped.append((bridge.map(source_ns), raw))
    if carried_epoch is not None and not any(
        int(raw["event_type"]) == EVENT_ROUTE_EPOCH_CHANGED
        and int(raw["timestamp"]) * 1000 == bridge.valid_from_ns
        for _, raw in mapped
    ):
        carried = dict(carried_epoch)
        carried["timestamp"] = bridge.valid_from_ns // 1000
        carried["subject_timestamp"] = bridge.valid_from_ns // 1000
        carried["carried_into_clock_window"] = True
        mapped.append((bridge.map(bridge.valid_from_ns), carried))
        mapped.sort(
            key=lambda item: (
                item[0], int(item[1]["ulog_multi_id"]), int(item[1]["sequence"])
            )
        )
    epochs = [item for item in mapped if int(item[1]["event_type"]) == EVENT_ROUTE_EPOCH_CHANGED]
    if not epochs:
        raise TraceClosureError("no route epoch is covered by the clock bridge")
    epoch_times = [item[0] for item in epochs]
    epoch_details: list[dict[str, Any]] = []
    for timestamp_ns, raw in epochs:
        route = _route(int(raw["new_nav_state"]), plan)
        epoch_details.append(
            {
                "timestamp_ns": timestamp_ns,
                "route": route,
                "epoch": int(raw["route_epoch_id"]),
                "nav_state": int(raw["new_nav_state"]),
                "previous_nav_state": int(raw["previous_nav_state"]),
                "source_id": 0,
            }
        )
    # Bind each route epoch to the first observed command-consumption controller
    # in that epoch. This is explicit temporal binding, not a hidden DDS field.
    for timestamp_ns, raw in mapped:
        if int(raw["event_type"]) != EVENT_SETPOINT_CONSUMED:
            continue
        index = bisect_right(epoch_times, timestamp_ns) - 1
        if index >= 0 and epoch_details[index]["source_id"] == 0:
            epoch_details[index]["source_id"] = int(raw["source_id"])

    result: list[dict[str, Any]] = []
    identities = [
        _identity(
            route=item["route"],
            epoch=item["epoch"],
            nav_state=item["nav_state"],
            source_id=item["source_id"],
            run_id=plan["run_id"],
        )
        for item in epoch_details
    ]
    latest_subject_by_epoch: dict[int, int] = {}
    for timestamp_ns, raw in mapped:
        event_type = int(raw["event_type"])
        index = bisect_right(epoch_times, timestamp_ns) - 1
        if index < 0:
            continue
        identity = identities[index]
        provenance = {
            "clock_bridge_id": bridge.bridge_id,
            "raw_source_domain": "px4_boot_us",
            "raw_timestamp_us": int(raw["timestamp"]),
            "raw_observation_instance": int(raw["ulog_multi_id"]),
            "raw_observation_sequence": int(raw["sequence"]),
        }
        if event_type == EVENT_ROUTE_EPOCH_CHANGED:
            if index > 0:
                result.append(
                    {
                        "kind": "revocation",
                        "timestamp_ns": timestamp_ns,
                        "source_domain": "analysis_monotonic",
                        **identities[index - 1],
                        **provenance,
                    }
                )
            result.append(
                {
                    "kind": "activation",
                    "timestamp_ns": timestamp_ns,
                    "source_domain": "analysis_monotonic",
                    **identity,
                    **provenance,
                }
            )
            result.append(
                {
                    "kind": "owner_changed",
                    "timestamp_ns": timestamp_ns,
                    "source_domain": "analysis_monotonic",
                    **identity,
                    **provenance,
                }
            )
            continue
        if event_type == EVENT_SETPOINT_CONSUMED:
            subject = int(raw["subject_timestamp"]) * 1000
            latest_subject_by_epoch[index] = subject
            result.append(
                {
                    "kind": "command_consumed",
                    "timestamp_ns": timestamp_ns,
                    "source_domain": "analysis_monotonic",
                    "command_subject_ns": bridge.map(subject),
                    **identity,
                    **provenance,
                }
            )
            continue
        if event_type in {EVENT_ALLOCATOR_INPUT_PUBLISHED, EVENT_ACTUATOR_OUTPUT_PUBLISHED}:
            source_subject = latest_subject_by_epoch.get(index)
            if source_subject is None or not bridge.valid_from_ns <= source_subject <= bridge.valid_until_ns:
                # A downstream publication before the first observed command
                # in a new epoch has no defensible subject binding. It is not
                # normalized; the required installation chain must instead be
                # established by later, fully bound evidence.
                continue
            common = {
                "timestamp_ns": timestamp_ns,
                "source_domain": "analysis_monotonic",
                "command_subject_ns": bridge.map(source_subject),
                "raw_stage_subject_ns": int(raw["subject_timestamp"]) * 1000,
                **identity,
                **provenance,
            }
            if event_type == EVENT_ALLOCATOR_INPUT_PUBLISHED:
                result.append({"kind": "controller_output", **common})
            else:
                result.append({"kind": "allocator_output", **common})
                result.append(
                    {
                        "kind": "actuator_write",
                        "coalesced_with": "allocator_output",
                        "sitl_writer_boundary": "actuator_motors_uorb",
                        **common,
                    }
                )
            continue
        lifecycle_kind = {
            EVENT_REGISTRATION_PROCESSED: "registration",
            EVENT_UNREGISTER_REQUEST_PROCESSED: "revocation",
            EVENT_EXTERNAL_MODE_SLOT_REMOVED: "revocation",
            EVENT_EXECUTOR_SLOT_REMOVED: "revocation",
            EVENT_ARMING_CHECK_SLOT_REMOVED: "revocation",
            EVENT_ARMING_REQUEST_REJECTED: "fault_detected",
        }.get(event_type)
        if lifecycle_kind:
            result.append(
                {
                    "kind": lifecycle_kind,
                    "timestamp_ns": timestamp_ns,
                    "source_domain": "analysis_monotonic",
                    "result_code": int(raw["result"]),
                    "reason_code": int(raw["reason_code"]),
                    "component_hash": int(raw["component_hash"]),
                    **identity,
                    **provenance,
                }
            )
    return result


def close_trace(
    *,
    plan_path: Path,
    environment_path: Path,
    ulog_summary_path: Path,
    observations_path: Path,
    sidecar_paths: list[Path],
    output_path: Path,
    maximum_clock_uncertainty_ns: int,
) -> None:
    plan = load_plan(plan_path)
    environment = _read_json(environment_path)
    if isinstance(environment, dict) and "execution_environment" in environment:
        environment = environment["execution_environment"]
    if environment != plan["execution_environment"]:
        raise TraceClosureError("environment attestation differs from the frozen plan")
    ulog_summary = _read_json(ulog_summary_path)
    if ulog_summary.get("status") != "PASS":
        raise TraceClosureError("ULog integrity did not pass")
    observations = _read_json(observations_path)
    if not isinstance(observations, list):
        raise TraceClosureError("ULog observations must be an array")
    sidecars = _read_jsonl(sidecar_paths)
    bridge = _clock_bridge(sidecars, maximum_clock_uncertainty_ns)
    normalized = _map_ulog(observations, bridge, plan)
    lifecycle = []
    supported = {
        "transition_requested",
        "command_published",
        "completion",
        "fault_detected",
        "fallback_triggered",
        "terminal_state",
        "cleanup_completed",
    }
    for record in sidecars:
        record_kind = record.get("kind")
        if record_kind == "mode_completed":
            record = {
                **record,
                "kind": "completion",
                "route": str(plan["transition"]["target_route"]),
            }
            record_kind = "completion"
        if record_kind not in supported:
            continue
        timestamp = int(record["received_monotonic_ns"])
        event = {
            key: value
            for key, value in record.items()
            if key not in {"schema_version", "sequence", "received_monotonic_ns", "run_id"}
        }
        event.update(
            {
                "timestamp_ns": timestamp,
                "source_domain": "analysis_monotonic",
                "clock_bridge_id": bridge.bridge_id,
            }
        )
        lifecycle.append(event)
    status_records = [item for item in sidecars if item.get("kind") == "vehicle_status"]
    land_records = [item for item in sidecars if item.get("kind") == "vehicle_land_detected"]
    if status_records and land_records:
        status = max(status_records, key=lambda value: int(value["received_monotonic_ns"]))
        land = max(land_records, key=lambda value: int(value["received_monotonic_ns"]))
        terminal_timestamp = max(
            int(status["received_monotonic_ns"]), int(land["received_monotonic_ns"])
        )
        lifecycle.append(
            {
                "kind": "terminal_state",
                "timestamp_ns": terminal_timestamp,
                "source_domain": "analysis_monotonic",
                "clock_bridge_id": bridge.bridge_id,
                "route": _route(int(status["nav_state"]), plan),
                "landed": bool(land.get("landed")),
                "disarmed": int(status["arming_state"]) == 1,
            }
        )
    combined = sorted(
        [*normalized, *lifecycle],
        key=lambda value: (
            int(value["timestamp_ns"]),
            EVENT_ORDER.get(str(value["kind"]), 1000),
        ),
    )
    with TraceCollector(output_path, plan["run_id"]) as collector:
        collector.append(
            {
                "kind": "collection_started",
                "timestamp_ns": 0,
                "source_domain": "analysis_monotonic",
                "clock_bridge_id": bridge.bridge_id,
            }
        )
        collector.append(
            {
                "kind": "environment_attested",
                "timestamp_ns": 1,
                "source_domain": "analysis_monotonic",
                "clock_bridge_id": bridge.bridge_id,
                "execution_environment": environment,
            }
        )
        collector.append(bridge.event(run_id=plan["run_id"], sequence=2, timestamp_ns=2))
        for event in combined:
            collector.append(event)
        stopped = max((int(item["timestamp_ns"]) for item in combined), default=2) + 1
        collector.append(
            {
                "kind": "collection_stopped",
                "timestamp_ns": stopped,
                "source_domain": "analysis_monotonic",
                "clock_bridge_id": bridge.bridge_id,
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--ulog-summary", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-clock-uncertainty-ns", type=int, required=True)
    args = parser.parse_args()
    try:
        close_trace(
            plan_path=args.plan,
            environment_path=args.environment,
            ulog_summary_path=args.ulog_summary,
            observations_path=args.observations,
            sidecar_paths=args.sidecar,
            output_path=args.output,
            maximum_clock_uncertainty_ns=args.maximum_clock_uncertainty_ns,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": "CLOSED", "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
