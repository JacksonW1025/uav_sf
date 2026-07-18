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
        _event(90_000, "allocator_input_published", 14, route_epoch_id=1),
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


def _bridge(status: str = "VALID") -> dict[str, object]:
    return {
        "clock_bridge_id": "clock-retained-test",
        "status": status,
        "offset_ns": 1_000_000_000,
        "rate_ratio": 1.0,
        "reference_px4_us": 0,
        "reference_ros_ns": 1_000_000_000,
        "uncertainty_ns": 0,
        "valid_from": 0,
        "valid_until": 5_000_000,
    }


def _retained_events(*, writer_gap: bool = False) -> list[dict[str, object]]:
    events = [
        _event(
            1_000_000_000,
            "channel_configuration_applied",
            23,
            domain="ros_node_ns",
        ),
        _event(
            1_000_000_000,
            "experiment_window_started",
            23,
            domain="ros_node_ns",
        ),
        _event(
            5_000_000_000,
            "probe_state_transition",
            23,
            domain="ros_node_ns",
        ),
        _event(
            400_000,
            "vehicle_status",
            23,
            route_epoch_id=7,
            authority_source="dynamic_external_mode",
            registration_state={"registered": True, "mode_id": 23},
        ),
        _event(
            1_500_000,
            "vehicle_status",
            23,
            route_epoch_id=7,
            authority_source="dynamic_external_mode",
            registration_state={"registered": True, "mode_id": 23},
        ),
        _event(
            2_500_000,
            "vehicle_status",
            23,
            route_epoch_id=7,
            authority_source="dynamic_external_mode",
            registration_state={"registered": True, "mode_id": 23},
        ),
        _event(
            3_600_000,
            "vehicle_status",
            23,
            route_epoch_id=7,
            authority_source="dynamic_external_mode",
            registration_state={"registered": True, "mode_id": 23},
        ),
    ]
    timestamps = list(range(500_000, 3_500_001, 10_000))
    if writer_gap:
        timestamps = [timestamp for timestamp in timestamps if not 1_000_000 < timestamp < 1_120_000]
    for sequence, timestamp in enumerate(timestamps, start=1):
        events.append(
            _event(
                timestamp,
                "actuator_output_published",
                23,
                route_epoch_id=7,
                authority_source="dynamic_external_mode",
                actuator_writer="control_allocator",
                observation={"sequence": sequence},
            )
        )
    return events


def _retained_writer() -> dict[str, object]:
    return {
        "candidate_writers": ["control_allocator"],
        "observed_writers": ["control_allocator"],
        "uninstrumented_candidates": [],
        "expected_period_ms": 10,
    }


def test_complete_same_boot_evidence_passes() -> None:
    result = evaluate(_complete_events(), _writer())
    Draft202012Validator(RESULT_SCHEMA).validate(result)
    assert result["status"] == "PASS"
    assert all(
        clause["status"] in {"PASS", "NOT_APPLICABLE"}
        for clause in result["clauses"].values()
    )
    assert result["route_oracle_version"] == "0.4"
    assert result["schema_version"] == "1.3"
    assert result["observation_kind"] == "TRANSITION"
    assert result["threshold_profile_id"] == "route-oracle-v0.3-default"
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
    events[4].pop("route_epoch_id")
    events[6].pop("route_epoch_id")
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


def test_complete_artifact_turns_missing_installation_into_violation() -> None:
    events = [
        event
        for event in _complete_events()
        if not (event["event_type"] == "px4_setpoint_consumed" and event["declared_mode"] == 5)
    ]
    result = evaluate(events, _writer(), source_artifact_complete=True)
    assert result["clauses"]["installation"]["status"] == "VIOLATION"


def test_incomplete_artifact_keeps_missing_installation_unknown() -> None:
    events = [
        event
        for event in _complete_events()
        if not (event["event_type"] == "px4_setpoint_consumed" and event["declared_mode"] == 5)
    ]
    result = evaluate(events, _writer(), source_artifact_complete=False)
    assert result["clauses"]["installation"]["status"] == "UNKNOWN"


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


def test_conforming_retained_route_passes_with_explicit_applicability() -> None:
    result = evaluate(
        _retained_events(),
        _retained_writer(),
        _bridge(),
        observation_kind="retained-route",
        retained_route_mode=23,
        source_artifact_complete=True,
    )
    Draft202012Validator(RESULT_SCHEMA).validate(result)
    assert result["status"] == "PASS"
    assert result["observation_kind"] == "RETAINED_ROUTE"
    assert result["transition"] is None
    assert result["violation_categories"] == []
    assert {
        name: clause["status"] for name, clause in result["clauses"].items()
    } == {
        "revocation": "NOT_APPLICABLE",
        "installation": "NOT_APPLICABLE",
        "exclusivity": "PASS",
        "continuity": "PASS",
        "recovery": "NOT_APPLICABLE",
    }
    assert result["retained_route"]["coverage_verdict"] == "COMPLETE"


def test_retained_route_unexpected_fallback_is_violation() -> None:
    events = _retained_events()
    events.append(
        _event(
            2_000_000,
            "route_epoch_changed",
            4,
            route_epoch_id=8,
            authority_source="px4_internal",
        )
    )
    result = evaluate(
        events,
        _retained_writer(),
        _bridge(),
        observation_kind="retained-route",
        retained_route_mode=23,
        source_artifact_complete=True,
    )
    assert result["status"] == "VIOLATION"
    assert "UNEXPECTED_FALLBACK" in result["violation_categories"]


def test_retained_route_proved_writer_gap_is_continuity_violation() -> None:
    result = evaluate(
        _retained_events(writer_gap=True),
        _retained_writer(),
        _bridge(),
        observation_kind="retained-route",
        retained_route_mode=23,
        source_artifact_complete=True,
    )
    assert result["status"] == "VIOLATION"
    assert result["clauses"]["continuity"]["status"] == "VIOLATION"
    assert "ROUTE_RETENTION_GAP" in result["violation_categories"]


def test_retained_route_writer_overlap_is_exclusivity_violation() -> None:
    events = _retained_events()
    events.append(
        _event(
            2_000_000,
            "actuator_output_published",
            23,
            route_epoch_id=7,
            authority_source="dynamic_external_mode",
            actuator_writer="direct_actuator",
            observation={"sequence": 1},
        )
    )
    result = evaluate(
        events,
        _retained_writer(),
        _bridge(),
        observation_kind="retained-route",
        retained_route_mode=23,
        source_artifact_complete=True,
    )
    assert result["status"] == "VIOLATION"
    assert result["clauses"]["exclusivity"]["status"] == "VIOLATION"
    assert "WRITER_CONFLICT" in result["violation_categories"]


def test_retained_route_missing_epoch_is_unknown() -> None:
    events = _retained_events()
    for event in events:
        event.pop("route_epoch_id", None)
    result = evaluate(
        events,
        _retained_writer(),
        _bridge(),
        observation_kind="retained-route",
        retained_route_mode=23,
        source_artifact_complete=True,
    )
    assert result["status"] == "UNKNOWN"
    assert result["evidence_completeness"]["route_epoch"] == "INCOMPLETE"


def test_retained_route_invalid_clock_is_unknown() -> None:
    result = evaluate(
        _retained_events(),
        _retained_writer(),
        _bridge("INVALID"),
        observation_kind="retained-route",
        retained_route_mode=23,
        source_artifact_complete=True,
    )
    assert result["status"] == "UNKNOWN"
    assert result["evidence_completeness"]["critical_window"] == "INSUFFICIENT"
