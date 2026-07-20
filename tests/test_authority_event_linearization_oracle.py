from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from scripts.oracles.authority_event_linearization_oracle import evaluate
from scripts.probes.c1_concurrency_monitor import CLOCK_PREFLIGHT_WARMUP_SAMPLES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/motivation/c1_concurrency"
SUMMARY = ROOT / "data/processed/motivation/c1_concurrency/c1_summary.json"
SCHEMA = json.loads(
    (ROOT / "data/schemas/authority_event_linearization_result.schema.json").read_text(
        encoding="utf-8"
    )
)


def _inputs(
    *,
    final_nav_state: int = 4,
    executor: int = 0,
    timing_order: str = "A_FIRST",
    bridge_status: str = "VALID",
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    event_a_ros_ns = 1_000_000_000
    event_b_ros_ns = 1_400_000_000
    if timing_order == "B_FIRST":
        event_a_ros_ns, event_b_ros_ns = event_b_ros_ns, event_a_ros_ns
    elif timing_order == "NEAR_SIMULTANEOUS":
        event_b_ros_ns = event_a_ros_ns
    inputs = [
        {
            "name": "external_activation",
            "monotonic_ns": event_a_ros_ns,
            "ros_time_ns": event_a_ros_ns,
            "origin": "public_interface",
        },
        {
            "name": "gcs_hold",
            "monotonic_ns": event_b_ros_ns,
            "ros_time_ns": event_b_ros_ns,
            "origin": "public_interface",
        },
    ]
    runner: dict[str, object] = {
        "run_id": "c1-synthetic",
        "pair": "A",
        "timing_order": timing_order,
        "status": "PASS",
        "external_mode_id": 23,
        "input_events": inputs,
        "linearization_final": {
            "nav_state": final_nav_state,
            "executor_in_charge": executor,
            "armed": True,
            "failsafe": False,
        },
        "cleanup": {"landed": True, "disarmed": True},
    }
    events = [
        {
            "event_type": "linearization_window_closed",
            "ros_time_ns": 1_600_000_000,
            "monotonic_ns": 1_600_000_000,
        }
    ]
    trace: list[dict[str, object]] = [
        {
            "event_type": "route_epoch_changed",
            "timestamp": 1_000_000,
            "declared_mode": 23,
            "route_epoch_id": 1,
        },
        {
            "event_type": "route_epoch_changed",
            "timestamp": 1_400_000,
            "declared_mode": final_nav_state,
            "route_epoch_id": 2,
        },
    ]
    for timestamp in range(904_000, 1_701_000, 8_000):
        trace.append(
            {
                "event_type": "actuator_output_published",
                "timestamp": timestamp,
                "route_epoch_id": 1 if timestamp <= 1_400_000 else 2,
                "actuator_writer": "control_allocator",
            }
        )
    bridge: dict[str, object] = {
        "status": bridge_status,
        "reference_px4_us": 1_000_000,
        "reference_ros_ns": 1_000_000_000,
        "rate_ratio": 1.0,
        "valid_from": 800_000,
        "valid_until": 2_000_000,
    }
    return runner, events, trace, bridge


def test_authority_schema_and_synthetic_linearization_pass() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    result = evaluate(*_inputs())
    Draft202012Validator(SCHEMA).validate(result)
    assert result["status"] == "PASS"
    assert all(clause["status"] == "PASS" for clause in result["clauses"].values())
    assert result["linearization"]["event_b_minus_event_a_ms"] == 400.0


def test_illegal_final_route_is_a_complete_evidence_violation() -> None:
    result = evaluate(*_inputs(final_nav_state=5))
    assert result["status"] == "VIOLATION"
    assert result["clauses"]["linearizable_final_route"]["status"] == "VIOLATION"
    assert result["evidence_completeness"]["unknown_reasons"] == []


def test_unexpected_executor_owner_is_a_violation() -> None:
    result = evaluate(*_inputs(executor=1))
    assert result["status"] == "VIOLATION"
    assert result["clauses"]["owner_uniqueness"]["status"] == "VIOLATION"


def test_invalid_clock_bridge_cannot_be_promoted() -> None:
    result = evaluate(*_inputs(bridge_status="INVALID"))
    assert result["status"] == "UNKNOWN"
    assert "clock_bridge_not_VALID" in result["evidence_completeness"]["unknown_reasons"]


def test_registered_timing_miss_is_not_a_sut_violation() -> None:
    runner, events, trace, bridge = _inputs()
    runner["input_events"][1]["monotonic_ns"] = 1_050_000_000  # type: ignore[index]
    result = evaluate(runner, events, trace, bridge)
    assert result["status"] == "UNKNOWN"
    assert result["clauses"]["relative_timing"]["status"] == "VIOLATION"
    assert "registered_relative_timing_precondition_not_satisfied" in (
        result["evidence_completeness"]["unknown_reasons"]
    )


def test_c1_preregistration_matrix_caps_and_locked_artifacts() -> None:
    profile = yaml.safe_load((BASE / "preregistration.yaml").read_text(encoding="utf-8"))
    amendment = yaml.safe_load(
        (BASE / "oracle_amendment_001.yaml").read_text(encoding="utf-8")
    )
    matrix = yaml.safe_load((BASE / "matrix.yaml").read_text(encoding="utf-8"))
    ledger = yaml.safe_load((BASE / "attempt_ledger.yaml").read_text(encoding="utf-8"))
    assert profile["status"] == "FROZEN_BEFORE_FORMAL_ATTEMPTS"
    assert profile["formal_matrix"]["accepted_target"] == 15
    assert profile["formal_matrix"]["maximum_total_attempts"] == 30
    assert profile["violation_confirmation"]["maximum_total_confirmation_attempts"] == 3
    assert len(matrix["slots"]) == 15
    assert sum(slot["accepted_runs_required"] for slot in matrix["slots"]) == 15
    assert sum(slot["maximum_attempts"] for slot in matrix["slots"]) == 30
    attempts = ledger["attempts"]
    accepted = [item for item in attempts if item["counted_as_accepted"]]
    assert matrix["accepted_runs"] == ledger["accepted_runs"] == len(accepted)
    assert matrix["total_attempts"] == ledger["total_attempts"] == len(attempts)
    assert ledger["campaign_configuration_failures"] == sum(
        item["disposition"] == "CAMPAIGN_CONFIGURATION_FAILURE" for item in attempts
    )
    assert ledger["attempts"][0]["disposition"] == "CAMPAIGN_CONFIGURATION_FAILURE"
    for slot in matrix["slots"]:
        slot_attempts = [item for item in attempts if item["slot_id"] == slot["slot_id"]]
        assert slot["attempts"] == len(slot_attempts)
        assert slot["accepted_runs"] == sum(
            item["counted_as_accepted"] for item in slot_attempts
        )
        assert slot["attempts"] <= slot["maximum_attempts"]
    harness_amendment = yaml.safe_load(
        (BASE / "harness_amendment_002.yaml").read_text(encoding="utf-8")
    )
    superseded = {
        **amendment["bounded_correction"]["replacement_hashes"],
        **harness_amendment["bounded_correction"]["replacement_hashes"],
    }
    old_hashes = {
        **amendment["bounded_correction"]["old_hashes"],
        **harness_amendment["bounded_correction"]["old_hashes"],
    }
    for relative, expected in profile["locked_artifacts"].items():
        if relative in superseded:
            assert old_hashes[relative] == expected
            expected = superseded[relative]
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert actual == expected
    for item in profile["locked_binaries"].values():
        actual = hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
        assert actual == item["sha256"]


def test_c1_oracle_amendment_is_analysis_only_and_preserves_bounds() -> None:
    amendment = yaml.safe_load(
        (BASE / "oracle_amendment_001.yaml").read_text(encoding="utf-8")
    )
    assert amendment["trigger_classification"] == "CAMPAIGN_CONFIGURATION_FAILURE"
    assert not amendment["bounded_correction"]["diagnostic_reanalysis"]["use_in_denominator"]
    invariants = amendment["invariants"]
    assert not invariants["px4_or_controller_behavior_change"]
    assert not invariants["code_read_by_sut"]
    assert not invariants["legal_serial_outcomes_changed"]
    assert not invariants["route_gap_threshold_changed"]
    assert not invariants["timing_threshold_changed"]
    assert not invariants["acceptance_or_rejection_rule_changed"]
    assert not invariants["attempt_caps_or_seeds_changed"]


def test_c1_warmup_amendment_applies_only_to_future_open_slots() -> None:
    amendment = yaml.safe_load(
        (BASE / "harness_amendment_002.yaml").read_text(encoding="utf-8")
    )
    assert amendment["closed_slot"] == "C1-A-NEAR_SIMULTANEOUS"
    assert amendment["closed_slot_will_not_be_retried"]
    assert amendment["bounded_correction"]["preflight_clock_samples"] == 10
    invariants = amendment["invariants"]
    assert not invariants["px4_controller_or_route_semantics_change"]
    assert not invariants["direct_nav_state_executor_or_failsafe_mutation"]
    assert not invariants["relative_event_timing_changed"]
    assert not invariants["clock_bridge_threshold_changed"]
    assert not invariants["attempt_caps_or_seeds_changed"]
    assert not invariants["prior_closed_slot_reopened"]


def test_c1_runner_is_bounded_and_uses_public_interfaces() -> None:
    runner = (ROOT / "scripts/probes/run_c1_concurrency.sh").read_text(encoding="utf-8")
    monitor = (ROOT / "scripts/probes/c1_concurrency_monitor.py").read_text(encoding="utf-8")
    subject = (
        ROOT / "scripts/adapters/external_mode_adapter/src/c1_concurrency_probe.cpp"
    ).read_text(encoding="utf-8")
    assert '--timeout 120' in runner
    assert CLOCK_PREFLIGHT_WARMUP_SAMPLES == 10
    assert "self.clock_samples >= CLOCK_PREFLIGHT_WARMUP_SAMPLES" in monitor
    assert 'stop_process "${MODE_PID}" TERM' in runner
    assert "VehicleCommand.VEHICLE_CMD_SET_NAV_STATE" in monitor
    assert "VehicleCommand.VEHICLE_CMD_NAV_RETURN_TO_LAUNCH" in monitor
    assert "setArmingCheckReplyEnabled" in subject
    assert "completed(px4_ros2::Result::Success)" in subject
    forbidden = (
        "self.status.nav_state =",
        "self.status.executor_in_charge =",
        "self.status.failsafe =",
    )
    assert not any(token in monitor for token in forbidden)


def test_c1_final_gate_preserves_bounded_negative_and_incomplete_slot() -> None:
    matrix = yaml.safe_load((BASE / "matrix.yaml").read_text(encoding="utf-8"))
    ledger = yaml.safe_load((BASE / "attempt_ledger.yaml").read_text(encoding="utf-8"))
    gate = json.loads((BASE / "c1_gate.json").read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert matrix["status"] == ledger["status"] == "FINAL_ANALYSIS_COMPLETE"
    assert matrix["accepted_runs"] == ledger["accepted_runs"] == 14
    assert matrix["total_attempts"] == ledger["total_attempts"] == 17
    assert ledger["violations"] == gate["accepted_oracle_violations"] == 0
    assert gate["status"] == "CONDITIONAL_PASS"
    assert gate["state_grammar_usable"]
    assert gate["measurement_insufficient_slots"] == ["C1-A-NEAR_SIMULTANEOUS"]
    assert not gate["authorizes_full_fuzzer_campaign"]
    assert summary["formal_matrix"]["oracle_pass"] == 14
    assert summary["confirmation"]["status"] == "NOT_TRIGGERED_NO_VIOLATIONS"
    assert summary["raw_evidence"]["ignored"]
