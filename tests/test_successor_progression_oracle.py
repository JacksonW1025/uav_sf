from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from scripts.oracles.successor_progression_oracle import evaluate


ROOT = Path(__file__).resolve().parents[1]
PROFILE = yaml.safe_load(
    (ROOT / "experiments/motivation/successor/baseline_lifecycle_profile.yaml").read_text(
        encoding="utf-8"
    )
)
EVENT_SCHEMA = json.loads(
    (ROOT / "data/schemas/successor_lifecycle_event.schema.json").read_text(encoding="utf-8")
)
RESULT_SCHEMA = json.loads(
    (ROOT / "data/schemas/successor_oracle_result.schema.json").read_text(encoding="utf-8")
)


def event(
    event_type: str,
    timestamp_ns: int,
    *,
    mode: int | None = None,
    executor: int | None = None,
    armed: bool | None = None,
    landed: bool | None = None,
    registered_mode: int | None = None,
    registered_executor: int | None = None,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "run_id": "successor-test",
        "event_type": event_type,
        "ros_time_ns": timestamp_ns,
        "monotonic_ns": timestamp_ns,
        "px4_timestamp_us": timestamp_ns // 1000,
        "active_mode": mode,
        "nav_state_user_intention": mode,
        "executor_in_charge": executor,
        "arming_state": 2 if armed else (1 if armed is False else None),
        "armed": armed,
        "landed": landed,
        "failsafe": False,
        "registered_mode_id": registered_mode,
        "registered_executor_id": registered_executor,
        "owned_mode": registered_mode,
        "details": details or {},
    }


def passing_inputs() -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, object],
    dict[str, object],
]:
    lifecycle = [
        event("monitor_started", 1_000),
        event(
            "registration_observed",
            2_000,
            registered_mode=23,
            registered_executor=1,
            details={"success": True, "mode_id": 23, "mode_executor_id": 1},
        ),
        event(
            "vehicle_status_observed",
            3_000,
            mode=23,
            executor=1,
            armed=True,
            registered_mode=23,
            registered_executor=1,
        ),
        event(
            "mode_completed_observed",
            10_000_000,
            mode=23,
            executor=1,
            armed=True,
            registered_mode=23,
            registered_executor=1,
            details={"nav_state": 23, "result": 0},
        ),
        event(
            "executor_command_observed",
            20_000_000,
            mode=23,
            executor=1,
            armed=True,
            registered_mode=23,
            registered_executor=1,
            details={"command": 100001, "param1": 18, "source_component": 1001},
        ),
        event(
            "vehicle_status_observed",
            30_000_000,
            mode=18,
            executor=1,
            armed=True,
            registered_mode=23,
            registered_executor=1,
        ),
        event(
            "land_detected_observed",
            40_000_000,
            mode=18,
            executor=1,
            armed=True,
            landed=True,
            registered_mode=23,
            registered_executor=1,
            details={"landed": True},
        ),
        event(
            "vehicle_status_observed",
            50_000_000,
            mode=18,
            executor=1,
            armed=False,
            landed=True,
            registered_mode=23,
            registered_executor=1,
        ),
        event(
            "monitor_finished",
            60_000_000,
            mode=18,
            executor=1,
            armed=False,
            landed=True,
            registered_mode=23,
            registered_executor=1,
            details={"status": "PASS"},
        ),
    ]
    executor_events = [
        {"event_type": "external_mode_completed", "ros_time_ns": 9_000_000},
        {
            "event_type": "executor_result",
            "stage": "external_mode_complete",
            "result": "Success",
            "ros_time_ns": 11_000_000,
        },
        {"event_type": "external_mode_deactivated", "ros_time_ns": 31_000_000},
    ]
    route_events = [
        {
            "event_type": "route_epoch_changed",
            "declared_mode": 18,
            "route_epoch_id": 5,
            "timestamp": 30_000,
            "timestamp_domain": "ulog_us",
        }
    ]
    route_oracle = {
        "status": "PASS",
        "transition": {
            "source_mode": 23,
            "target_mode": 18,
            "source_route_epoch_id": 4,
        },
        "clauses": {"installation": {"status": "PASS"}},
    }
    clock_bridge = {"status": "VALID"}
    return lifecycle, executor_events, route_events, route_oracle, clock_bridge


def test_schemas_are_valid_and_profile_is_explicit() -> None:
    Draft202012Validator.check_schema(EVENT_SCHEMA)
    Draft202012Validator.check_schema(RESULT_SCHEMA)
    assert PROFILE["expected_successor"]["selected_nav_state"] == 18
    assert PROFILE["expected_successor"]["command"] == 100001
    assert PROFILE["expected_successor"]["command_param1"] == 18
    assert PROFILE["missing_required_evidence"] == "UNKNOWN"


