from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[1]
CASE_SCHEMA = json.loads(
    (ROOT / "data/schemas/fuzz_case.schema.json").read_text(encoding="utf-8")
)
RESULT_SCHEMA = json.loads(
    (ROOT / "data/schemas/fuzz_result.schema.json").read_text(encoding="utf-8")
)


def valid_case() -> dict:
    return {
        "schema_version": "1.0",
        "case_id": "p2-sigterm-hover",
        "seed_id": "p2.sigterm.hover",
        "route_family": "family_a_external_autonomy",
        "source_route": "dynamic_external_mode",
        "target_route": "internal_hold",
        "fallback_route": "internal_hold",
        "behavior_context": "hover",
        "initial_state_constraints": {
            "armed": True,
            "minimum_altitude_m": 2.0,
            "maximum_speed_m_s": 1.0,
            "maximum_descent_rate_m_s": 0.3,
            "maximum_turn_rate_rad_s": 0.2,
        },
        "transition_events": [
            {"event_id": "fault", "kind": "process_sigterm", "offset_s": 2.0},
            {"event_id": "fallback", "kind": "fallback", "offset_s": 3.0},
        ],
        "channel_states": [
            {
                "offset_s": 0.0,
                "liveness": "on",
                "setpoint": "on",
                "registration": "registered",
                "process_state": "running",
            }
        ],
        "faults": [
            {
                "fault_id": "producer-term",
                "kind": "sigterm",
                "target_session": "case_producer",
                "event_id": "fault",
            }
        ],
        "timing": {
            "fault_offset_s": 2.0,
            "heartbeat_setpoint_skew_s": 0.0,
            "repeated_transition_interval_s": 2.0,
            "maximum_duration_s": 120.0,
        },
        "repetition": {"count": 1, "simulation_seed": 501},
        "environment": {
            "profile": "canonical",
            "vehicle": "x500",
            "world": "default",
            "sitl_only": True,
            "wind_m_s": 0.0,
            "observation_profile": "TRANSITION",
        },
        "provenance": {"source": "p2", "source_case": "p2-sigterm"},
    }


def test_fuzz_schemas_are_valid_and_accept_bounded_case() -> None:
    Draft202012Validator.check_schema(CASE_SCHEMA)
    Draft202012Validator.check_schema(RESULT_SCHEMA)
    Draft202012Validator(CASE_SCHEMA).validate(valid_case())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vehicle", "real_x500"),
        ("world", "hardware"),
        ("sitl_only", False),
        ("wind_m_s", 2.1),
    ],
)
def test_case_schema_rejects_execution_outside_safety_envelope(field, value) -> None:
    case = copy.deepcopy(valid_case())
    case["environment"][field] = value
    with pytest.raises(ValidationError):
        Draft202012Validator(CASE_SCHEMA).validate(case)


def test_case_schema_rejects_arbitrary_event_and_shell_fields() -> None:
    case = valid_case()
    case["transition_events"][0]["kind"] = "shell"
    case["transition_events"][0]["command"] = "do-not-run"
    with pytest.raises(ValidationError):
        Draft202012Validator(CASE_SCHEMA).validate(case)
