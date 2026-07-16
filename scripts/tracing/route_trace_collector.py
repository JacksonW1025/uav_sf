#!/usr/bin/env python3
"""Collect ROS/PX4 events into the canonical route trace schema."""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "data" / "schemas" / "route_trace.schema.json"


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@dataclass
class RouteState:
    run_id: str
    declared_mode: object = None
    registration_state: object = None
    authority_source: Optional[str] = None
    producer_identity: Optional[str] = None
    setpoint_level: Optional[str] = None
    setpoint_topic: Optional[str] = None
    message_age: Optional[float] = None
    enabled_modules: list[str] = field(default_factory=list)
    bypassed_modules: list[str] = field(default_factory=list)
    allocator_input: object = None
    actuator_writer: object = None
    actuator_output_summary: Optional[dict[str, object]] = None
    failsafe_state: object = None
    fallback_target: object = None

    def event(
        self,
        timestamp: float,
        timestamp_domain: str,
        event_type: str,
        evidence_source: str,
        confidence: str,
    ) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "timestamp": timestamp,
            "timestamp_domain": timestamp_domain,
            "event_type": event_type,
            "declared_mode": self.declared_mode,
            "registration_state": self.registration_state,
            "authority_source": self.authority_source,
            "producer_identity": self.producer_identity,
            "setpoint_level": self.setpoint_level,
            "setpoint_topic": self.setpoint_topic,
            "message_age": self.message_age,
            "enabled_modules": sorted(set(self.enabled_modules)),
            "bypassed_modules": sorted(set(self.bypassed_modules)),
            "allocator_input": self.allocator_input,
            "actuator_writer": self.actuator_writer,
            "actuator_output_summary": self.actuator_output_summary,
            "failsafe_state": self.failsafe_state,
            "fallback_target": self.fallback_target,
            "evidence_source": evidence_source,
            "confidence": confidence,
        }


class RouteTraceWriter:
    def __init__(self, output: Path, schema: Optional[dict[str, Any]] = None) -> None:
        self.output = output
        self.validator = Draft202012Validator(schema or load_schema())
        self.output.parent.mkdir(parents=True, exist_ok=True)

    def write(self, events: Iterable[dict[str, object]]) -> int:
        count = 0
        with self.output.open("w", encoding="utf-8") as handle:
            for event in events:
                self.validator.validate(event)
                handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
                count += 1
        return count


CONTROL_MODULE_FLAGS = {
    "flag_multicopter_position_control_enabled": "mc_pos_control",
    "flag_control_attitude_enabled": "mc_att_control",
    "flag_control_rates_enabled": "mc_rate_control",
    "flag_control_allocation_enabled": "control_allocator",
}


