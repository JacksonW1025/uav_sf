from __future__ import annotations

from jsonschema import Draft202012Validator

from scripts.oracles.route_oracle_v0 import RESULT_SCHEMA, _mode_transition, evaluate


def _event(
    timestamp: int,
    event_type: str,
    mode: int,
    domain: str = "ulog_us",
    **extra: object,
) -> dict[str, object]:
    return {
        "schema_version": "1.2",
        "run_id": "oracle-test",
        "timestamp": timestamp,
        "timestamp_domain": domain,
        "event_type": event_type,
        "declared_mode": mode,
        "setpoint_level": extra.pop("setpoint_level", "velocity"),
        "enabled_modules": extra.pop("enabled_modules", ["mc_rate_control", "control_allocator"]),
        **extra,
    }


def _complete_events() -> list[dict[str, object]]:
    return [
        _event(0, "vehicle_status", 14),
        _event(5_000, "producer_still_publishing", 14, route_epoch_id=1),
        _event(10_000, "px4_setpoint_consumed", 14, route_epoch_id=1),
        _event(
            95_000,
            "actuator_output_published",
            14,
            actuator_writer="control_allocator",
            route_epoch_id=1,
        ),
        _event(100_000, "vehicle_status", 5),
        _event(
            105_000,
            "actuator_output_published",
            5,
            actuator_writer="control_allocator",
            route_epoch_id=2,
        ),
        _event(110_000, "px4_setpoint_consumed", 5, route_epoch_id=2),
        _event(115_000, "allocator_input_published", 5),
    ]


def _writer(status: str = "EXCLUSIVE") -> dict[str, object]:
    return {
        "status": status,
        "candidate_writers": ["control_allocator"],
        "observed_writers": ["control_allocator"],
        "uninstrumented_candidates": [],
        "sequence_gaps": [],
        "competing_windows": [] if status != "COMPETING_WRITERS" else [{}],
        "observation_holes": [],
        "expected_period_ms": 0,
        "transition_windows": [
            {
                "timestamp_us": 100_000,
                "from_mode": 14,
                "to_mode": 5,
                "start_us": 50_000,
                "end_us": 150_000,
                "observed_writers": (
                    ["control_allocator", "rover_ackermann"]
                    if status == "COMPETING_WRITERS"
                    else ["control_allocator"]
                ),
                "coverage_verdict": "COMPLETE",
                "maximum_gap_ms": 10.0,
            }
        ],
    }


def test_complete_same_boot_evidence_passes() -> None:
    result = evaluate(_complete_events(), _writer())
    Draft202012Validator(RESULT_SCHEMA).validate(result)
    assert result["status"] == "PASS"
    assert all(
        clause["status"] in {"PASS", "NOT_APPLICABLE"}
        for clause in result["clauses"].values()
    )
    assert result["clauses"]["revocation"]["metrics"]["post_revocation_consumption_count"] == 0


def test_missing_cross_domain_bridge_is_unknown() -> None:
    events = _complete_events()
    events[1] = _event(
        5_000_000,
        "producer_still_publishing",
        14,
        domain="ros_node_ns",
    )
    result = evaluate(events, _writer())
    assert result["status"] == "UNKNOWN"
    assert result["clauses"]["revocation"]["status"] == "UNKNOWN"


def test_competing_writer_is_violation() -> None:
    result = evaluate(_complete_events(), _writer("COMPETING_WRITERS"))
    assert result["status"] == "VIOLATION"
    assert result["clauses"]["exclusivity"]["status"] == "VIOLATION"


def test_shared_writer_without_route_epoch_is_unknown_not_violation() -> None:
    events = _complete_events()
    events[3].pop("route_epoch_id")
    events[5].pop("route_epoch_id")
    events.extend(
        [
            _event(200_000, "vehicle_status", 14),
            _event(205_000, "actuator_output_published", 14, actuator_writer="control_allocator"),
        ]
    )
    result = evaluate(events, _writer())
    assert result["status"] == "UNKNOWN"
    assert result["clauses"]["revocation"]["status"] == "UNKNOWN"
    assert result["clauses"]["revocation"]["metrics"]["post_revocation_writer_count"] is None


def test_no_transition_is_not_applicable() -> None:
    result = evaluate([_event(0, "vehicle_status", 4)], _writer())
    assert result["status"] == "NOT_APPLICABLE"
    assert all(
        clause["status"] == "NOT_APPLICABLE" for clause in result["clauses"].values()
    )


def test_executor_bookkeeping_exit_without_consumption_is_skipped() -> None:
    events = [
        _event(0, "vehicle_status", 4, route_epoch_id=1),
        _event(100, "vehicle_status", 23, route_epoch_id=2),
        _event(200, "vehicle_status", 17, route_epoch_id=3),
        _event(300, "vehicle_status", 23, route_epoch_id=4),
        _event(400, "px4_setpoint_consumed", 23, route_epoch_id=4),
        _event(500, "vehicle_status", 5, route_epoch_id=5),
    ]
    transition = _mode_transition(events)
    assert transition is not None
    assert transition["timestamp_us"] == 500
    assert transition["source_route_epoch_id"] == 4
