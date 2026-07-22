from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from scripts.oracles.session_rollover_oracle import CONTRACT_CLASSIFICATION, evaluate
from scripts.probes.r1_session_monitor import CLOCK_PREFLIGHT_WARMUP_SAMPLES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/motivation/r1_session"
SCHEMA = json.loads(
    (ROOT / "data/schemas/session_rollover_result.schema.json").read_text(encoding="utf-8")
)


def _inputs(
    *,
    scenario: str = "A",
    completion_provenance: str = "NONE",
    lifecycle_progressed: bool = False,
    successor_request: bool | None = None,
) -> tuple[
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    old_session = "r1-synthetic:old"
    new_session = "r1-synthetic:new"
    runner: dict[str, object] = {
        "schema_version": "1.0",
        "run_id": "r1-synthetic",
        "scenario": scenario,
        "status": "PASS",
        "clock_sample_count": 20,
        "expected_successor_nav_state": 5,
        "old_session": {
            "registration_request_id": 111,
            "registration_reply_request_id": 111,
            "registration_instance_id": 1001,
            "producer_session_id": old_session,
            "activation_id": 1,
            "mode_id": 23,
            "executor_id": 1,
            "stop_monotonic_ns": 1_500_000_000,
        },
        "new_session": {
            "registration_request_id": 222,
            "registration_reply_request_id": 222,
            "registration_instance_id": 2002,
            "producer_session_id": new_session,
            "activation_id": 1,
            "mode_id": 23,
            "executor_id": 1,
            "active_monotonic_ns": 2_000_000_000,
            "completion_wait_armed": scenario == "C",
        },
        "controller_graph_at_close": {"position": True, "allocator": True},
        "cleanup": {"landed": True, "disarmed": True},
    }
    if scenario == "C":
        if successor_request is None:
            successor_request = lifecycle_progressed
        runner["completion_event"] = {
            "created": True,
            "released_once": True,
            "release_count": 1,
            "observed": True,
            "provenance": completion_provenance,
            "producer_session_id": (
                old_session
                if completion_provenance == "EARLIER_SESSION"
                else new_session if completion_provenance == "NEW_SESSION" else None
            ),
            "new_lifecycle_progressed": lifecycle_progressed,
            "successor_request_observed": successor_request,
        }

    events: list[dict[str, object]] = [
        {
            "event_type": "r1_registration_request_observed",
            "session_role": "old",
            "request_id": 111,
            "ros_time_ns": 800_000_000,
        },
        {
            "event_type": "r1_registration_observed",
            "session_role": "old",
            "request_id": 111,
            "mode_id": 23,
            "executor_id": 1,
            "ros_time_ns": 850_000_000,
        },
        {
            "event_type": "old_session_active_snapshot",
            "ros_time_ns": 1_000_000_000,
            "monotonic_ns": 1_000_000_000,
            "mode_id": 23,
            "executor_in_charge": 1,
            "controller_graph": {"position": True, "allocator": True},
        },
        {
            "event_type": "r1_component_stopped",
            "session_role": "old",
            "ros_time_ns": 1_500_000_000,
            "monotonic_ns": 1_500_000_000,
        },
        {
            "event_type": "r1_registration_request_observed",
            "session_role": "new",
            "request_id": 222,
            "ros_time_ns": 1_700_000_000,
        },
        {
            "event_type": "r1_registration_observed",
            "session_role": "new",
            "request_id": 222,
            "mode_id": 23,
            "executor_id": 1,
            "ros_time_ns": 1_750_000_000,
        },
        {
            "event_type": "new_session_active_snapshot",
            "ros_time_ns": 2_000_000_000,
            "monotonic_ns": 2_000_000_000,
            "mode_id": 23,
            "executor_in_charge": 1,
            "controller_graph": {"position": True, "allocator": True},
        },
    ]
    if scenario == "C":
        events.append(
            {
                "event_type": "old_session_message_released_once",
                "ros_time_ns": 2_200_000_000,
                "monotonic_ns": 2_200_000_000,
            }
        )
    events.append(
        {
            "event_type": "r1_isolation_window_closed",
            "ros_time_ns": 3_000_000_000,
            "monotonic_ns": 3_000_000_000,
            "controller_graph": {"position": True, "allocator": True},
        }
    )

    trace: list[dict[str, object]] = [
        {
            "event_type": "route_epoch_changed",
            "timestamp": 900_000,
            "declared_mode": 23,
            "route_epoch_id": 10,
        },
        {
            "event_type": "route_epoch_changed",
            "timestamp": 1_900_000,
            "declared_mode": 23,
            "route_epoch_id": 20,
        },
    ]
    if lifecycle_progressed:
        trace.append(
            {
                "event_type": "route_epoch_changed",
                "timestamp": 2_300_000,
                "declared_mode": 5,
                "route_epoch_id": 21,
            }
        )
    for timestamp, event_type in (
        (2_050_000, "px4_setpoint_consumed"),
        (2_100_000, "allocator_input_published"),
        (2_150_000, "actuator_output_published"),
        (2_400_000, "px4_setpoint_consumed"),
        (2_450_000, "allocator_input_published"),
        (2_500_000, "actuator_output_published"),
    ):
        trace.append(
            {
                "event_type": event_type,
                "timestamp": timestamp,
                "route_epoch_id": 21 if lifecycle_progressed and timestamp >= 2_300_000 else 20,
            }
        )

    bridge: dict[str, object] = {
        "status": "VALID",
        "reference_px4_us": 1_000_000,
        "reference_ros_ns": 1_000_000_000,
        "rate_ratio": 1.0,
        "valid_from": 800_000,
        "valid_until": 3_200_000,
    }
    old_lifecycle: list[dict[str, object]] = [
        {
            "event_type": "external_mode_registered",
            "ros_time_ns": 850_000_000,
            "registration_instance_id": 1001,
            "producer_session_id": old_session,
            "mode_id": 23,
        },
        {
            "event_type": "external_mode_activated",
            "ros_time_ns": 950_000_000,
            "registration_instance_id": 1001,
            "producer_session_id": old_session,
            "activation_id": 1,
            "mode_id": 23,
        },
    ]
    new_lifecycle: list[dict[str, object]] = [
        {
            "event_type": "external_mode_registered",
            "ros_time_ns": 1_750_000_000,
            "registration_instance_id": 2002,
            "producer_session_id": new_session,
            "mode_id": 23,
        },
        {
            "event_type": "external_mode_activated",
            "ros_time_ns": 1_950_000_000,
            "registration_instance_id": 2002,
            "producer_session_id": new_session,
            "activation_id": 1,
            "mode_id": 23,
        },
    ]
    return runner, events, trace, bridge, old_lifecycle, new_lifecycle


def test_clean_reentry_pass() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    result = evaluate(*_inputs(scenario="A"))
    Draft202012Validator(SCHEMA).validate(result)
    assert result["status"] == "PASS"
    assert result["contract_classification"] == CONTRACT_CLASSIFICATION
    assert result["identities"]["old"]["mode_id"] == result["identities"]["new"]["mode_id"]
    assert result["identities"]["relation_established"]


def test_restart_pass() -> None:
    result = evaluate(*_inputs(scenario="B"))
    assert result["status"] == "PASS"
    assert result["clauses"]["lifecycle_owner_rollover"]["status"] == "PASS"


def test_new_session_completion_pass() -> None:
    result = evaluate(
        *_inputs(
            scenario="C", completion_provenance="NEW_SESSION", lifecycle_progressed=True
        )
    )
    assert result["status"] == "PASS"
    assert result["route_epochs"]["successor"] == 21
    assert result["clauses"]["completion_session_isolation"]["status"] == "PASS"


def test_earlier_session_completion_ignored_pass() -> None:
    result = evaluate(
        *_inputs(
            scenario="C", completion_provenance="EARLIER_SESSION", lifecycle_progressed=False
        )
    )
    assert result["status"] == "PASS"
    assert result["clauses"]["successor_progression"]["status"] == "NOT_APPLICABLE"


def test_instance_identity_ambiguity_is_exposure() -> None:
    result = evaluate(
        *_inputs(scenario="C", completion_provenance="AMBIGUOUS", lifecycle_progressed=False)
    )
    assert result["status"] == "EXPOSURE"
    assert result["completion"]["wire_instance_or_generation_fields"] == []
    assert result["clauses"]["completion_session_isolation"]["status"] == "EXPOSURE"


def test_earlier_session_completion_progresses_new_lifecycle_violation() -> None:
    result = evaluate(
        *_inputs(
            scenario="C", completion_provenance="EARLIER_SESSION", lifecycle_progressed=True
        )
    )
    assert result["status"] == "VIOLATION"
    assert result["clauses"]["completion_session_isolation"]["status"] == "VIOLATION"
    assert result["clauses"]["successor_progression"]["status"] == "PASS"


def test_missing_old_session_identity_unknown() -> None:
    inputs = list(_inputs(scenario="A"))
    old_lifecycle = inputs[4]
    old_lifecycle[0].pop("producer_session_id")
    old_lifecycle[1].pop("producer_session_id")
    runner = inputs[0]
    runner["old_session"].pop("producer_session_id")  # type: ignore[union-attr]
    result = evaluate(*inputs)
    assert result["status"] == "UNKNOWN"
    assert result["clauses"]["session_relation"]["status"] == "UNKNOWN"


def test_missing_new_activation_unknown() -> None:
    inputs = list(_inputs(scenario="A"))
    inputs[5].pop()
    inputs[0]["new_session"].pop("activation_id")  # type: ignore[union-attr]
    result = evaluate(*inputs)
    assert result["status"] == "UNKNOWN"
    assert result["identities"]["new"]["activation_key"] is None


def test_missing_successor_evidence_unknown() -> None:
    result = evaluate(
        *_inputs(
            scenario="C",
            completion_provenance="EARLIER_SESSION",
            lifecycle_progressed=True,
            successor_request=False,
        )
    )
    assert result["status"] == "UNKNOWN"
    assert result["clauses"]["successor_progression"]["status"] == "UNKNOWN"


def test_incomplete_cleanup_unknown() -> None:
    inputs = list(_inputs(scenario="A"))
    inputs[0]["cleanup"] = {"landed": True, "disarmed": None}
    result = evaluate(*inputs)
    assert result["status"] == "UNKNOWN"
    assert result["clauses"]["cleanup"]["status"] == "UNKNOWN"


def test_not_applicable_without_distinct_session_relation() -> None:
    inputs = list(_inputs(scenario="A"))
    runner = inputs[0]
    runner["new_session"] = dict(runner["old_session"])  # type: ignore[arg-type]
    runner["new_session"]["active_monotonic_ns"] = 2_000_000_000  # type: ignore[index]
    inputs[1][4]["request_id"] = 111
    inputs[1][5]["request_id"] = 111
    inputs[4] = [dict(item) for item in inputs[4]]
    inputs[5] = [dict(item) for item in inputs[4]]
    for item in inputs[5]:
        item["ros_time_ns"] = int(item["ros_time_ns"]) + 1_000_000_000
    result = evaluate(*inputs)
    assert result["status"] == "NOT_APPLICABLE"
    assert result["clauses"]["session_relation"]["status"] == "NOT_APPLICABLE"


def test_preregistration_matrix_caps_and_ledger_consistency() -> None:
    preregistration = yaml.safe_load((BASE / "preregistration.yaml").read_text(encoding="utf-8"))
    matrix = yaml.safe_load((BASE / "matrix.yaml").read_text(encoding="utf-8"))
    ledger = yaml.safe_load((BASE / "attempt_ledger.yaml").read_text(encoding="utf-8"))
    assert preregistration["status"] == "FROZEN_BEFORE_FORMAL_ATTEMPTS"
    assert preregistration["execution_gate"]["preregistration_commit_must_be_pushed"]
    assert preregistration["selected_r1_c_semantic"] == "ModeCompleted"
    assert preregistration["contract"]["classification"] == "B"
    assert preregistration["oracle"]["statuses"] == [
        "PASS",
        "EXPOSURE",
        "VIOLATION",
        "UNKNOWN",
        "NOT_APPLICABLE",
    ]
    assert matrix["accepted_target"] == 9
    assert matrix["maximum_attempts_per_scenario"] == 6
    assert matrix["maximum_total_attempts"] == 18
    assert len(matrix["scenarios"]) == 3
    assert sum(item["accepted_runs_required"] for item in matrix["scenarios"]) == 9
    assert sum(item["maximum_attempts"] for item in matrix["scenarios"]) == 18
    assert ledger["preregistration_commit"] == (
        "9faad09d0e9e7631497034e7ee27f8ab2ce9d896"
    )
    attempts = ledger["attempts"]
    accepted = [item for item in attempts if item["counted_as_accepted"]]
    assert matrix["accepted_runs"] == ledger["accepted_runs"] == len(accepted)
    assert matrix["total_attempts"] == ledger["total_attempts"] == len(attempts)
    assert ledger["attempt_classifications"]["FORMAL_SAFETY_STOP"] == sum(
        item["disposition"] == "FORMAL_SAFETY_STOP" for item in attempts
    )
    for scenario in matrix["scenarios"]:
        scenario_attempts = [
            item for item in attempts if item["scenario_id"] == scenario["scenario_id"]
        ]
        assert scenario["attempts"] == len(scenario_attempts)
        assert scenario["accepted_runs"] == sum(
            item["counted_as_accepted"] for item in scenario_attempts
        )
        assert scenario["attempts"] <= scenario["maximum_attempts"]
        assert [item["simulation_seed"] for item in scenario_attempts] == (
            scenario["seed_schedule"][: len(scenario_attempts)]
        )


def test_preregistered_source_and_binary_identity_is_exact() -> None:
    preregistration = yaml.safe_load((BASE / "preregistration.yaml").read_text(encoding="utf-8"))
    for relative, expected in preregistration["locked_artifacts"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected

    missing_local_binaries = []
    for binary in preregistration["locked_binaries"].values():
        path = ROOT / binary["path"]
        if not path.is_file():
            missing_local_binaries.append(binary["path"])
            continue
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binary["sha256"]

    if missing_local_binaries:
        pytest.skip(
            "locked local runtime binaries are intentionally absent from a clean "
            "checkout; formal R1 preflight requires all binaries: "
            + ", ".join(missing_local_binaries)
        )


def test_harness_contract_is_bounded_and_local() -> None:
    runner = (ROOT / "scripts/probes/run_r1_session.sh").read_text(encoding="utf-8")
    monitor = (ROOT / "scripts/probes/r1_session_monitor.py").read_text(encoding="utf-8")
    subject = (
        ROOT / "scripts/adapters/r1_session_adapter/src/r1_session_probe.cpp"
    ).read_text(encoding="utf-8")
    assert '--timeout 150' in runner
    assert CLOCK_PREFLIGHT_WARMUP_SAMPLES == 20
    assert "self.clock_samples >= CLOCK_PREFLIGHT_WARMUP_SAMPLES" in monitor
    assert '[[ ! -e "${RAW_DIR}" ]]' in runner
    assert "/fmu/in/mode_completed" in monitor
    assert "release_count=1" in monitor
    assert "RegisterExtComponentRequest" in monitor
    assert "request_id=int(message.request_id)" in monitor
    assert "executor_successor_requested" in subject
    assert "rtl([this]" in subject
    forbidden = (
        "self.status.nav_state =",
        "self.status.executor_in_charge =",
        "self.status.failsafe =",
    )
    assert not any(token in monitor for token in forbidden)


def test_semantic_audit_is_revision_locked_and_neutral() -> None:
    audit = (ROOT / "docs/motivation/R1_SESSION_SEMANTIC_AUDIT.md").read_text(
        encoding="utf-8"
    )
    assert "4ae21a5e569d3d89c2f6366688cbacb3e93437c9" in audit
    assert "18ecff03041c6f8d8a0012fbc63af0b23dd60af1" in audit
    assert "c3e410f035806e8c56246708432ded09c976434b" in audit
    assert "`timestamp`, `result`, and `nav_state`" in audit
    assert "completion-session isolation check" in audit
    assert (
        "Mere observation or apparent\nacceptance is not automatically classified as a defect."
        in audit
    )
    state = (ROOT / "docs/repository/MOTIVATION_COMPLETION_STATE.md").read_text(
        encoding="utf-8"
    )
    assert "Record and push final C1 commit" not in state
    assert "d78a206080a033f20fbd66fdb940c2ff8b1040d2" in state