class RouteEventReducer:
    """Stateful, explicit derivations used by both ROS and ULog collectors."""

    def __init__(self, run_id: str) -> None:
        self.state = RouteState(run_id=run_id)

    def reduce(
        self,
        source: str,
        payload: dict[str, object],
        timestamp: float,
        domain: str = "px4_uorb_us",
    ) -> dict[str, object]:
        event_type = source
        confidence = "HIGH"

        if source == "vehicle_status":
            nav_state = int(payload["nav_state"])
            self.state.declared_mode = nav_state
            if nav_state == 14:
                self.state.authority_source = "ros2_offboard"
            elif 23 <= nav_state <= 30:
                self.state.authority_source = "dynamic_external_mode"
            else:
                self.state.authority_source = "px4_internal"
            if bool(payload.get("failsafe", False)) and nav_state not in range(23, 31) and nav_state != 14:
                self.state.fallback_target = nav_state

        elif source == "register_ext_component_reply":
            success = bool(payload.get("success", False))
            self.state.registration_state = {
                "registered": success,
                "name": str(payload.get("name", "")),
                "mode_id": int(payload.get("mode_id", -1)),
                "mode_executor_id": int(payload.get("mode_executor_id", -1)),
                "arming_check_id": int(payload.get("arming_check_id", -1)),
            }
            if success and payload.get("name"):
                self.state.producer_identity = f"registered_component:{payload['name']}"

        elif source == "vehicle_control_mode":
            enabled = [name for flag, name in CONTROL_MODULE_FLAGS.items() if bool(payload.get(flag, False))]
            all_modules = set(CONTROL_MODULE_FLAGS.values())
            self.state.enabled_modules = enabled
            self.state.bypassed_modules = sorted(all_modules - set(enabled))
            if bool(payload.get("flag_control_position_enabled", False)):
                self.state.setpoint_level = "position"
            elif bool(payload.get("flag_control_velocity_enabled", False)):
                self.state.setpoint_level = "velocity"
            elif bool(payload.get("flag_control_attitude_enabled", False)):
                self.state.setpoint_level = "attitude"
            elif bool(payload.get("flag_control_rates_enabled", False)):
                self.state.setpoint_level = "body_rate"
            elif bool(payload.get("flag_control_allocation_enabled", False)):
                self.state.setpoint_level = "thrust_and_torque"
            self.state.setpoint_topic = "trajectory_setpoint" if self.state.setpoint_level in {"position", "velocity"} else None
            confidence = "MEDIUM"

        elif source == "producer_publish":
            self.state.producer_identity = str(payload["producer_identity"])
            self.state.setpoint_topic = str(payload.get("setpoint_topic", "trajectory_setpoint"))
            event_type = "producer_still_publishing"

        elif source == "trajectory_setpoint":
            subject_timestamp = float(payload.get("timestamp", timestamp))
            self.state.setpoint_topic = "trajectory_setpoint"
            self.state.message_age = max(0.0, (timestamp - subject_timestamp) / 1_000_000.0)
            event_type = "px4_setpoint_received"
            confidence = "MEDIUM"

        elif source == "route_observability":
            event_id = int(payload["event_type"])
            writer_id = int(payload.get("writer_id", 0))
            subject_timestamp = float(payload.get("subject_timestamp", timestamp))
            self.state.message_age = max(0.0, (timestamp - subject_timestamp) / 1_000_000.0)
            if event_id == 1:
                event_type = "px4_setpoint_consumed"
                self.state.setpoint_topic = "trajectory_setpoint"
            elif event_id == 2:
                event_type = "allocator_input_published"
                self.state.allocator_input = {
                    "topic": "vehicle_torque_setpoint",
                    "writer": "mc_rate_control" if writer_id == 1 else "unknown",
                }
            elif event_id == 3:
                event_type = "actuator_output_published"
                self.state.actuator_writer = "control_allocator" if writer_id == 2 else "unknown"
            else:
                event_type = "unknown_instrumentation_event"
                confidence = "LOW"

        elif source == "actuator_motors":
            controls = [float(value) for key, value in payload.items() if key.startswith("control[")]
            finite = [value for value in controls if math.isfinite(value)]
            self.state.actuator_output_summary = {
                "finite_channels": len(finite),
                "minimum": min(finite) if finite else None,
                "maximum": max(finite) if finite else None,
            }

        elif source == "failsafe_flags":
            active_flags = sorted(
                key for key, value in payload.items() if key != "timestamp" and isinstance(value, bool) and value
            )
            self.state.failsafe_state = {"active": bool(active_flags), "flags": active_flags}

        else:
            confidence = "UNKNOWN"

        return self.state.event(timestamp, domain, event_type, f"collector:{source}", confidence)


def rows_from_ulog(path: Path) -> Iterator[tuple[float, str, dict[str, object]]]:
    try:
        from pyulog import ULog
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("pyulog is required for ULog collection") from exc
    wanted = {
        "vehicle_status",
        "register_ext_component_reply",
        "vehicle_control_mode",
        "trajectory_setpoint",
        "route_observability",
        "actuator_motors",
        "failsafe_flags",
    }
    ulog = ULog(str(path))
    rows: list[tuple[float, str, dict[str, object]]] = []
    for dataset in ulog.data_list:
        if dataset.name not in wanted or "timestamp" not in dataset.data:
            continue
        for index, timestamp in enumerate(dataset.data["timestamp"]):
            payload = {key: values[index].item() for key, values in dataset.data.items()}
            payload["instance"] = dataset.multi_id
            rows.append((float(timestamp), dataset.name, payload))
    yield from sorted(rows, key=lambda item: item[0])


