from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from scripts.tracing.route_trace_collector import (
    RouteEventReducer,
    RouteTraceWriter,
    collect_ulogs,
    lifecycle_events,
    processed_trace_events,
    producer_events,
)
from scripts.tracing import route_trace_collector
from scripts.tracing.migrate_route_trace_v1_0_to_v1_1 import migrate_event
from scripts.tracing.migrate_route_trace_v1_1_to_v1_2 import migrate_event as migrate_v1_2_event


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "data" / "schemas" / "route_trace.schema.json").read_text(encoding="utf-8"))


def test_schema_is_valid_and_requires_all_route_fields() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    required = set(SCHEMA["required"])
    assert len(required) == 28
    assert {
        "producer_identity",
        "actuator_writer",
        "fallback_target",
        "behavior_phase",
        "route_epoch_id",
        "route_activation_id",
        "producer_session_id",
        "registration_instance_id",
        "route_change_source",
        "observation",
        "evidence_source",
    } <= required
    assert SCHEMA["properties"]["schema_version"]["const"] == "1.2"


def test_reducer_distinguishes_publish_consume_and_writer(tmp_path: Path) -> None:
    reducer = RouteEventReducer("run-1")
    events = [
        reducer.reduce("producer_publish", {"producer_identity": "node-a"}, 1_000_000, "ros_node_ns"),
        reducer.reduce("trajectory_setpoint", {"timestamp": 900_000}, 1_000_000),
        reducer.reduce(
            "route_observability",
            {"event_type": 1, "subject_timestamp": 900_000, "sequence": 0, "profile": 2},
            1_010_000,
        ),
        reducer.reduce(
            "route_observability",
            {"event_type": 2, "writer_id": 1, "sequence": 0, "profile": 2},
            1_020_000,
        ),
        reducer.reduce(
            "route_observability",
            {"event_type": 3, "writer_id": 2, "sequence": 0, "profile": 2},
            1_030_000,
        ),
    ]
    output = tmp_path / "trace.jsonl"
    assert RouteTraceWriter(output, SCHEMA).write(events) == 5
    assert events[0]["event_type"] == "producer_still_publishing"
    assert events[2]["event_type"] == "px4_setpoint_consumed"
    assert events[-1]["actuator_writer"] == "control_allocator"
    assert events[-1]["observation"]["sequence"] == 0


def test_invalid_event_is_rejected(tmp_path: Path) -> None:
    event = RouteEventReducer("run-2").reduce("vehicle_status", {"nav_state": 14}, 1.0)
    del event["timestamp_domain"]
    with pytest.raises(ValidationError):
        RouteTraceWriter(tmp_path / "bad.jsonl", SCHEMA).write([event])


def test_processed_trace_thins_allocator_but_not_final_writer() -> None:
    reducer = RouteEventReducer("compact")
    events = []
    for sequence in range(8):
        events.append(
            reducer.reduce(
                "route_observability",
                {"event_type": 2, "writer_id": 1, "sequence": sequence, "profile": 2},
                1000 + sequence,
            )
        )
        events.append(
            reducer.reduce(
                "route_observability",
                {"event_type": 3, "writer_id": 2, "sequence": sequence, "profile": 2},
                2000 + sequence,
            )
        )
    compact = list(processed_trace_events(events))
    assert sum(event["event_type"] == "allocator_input_published" for event in compact) == 2
    assert sum(event["event_type"] == "actuator_output_published" for event in compact) == 8


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
    assert producer_event["setpoint_level"] == "unknown"
    assert producer_event["behavior_phase"] == "hover"

    lifecycle = tmp_path / "mode.log"
    lifecycle.write_text(
        '[INFO] [1000.25] [mode]: {"event_type":"external_mode_registered","mode_id":23}\n',
        encoding="utf-8",
    )
    [registration] = list(lifecycle_events(lifecycle, "run-sidecar"))
    assert registration["registration_state"]["mode_id"] == 23
    assert registration["timestamp"] == 1_000_250_000_000.0


