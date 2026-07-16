from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from scripts.tracing.actuator_writer_collector import summarize
from scripts.tracing.route_trace_collector import RouteEventReducer, RouteTraceWriter


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