def test_conforming_completion_land_disarm_chain_passes() -> None:
    result = evaluate(PROFILE, *passing_inputs())
    Draft202012Validator(RESULT_SCHEMA).validate(result)
    assert result["status"] == "PASS"
    assert {name: clause["status"] for name, clause in result["clauses"].items()} == {
        "ownership": "PASS",
        "completion": "PASS",
        "successor_request": "PASS",
        "successor_installation": "PASS",
        "mission_progression": "PASS",
    }
    assert result["violation_categories"] == []


def test_issue_162_pattern_detects_wrong_owner_and_missing_successor() -> None:
    lifecycle, executor_events, route_events, _, clock_bridge = passing_inputs()
    lifecycle = [
        {
            **item,
            "executor_in_charge": 0 if item["active_mode"] == 23 else item["executor_in_charge"],
        }
        for item in lifecycle
        if item["event_type"] not in {
            "executor_command_observed",
            "land_detected_observed",
        }
        and item["active_mode"] != 18
    ]
    lifecycle.append({
        **lifecycle[-1],
        "event_type": "monitor_finished",
        "ros_time_ns": 60_000_000,
        "monotonic_ns": 60_000_000,
        "details": {"status": "FAIL"},
        "armed": True,
        "arming_state": 2,
    })
    result = evaluate(PROFILE, lifecycle, executor_events[:2], route_events, None, clock_bridge)
    assert result["status"] == "VIOLATION"
    assert result["clauses"]["ownership"]["status"] == "VIOLATION"
    assert result["clauses"]["successor_request"]["status"] == "VIOLATION"
    assert {
        "EXECUTOR_NOT_IN_CHARGE",
        "EXPECTED_SUCCESSOR_NOT_REQUESTED",
        "LIFECYCLE_DEAD_END",
    } <= set(result["violation_categories"])


def test_missing_evidence_stays_unknown() -> None:
    lifecycle = [event("monitor_started", 1_000)]
    result = evaluate(PROFILE, lifecycle, [], [], None, None)
    assert result["status"] == "UNKNOWN"
    assert all(
        clause["status"] == "UNKNOWN" for clause in result["clauses"].values()
    )


def test_generated_completion_without_receiver_is_violation() -> None:
    lifecycle, executor_events, route_events, route_oracle, clock_bridge = passing_inputs()
    executor_events = [
        item for item in executor_events if item["event_type"] != "executor_result"
    ]
    result = evaluate(
        PROFILE, lifecycle, executor_events, route_events, route_oracle, clock_bridge
    )
    assert result["status"] == "VIOLATION"
    assert result["clauses"]["completion"]["status"] == "VIOLATION"
    assert "COMPLETION_NOT_DELIVERED" in result["violation_categories"]


def test_unknown_route_installation_is_not_promoted_to_pass() -> None:
    lifecycle, executor_events, route_events, route_oracle, clock_bridge = passing_inputs()
    route_oracle["clauses"]["installation"]["status"] = "UNKNOWN"
    result = evaluate(
        PROFILE, lifecycle, executor_events, route_events, route_oracle, clock_bridge
    )
    assert result["status"] == "UNKNOWN"
    assert result["clauses"]["successor_installation"]["status"] == "UNKNOWN"


def test_command_from_wrong_source_is_not_expected_successor_request() -> None:
    lifecycle, executor_events, route_events, route_oracle, clock_bridge = passing_inputs()
    command = next(
        item for item in lifecycle if item["event_type"] == "executor_command_observed"
    )
    command["details"]["source_component"] = 1002
    result = evaluate(
        PROFILE, lifecycle, executor_events, route_events, route_oracle, clock_bridge
    )
    assert result["status"] == "VIOLATION"
    assert result["clauses"]["successor_request"]["status"] == "VIOLATION"
    assert "EXPECTED_SUCCESSOR_NOT_REQUESTED" in result["violation_categories"]


def test_set_nav_state_command_for_wrong_mode_is_not_land_request() -> None:
    lifecycle, executor_events, route_events, route_oracle, clock_bridge = passing_inputs()
    command = next(
        item for item in lifecycle if item["event_type"] == "executor_command_observed"
    )
    command["details"]["param1"] = 5
    result = evaluate(
        PROFILE, lifecycle, executor_events, route_events, route_oracle, clock_bridge
    )
    assert result["status"] == "VIOLATION"
    assert result["clauses"]["successor_request"]["status"] == "VIOLATION"


def test_explicitly_unsupported_profile_is_not_applicable() -> None:
    profile = {**PROFILE, "profile_id": "unsupported", "applicability": "NOT_APPLICABLE"}
    result = evaluate(profile, [], [], [], None, None)
    assert result["status"] == "NOT_APPLICABLE"
    assert all(
        clause["status"] == "NOT_APPLICABLE" for clause in result["clauses"].values()
    )