def test_lifecycle_sidecar_preserves_declared_component_identity(tmp_path: Path) -> None:
    lifecycle = tmp_path / "successor.log"
    lifecycle.write_text(
        '[INFO] [1000.25] [mode]: {"event_type":"external_mode_registered",'
        '"component_name":"Successor Baseline","mode_id":23}\n'
        '[INFO] [1001.25] [mode]: {"event_type":"external_mode_activated",'
        '"component_name":"Successor Baseline","mode_id":23,"activation_id":1}\n'
        '[INFO] [1002.25] [mode]: {"event_type":"external_mode_setpoint",'
        '"component_name":"Successor Baseline","behavior_phase":"hover"}\n',
        encoding="utf-8",
    )
    registration, activation, setpoint = list(
        lifecycle_events(lifecycle, "successor-sidecar")
    )
    expected = "registered_component:Successor Baseline"
    assert registration["registration_state"]["name"] == "Successor Baseline"
    assert registration["producer_identity"] == expected
    assert activation["producer_identity"] == expected
    assert setpoint["producer_identity"] == expected
    assert setpoint["event_type"] == "producer_still_publishing"


def test_lifecycle_sidecar_normalizes_c_printf_nonfinite_values(tmp_path: Path) -> None:
    lifecycle = tmp_path / "nonfinite.log"
    lifecycle.write_text(
        '[INFO] [1002.25] [mode]: {"event_type":"external_mode_setpoint",'
        '"component_name":"Issue 162 Custom RTL","horizontal_error_m":nan,'
        '"vertical_error_m":nan,"speed_m_s":nan}\n',
        encoding="utf-8",
    )
    [setpoint] = list(lifecycle_events(lifecycle, "historical-sidecar"))
    assert setpoint["event_type"] == "producer_still_publishing"
    assert setpoint["producer_identity"] == (
        "registered_component:Issue 162 Custom RTL"
    )


def test_collector_merges_independent_producer_and_monitor_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    producer = tmp_path / "producer.jsonl"
    producer.write_text(
        json.dumps(
            {
                "event_type": "adapter_event",
                "ros_time_ns": 100,
                "adapter_event": {
                    "event_type": "offboard_publish",
                    "producer_identity": "legacy-offboard",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monitor = tmp_path / "monitor.jsonl"
    monitor.write_text(
        json.dumps(
            {
                "event_type": "channel_configuration_applied",
                "ros_time_ns": 200,
                "heartbeat_or_health_enabled": True,
                "setpoint_enabled": False,
            }
        )
        + "\n"
        + json.dumps({"event_type": "experiment_window_started", "ros_time_ns": 201})
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(route_trace_collector, "rows_from_ulog", lambda _path: iter(()))
    output = tmp_path / "trace.jsonl"
    assert collect_ulogs(
        [tmp_path / "empty.ulg"],
        output,
        "merged-sidecars",
        producer_paths=[producer, monitor],
    ) == 3
    event_types = [json.loads(line)["event_type"] for line in output.read_text().splitlines()]
    assert event_types == [
        "producer_still_publishing",
        "channel_configuration_applied",
        "experiment_window_started",
    ]


def test_v1_migration_moves_old_phase_without_inventing_level() -> None:
    old = RouteEventReducer("migration").reduce("vehicle_status", {"nav_state": 14}, 1.0)
    old["schema_version"] = "1.0"
    old.pop("behavior_phase")
    old.pop("observation")
    old["setpoint_level"] = "straight_line"
    migrated, moved = migrate_event(old)
    assert moved is True
    assert migrated["schema_version"] == "1.1"
    assert migrated["behavior_phase"] == "straight_line"
    assert migrated["setpoint_level"] == "unknown"
    assert migrated["observation"] is None


def test_v1_1_to_v1_2_migration_does_not_invent_identities() -> None:
    old = RouteEventReducer("migration-v12").reduce("vehicle_status", {"nav_state": 14}, 1.0)
    old["schema_version"] = "1.1"
    for field in (
        "route_epoch_id",
        "route_activation_id",
        "producer_session_id",
        "registration_instance_id",
        "route_change_source",
    ):
        old.pop(field)
    migrated = migrate_v1_2_event(old)
    assert migrated["schema_version"] == "1.2"
    assert all(
        migrated[field] is None
        for field in (
            "route_epoch_id",
            "route_activation_id",
            "producer_session_id",
            "registration_instance_id",
            "route_change_source",
        )
    )
