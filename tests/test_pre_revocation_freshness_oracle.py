from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.oracles.pre_revocation_freshness_oracle import evaluate


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "data/schemas/pre_revocation_freshness_result.schema.json").read_text(
        encoding="utf-8"
    )
)


PROFILE = {
    "profile_id": "freshness-synthetic-v0.1",
    "applicability": "APPLICABLE",
    "policy": {
        "freshness": "EXPLICIT",
        "setpoint_timeout_ms": 100,
        "measurement_tolerance_ms": 5,
        "max_publish_after_fault_ms": 10,
        "health_loss_deadline_ms": 1500,
        "fallback_installation_after_health_ms": 250,
        "post_fallback_external_effect_grace_ms": 20,
        "physical_recovery_after_fallback_ms": 2000,
    },
    "physical_thresholds": {
        "maximum_attitude_excursion_deg": 45,
        "maximum_angular_rate_excursion_rad_s": 3,
        "altitude_loss_m": 1,
        "horizontal_displacement_m": 3,
    },
}


def observation() -> dict[str, object]:
    return {
        "run_id": "freshness-test",
        "setpoint_type": "RATE",
        "fault_type": "TOTAL_PROCESS_STOP",
        "producer_stopped": True,
        "health_alive_through_target_window": False,
        "external_route_retained_at_window_end": False,
        "environment_status": "VALID",
        "clock_bridge_status": "VALID",
        "windows": {
            "pre_fault_stable": "COMPLETE",
            "pre_revocation_target": "COMPLETE",
            "fallback": "COMPLETE",
        },
        "timestamps_us": {
            "fault_injection": 1_000_000,
            "producer_last_publish": 1_000_000,
            "px4_last_setpoint_receive": 1_010_000,
            "last_setpoint_consumption": 1_090_000,
            "last_external_allocator_input": 1_095_000,
            "last_external_writer_output": 1_100_000,
            "health_loss_detection": 2_200_000,
            "fallback_declared": 2_210_000,
            "fallback_installed": 2_230_000,
            "physical_recovery": 3_000_000,
        },
        "physical_metrics": {
            "maximum_attitude_excursion_deg": 20,
            "maximum_angular_rate_excursion_rad_s": 1.5,
            "altitude_loss_m": 0.2,
            "horizontal_displacement_m": 0.4,
        },
        "inputs": {"clock_bridge": "VALID"},
    }


def assert_valid(result: dict[str, object]) -> None:
    Draft202012Validator(SCHEMA).validate(result)


def test_schema_is_valid() -> None:
    Draft202012Validator.check_schema(SCHEMA)


def test_clean_stop_and_prompt_fallback_passes() -> None:
    result = evaluate(PROFILE, observation())
    assert_valid(result)
    assert result["status"] == "PASS"
    assert result["eligible_for_accepted_run"] is True


def test_bounded_stale_exposure_without_policy_is_exposure() -> None:
    profile = copy.deepcopy(PROFILE)
    profile["policy"]["freshness"] = "NONE"
    profile["policy"]["setpoint_timeout_ms"] = None
    result = evaluate(profile, observation())
    assert result["status"] == "EXPOSURE"
    assert result["clauses"]["setpoint_freshness"]["status"] == "EXPOSURE"
    assert result["clauses"]["allocator_writer_continuation"]["status"] == "EXPOSURE"


def test_policy_exceeding_stale_exposure_is_violation() -> None:
    observed = observation()
    observed["timestamps_us"]["last_setpoint_consumption"] = 1_130_001
    observed["timestamps_us"]["last_external_allocator_input"] = 1_140_000
    observed["timestamps_us"]["last_external_writer_output"] = 1_145_000
    result = evaluate(PROFILE, observed)
    assert result["status"] == "VIOLATION"
    assert "SETPOINT_POLICY_DEADLINE_EXCEEDED" in result["categories"]


def test_health_alive_setpoint_stall_retains_route_as_exposure() -> None:
    profile = copy.deepcopy(PROFILE)
    profile["policy"]["freshness"] = "NONE"
    profile["policy"]["setpoint_timeout_ms"] = None
    observed = observation()
    observed["fault_type"] = "SETPOINT_ONLY_STALL"
    observed["health_alive_through_target_window"] = True
    observed["external_route_retained_at_window_end"] = True
    observed["timestamps_us"]["last_setpoint_consumption"] = 4_000_000
    observed["timestamps_us"]["last_external_allocator_input"] = 4_000_000
    observed["timestamps_us"]["last_external_writer_output"] = 4_000_000
    for name in (
        "health_loss_detection",
        "fallback_declared",
        "fallback_installed",
        "physical_recovery",
    ):
        observed["timestamps_us"][name] = None
    result = evaluate(profile, observed)
    assert result["status"] == "EXPOSURE"
    assert result["clauses"]["fallback_detection"]["status"] == "PASS"
    assert result["clauses"]["fallback_installation"]["status"] == "PASS"
    assert result["clauses"]["recovery"]["status"] == "NOT_APPLICABLE"


def test_continued_setpoint_with_health_lost_has_no_cessation_window() -> None:
    observed = observation()
    observed["fault_type"] = "HEALTH_ONLY_STOP"
    observed["producer_stopped"] = False
    result = evaluate(PROFILE, observed)
    assert result["status"] == "NOT_APPLICABLE"


def test_missing_receive_timestamp_is_unknown() -> None:
    observed = observation()
    observed["timestamps_us"]["px4_last_setpoint_receive"] = None
    result = evaluate(PROFILE, observed)
    assert result["status"] == "UNKNOWN"
    assert result["clauses"]["setpoint_freshness"]["status"] == "UNKNOWN"


def test_missing_consumption_evidence_is_unknown() -> None:
    observed = observation()
    observed["timestamps_us"]["last_setpoint_consumption"] = None
    result = evaluate(PROFILE, observed)
    assert result["status"] == "UNKNOWN"
    assert result["clauses"]["controller_continuation"]["status"] == "UNKNOWN"


def test_incomplete_target_window_is_unknown() -> None:
    observed = observation()
    observed["windows"]["pre_revocation_target"] = "INCOMPLETE"
    result = evaluate(PROFILE, observed)
    assert result["status"] == "UNKNOWN"


def test_environment_failure_is_unknown_and_excluded() -> None:
    observed = observation()
    observed["environment_status"] = "ENVIRONMENT_FAILURE"
    result = evaluate(PROFILE, observed)
    assert result["status"] == "UNKNOWN"
    assert result["eligible_for_accepted_run"] is False
    assert result["exclusion_reason"] == "ENVIRONMENT_FAILURE"
    assert "ENVIRONMENT_FAILURE" in result["categories"]


def test_invalid_clock_bridge_is_unknown_and_excluded() -> None:
    observed = observation()
    observed["clock_bridge_status"] = "DEGRADED"
    result = evaluate(PROFILE, observed)
    assert result["status"] == "UNKNOWN"
    assert result["eligible_for_accepted_run"] is False
    assert result["exclusion_reason"] == "MEASUREMENT_UNKNOWN"


def test_explicit_not_applicable_profile() -> None:
    profile = copy.deepcopy(PROFILE)
    profile["applicability"] = "NOT_APPLICABLE"
    result = evaluate(profile, observation())
    assert result["status"] == "NOT_APPLICABLE"
    assert all(
        clause["status"] == "NOT_APPLICABLE"
        for clause in result["clauses"].values()
    )
