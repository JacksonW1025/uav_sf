from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from scripts.tracing.actuator_writer_collector import summarize
from scripts.tracing.route_trace_collector import (
    RouteEventReducer,
    RouteTraceWriter,
    lifecycle_events,
    producer_events,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "data" / "schemas" / "route_trace.schema.json").read_text(encoding="utf-8"))


def test_schema_is_valid_and_requires_all_route_fields() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    required = set(SCHEMA["required"])
    assert len(required) == 21
    assert {"producer_identity", "actuator_writer", "fallback_target", "evidence_source"} <= required


def test_reducer_distinguishes_publish_consume_and_writer(tmp_path: Path) -> None:
    reducer = RouteEventReducer("run-1")
    events = [
        reducer.reduce("producer_publish", {"producer_identity": "node-a"}, 1_000_000, "ros_node_ns"),
        reducer.reduce("trajectory_setpoint", {"timestamp": 900_000}, 1_000_000),
        reducer.reduce("route_observability", {"event_type": 1, "subject_timestamp": 900_000}, 1_010_000),
        reducer.reduce("route_observability", {"event_type": 2, "writer_id": 1}, 1_020_000),
        reducer.reduce("route_observability", {"event_type": 3, "writer_id": 2}, 1_030_000),
    ]
    output = tmp_path / "trace.jsonl"
    assert RouteTraceWriter(output, SCHEMA).write(events) == 5
    assert events[0]["event_type"] == "producer_still_publishing"
    assert events[2]["event_type"] == "px4_setpoint_consumed"
    assert events[-1]["actuator_writer"] == "control_allocator"
    assert summarize(output)["status"] == "ATTRIBUTED"


def test_invalid_event_is_rejected(tmp_path: Path) -> None:
    event = RouteEventReducer("run-2").reduce("vehicle_status", {"nav_state": 14}, 1.0)
    del event["timestamp_domain"]
    with pytest.raises(ValidationError):
        RouteTraceWriter(tmp_path / "bad.jsonl", SCHEMA).write([event])


def test_producer_and_lifecycle_sidecars_preserve_ros_clock_domain(tmp_path: Path) -> None:
    producer = tmp_path / "producer.jsonl"
    producer.write_text(
        json.dumps(
            {
                "event_type": "adapter_event",
                "ros_time_ns": 123,
                "adapter_event": {
                    "event_type": "offboard_publish",
                    "producer_identity": "node-a",
                    "behavior_phase": "hover",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    [producer_event] = list(producer_events(producer, "run-sidecar"))
    assert producer_event["event_type"] == "producer_still_publishing"
    assert producer_event["timestamp_domain"] == "ros_node_ns"
    assert producer_event["producer_identity"] == "node-a"

    lifecycle = tmp_path / "mode.log"
    lifecycle.write_text(
        '[INFO] [1000.25] [mode]: {"event_type":"external_mode_registered","mode_id":23}\n',
        encoding="utf-8",
    )
    [registration] = list(lifecycle_events(lifecycle, "run-sidecar"))
    assert registration["registration_state"]["mode_id"] == 23
    assert registration["timestamp"] == 1_000_250_000_000.0