def producer_events(path: Path, run_id: str) -> Iterator[dict[str, object]]:
    """Normalize the probe's producer-side JSONL without mixing clock domains."""
    state = RouteState(run_id=run_id)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            timestamp = float(record["ros_time_ns"])
            payload = record.get("adapter_event")
            event_type = str(record.get("event_type", "producer_event"))
            confidence = "MEDIUM"

            if isinstance(payload, dict):
                adapter_type = str(payload.get("event_type", payload.get("event", "adapter_event")))
                event_type = adapter_type
                identity = payload.get("producer_identity")
                if identity:
                    state.producer_identity = str(identity)
                if adapter_type == "offboard_publish":
                    event_type = "producer_still_publishing"
                    state.authority_source = "ros2_offboard"
                    state.setpoint_topic = "trajectory_setpoint"
                    state.setpoint_level = str(payload.get("behavior_phase", "velocity"))
                    confidence = "HIGH"
            elif event_type == "external_mode_registration_observed":
                mode_id = int(record["mode_id"])
                state.registration_state = {
                    "registered": True,
                    "name": str(record.get("name", "")),
                    "mode_id": mode_id,
                }
                state.producer_identity = "registered_component:Route Transition"
                event_type = "external_mode_registered"
                confidence = "HIGH"
            elif event_type == "state_transition":
                event_type = "probe_state_transition"
            elif event_type == "runner_finished":
                event_type = "probe_finished"

            yield state.event(
                timestamp,
                "ros_node_ns",
                event_type,
                f"producer_jsonl:{record.get('event_type', 'unknown')}",
                confidence,
            )


STRUCTURED_LOG_EVENT = re.compile(r"\[(?P<timestamp>[0-9]+(?:\.[0-9]+)?)\].*?(?P<json>\{\"event_type\".*\})")


def lifecycle_events(path: Path, run_id: str) -> Iterator[dict[str, object]]:
    """Extract the adapter/executor's structured ROS lifecycle records."""
    state = RouteState(run_id=run_id)
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = STRUCTURED_LOG_EVENT.search(line)
            if not match:
                continue
            payload = json.loads(match.group("json"))
            event_type = str(payload["event_type"])
            timestamp_ns = float(match.group("timestamp")) * 1_000_000_000.0
            confidence = "HIGH"

            if event_type == "external_mode_registered":
                mode_id = int(payload["mode_id"])
                state.registration_state = {
                    "registered": True,
                    "name": "Route Transition",
                    "mode_id": mode_id,
                }
                state.producer_identity = "registered_component:Route Transition"
            elif event_type == "external_mode_activated":
                state.declared_mode = int(payload["mode_id"])
                state.authority_source = "dynamic_external_mode"
                state.producer_identity = "registered_component:Route Transition"
                state.setpoint_topic = "trajectory_setpoint"
                state.setpoint_level = "velocity"
            elif event_type == "external_mode_setpoint":
                event_type = "producer_still_publishing"
                state.authority_source = "dynamic_external_mode"
                state.producer_identity = "registered_component:Route Transition"
                state.setpoint_topic = "trajectory_setpoint"
                state.setpoint_level = "velocity"
            elif event_type == "external_mode_deactivated":
                state.authority_source = None
            elif event_type.startswith("executor_") or event_type == "mode_executor_registered":
                if state.producer_identity is None:
                    state.producer_identity = "mode_executor:Route Transition"
                confidence = "MEDIUM" if event_type == "executor_transition" else "HIGH"

            details = ",".join(
                f"{key}={payload[key]}"
                for key in ("stage", "result", "phase", "sequence")
                if key in payload
            )
            evidence_source = f"ros_structured_log:{path.name}"
            if details:
                evidence_source += f":{details}"

            yield state.event(
                timestamp_ns,
                "ros_node_ns",
                event_type,
                evidence_source,
                confidence,
            )


def collect_ulog(
    path: Path,
    output: Path,
    run_id: str,
    producer_path: Optional[Path] = None,
    lifecycle_path: Optional[Path] = None,
) -> int:
    reducer = RouteEventReducer(run_id)
    events = [
        reducer.reduce(source, payload, timestamp, "ulog_us")
        for timestamp, source, payload in rows_from_ulog(path)
    ]
    if producer_path is not None:
        events.extend(producer_events(producer_path, run_id))
    if lifecycle_path is not None:
        events.extend(lifecycle_events(lifecycle_path, run_id))
    return RouteTraceWriter(output).write(events)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ulog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--producer-events", type=Path)
    parser.add_argument("--lifecycle-log", type=Path)
    args = parser.parse_args()
    count = collect_ulog(
        args.ulog,
        args.output,
        args.run_id,
        producer_path=args.producer_events,
        lifecycle_path=args.lifecycle_log,
    )
    print(json.dumps({"status": "PASS", "events": count, "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
