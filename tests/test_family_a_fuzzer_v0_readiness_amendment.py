from __future__ import annotations

import copy
import json
import math
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

from scripts.fuzzer_v0.family_a import build_v0p_compact_evidence as evidence
from scripts.fuzzer_v0.family_a import check_v0p_cleanup as cleanup
from scripts.fuzzer_v0.family_a import check_v0p_runtime_residue as residue
from scripts.fuzzer_v0.family_a import check_v0p_safety as safety
from scripts.fuzzer_v0.family_a import run_v0p_qualification as runner
from scripts.fuzzer_v0.family_a.common import (
    ContractError,
    enforce_scope,
    load_scenario_map,
    validate_manifest,
)
from scripts.setup.verify_family_a_v0p_environment import validate as validate_environment


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/fuzzer_v0/family_a/run_v0p_qualification.py"
ORIGINAL_DECISION = (
    ROOT
    / "experiments/fuzzer_v0/family_a/activation_review/qualification_activation_decision.json"
)
QUALIFICATION_LEDGER = (
    ROOT
    / "experiments/fuzzer_v0/family_a/activation_review/qualification_attempt_ledger.yaml"
)
FROZEN_LEDGER = ROOT / "experiments/fuzzer_v0/family_a/attempt_ledger.yaml"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _safety_pass_fixture() -> dict[str, object]:
    return {
        "command_values": [0.0, 0.5, -0.2],
        "observed_controller_values": [0.0, 0.4],
        "actuator_observations": [0.1, 0.2],
        "target_takeoff_altitude_m": 2.0,
        "baseline_altitude_m": 2.5,
        "minimum_altitude_m": 1.5,
        "maximum_commanded_horizontal_speed_m_s": 0.5,
        "maximum_observed_horizontal_speed_m_s": 0.5,
        "maximum_commanded_vertical_speed_abs_m_s": 0.2,
        "maximum_observed_vertical_speed_abs_m_s": 0.5,
        "maximum_attitude_excursion_deg": 45.0,
        "maximum_body_rate_rad_s": 3.0,
        "unexpected_ground_contact": False,
        "px4_abort": False,
        "clock_stall": False,
        "critical_window_complete": True,
        "route_epoch_present": True,
        "writer_lineage_present": True,
        "controller_lineage_present": True,
        "land_completed": True,
        "disarm_completed": True,
        "runner_timed_out": False,
        "environment_failure": False,
        "campaign_configuration_failure": False,
    }


def _completed_evidence(slot_id: str = "V0P-S1") -> dict[str, object]:
    value = evidence.template(slot_id)
    value["template_only"] = False
    value["attempt_identity"]["formal_attempt_registered"] = True
    value["repository_identity"] = {
        "commit": "5db3934c58553e491b19fe8da106948fe8cd1d16",
        "worktree_clean": True,
    }
    value["raw_artifact_manifest_hashes"] = {"manifest.json": "a" * 64}
    value["critical_window_status"] = "COMPLETE"
    value["clock_status"] = "VALID"
    value["route_result"] = "PASS"
    value["evidence_gate_classification"] = "ACCEPTED"
    value["safety_result"] = "PASS"
    value["cleanup_result"] = "CLEAN"
    value["process_port_audit"] = "CLEAN"
    value["final_attempt_classification"] = "ACCEPTED"
    return value


def test_runner_plan_parses_fixed_six_slots() -> None:
    process = _run("plan")
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result["status"] == "STATIC_PLAN_PASS"
    assert result["slot_count"] == 6
    assert [item["attempt_id"] for item in result["slots"]] == [
        f"V0P-A{number}" for number in range(1, 7)
    ]
    assert result["comparison_arms_reachable"] is False
    assert result["runtime_started"] is False


def test_runner_preflight_is_static_and_starts_no_runtime() -> None:
    result = runner.preflight(require_clean=False)
    assert result["status"] == "STATIC_PREFLIGHT_PASS"
    assert result["runtime_started"] is False
    assert result["flight_communication_started"] is False
    assert result["formal_attempt_registered"] is False
    assert result["checks"]["process_port_audit"]["audit_status"] == "CLEAN"


def test_runner_without_subcommand_starts_nothing() -> None:
    process = _run()
    assert process.returncode != 0
    assert "execute" in process.stderr


def test_runner_execute_refuses_current_decline() -> None:
    process = _run(
        "execute",
        "--phase",
        "V0_P_QUALIFICATION",
        "--strategy",
        "QUALIFICATION",
        "--seed-id",
        "P0_A_OFFBOARD_ADMISSION",
        "--attempt-id",
        "V0P-A1",
        "--activation-commit",
        "5db3934c58553e491b19fe8da106948fe8cd1d16",
    )
    assert process.returncode == runner.EXIT_AUTHORITY_REFUSAL
    result = json.loads(process.stdout)
    assert result == {
        "formal_attempt_registered": False,
        "reason": "the original DECLINE decision cannot authorize execute",
        "runtime_started": False,
        "status": "EXECUTE_REFUSED",
    }


def _approved_decision_fixture() -> dict[str, object]:
    return {
        "decision": "APPROVE_QUALIFICATION",
        "status": "AUTHORIZED_NOT_STARTED",
        "qualification_authorized": True,
        "runtime_authorized": True,
        "comparison_runtime_authorized": False,
        "requires_independent_activation_rereview": False,
    }


def test_execute_requires_independent_activation_commit(monkeypatch) -> None:
    candidate = (
        ROOT
        / "experiments/fuzzer_v0/family_a/readiness_amendment/static_readiness_gate.json"
    )
    original_read = runner.read_json
    monkeypatch.setattr(
        runner,
        "read_json",
        lambda path: (
            original_read(path)
            if path.resolve() == ORIGINAL_DECISION.resolve()
            else _approved_decision_fixture()
        ),
    )
    with pytest.raises(ContractError, match="independent activation decision commit"):
        runner._validate_independent_authority(
            decision_path=candidate,
            ledger_path=QUALIFICATION_LEDGER,
            activation_commit="not-a-commit",
            attempt_id="V0P-A1",
            seed_id="P0_A_OFFBOARD_ADMISSION",
        )


def test_execute_refuses_ledger_not_authorized(monkeypatch) -> None:
    candidate = (
        ROOT
        / "experiments/fuzzer_v0/family_a/readiness_amendment/static_readiness_gate.json"
    )
    original_read = runner.read_json
    monkeypatch.setattr(
        runner,
        "read_json",
        lambda path: (
            original_read(path)
            if path.resolve() == ORIGINAL_DECISION.resolve()
            else _approved_decision_fixture()
        ),
    )
    monkeypatch.setattr(runner, "git_text", lambda *args: "a" * 40)
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, candidate.read_bytes(), b""
        ),
    )
    with pytest.raises(ContractError, match="ledger is not AUTHORIZED_NOT_STARTED"):
        runner._validate_independent_authority(
            decision_path=candidate,
            ledger_path=QUALIFICATION_LEDGER,
            activation_commit="a" * 40,
            attempt_id="V0P-A1",
            seed_id="P0_A_OFFBOARD_ADMISSION",
        )


@pytest.mark.parametrize(
    "strategy",
    [
        "OFFICIAL_SEQUENCE",
        "BOUNDED_RANDOM_TIMING_COMPARATOR",
        "STATE_AWARE_MUTATION",
    ],
)
def test_runner_refuses_every_comparison_strategy(strategy: str) -> None:
    process = _run("plan", "--strategy", strategy)
    assert process.returncode == runner.EXIT_SCOPE_REFUSAL
    result = json.loads(process.stdout)
    assert strategy in result["reason"]
    assert result["runtime_started"] is False


@pytest.mark.parametrize(
    ("phase", "seed"),
    [
        ("V0-H", "ISSUE162_HISTORICAL_REPLAY"),
        ("V0_P_QUALIFICATION", "ISSUE162_HISTORICAL_REPLAY"),
        ("V0_P_QUALIFICATION", "R1_SESSION_ROLLOVER"),
        ("V0_P_QUALIFICATION", "W1_AEROSTACK2_RUNTIME"),
        ("V0_P_QUALIFICATION", "B1_REGISTERED_CONTROLLER"),
        ("V0_P_QUALIFICATION", "ORACLE_MUTANT_INSTALL_DELAY"),
    ],
)
def test_runner_refuses_historical_and_out_of_scope_seeds(
    phase: str, seed: str
) -> None:
    process = _run("plan", "--phase", phase, "--seed-id", seed)
    assert process.returncode == runner.EXIT_SCOPE_REFUSAL
    assert json.loads(process.stdout)["runtime_started"] is False


def test_runner_refuses_unmapped_seed() -> None:
    process = _run("plan", "--seed-id", "P5_T1_OFFBOARD")
    assert process.returncode == runner.EXIT_SCOPE_REFUSAL
    assert "not in the qualification scenario map" in process.stdout


def test_runner_refuses_seventh_attempt() -> None:
    process = _run(
        "execute",
        "--phase",
        "V0_P_QUALIFICATION",
        "--strategy",
        "QUALIFICATION",
        "--seed-id",
        "P0_A_OFFBOARD_ADMISSION",
        "--attempt-id",
        "V0P-A7",
        "--activation-commit",
        "5db3934c58553e491b19fe8da106948fe8cd1d16",
    )
    assert process.returncode == runner.EXIT_AUTHORITY_REFUSAL
    assert "maximum is six" in process.stdout


def test_runner_requires_exact_phase_and_strategy() -> None:
    with pytest.raises(ContractError):
        enforce_scope(phase="V0-P", strategy="QUALIFICATION")
    with pytest.raises(ContractError):
        enforce_scope(phase="V0_P_QUALIFICATION", strategy="RANDOM")


def test_scenario_map_rows_are_accepted_current_seeds() -> None:
    rows = load_scenario_map()
    assert len(rows) == 6
    assert {row["source_campaign"] for row in rows} == {"P0", "P2", "P3", "C1"}
    assert all(row["maximum_slot_use"] == "1" for row in rows)
    assert all(row["integrity_status"] == "PASS" for row in rows)


def test_collector_and_oracle_bindings_exist_and_hash_match() -> None:
    assert validate_manifest() == {"components": 25, "bindings": 6}


def test_compact_evidence_rejects_missing_critical_field() -> None:
    value = _completed_evidence()
    del value["clock_status"]
    with pytest.raises(jsonschema.ValidationError):
        evidence.validate_evidence(value, require_complete=True)


def test_unknown_remains_unknown_and_cannot_be_accepted() -> None:
    value = _completed_evidence()
    value["route_result"] = "UNKNOWN"
    value["final_attempt_classification"] = "OBSERVABILITY_REJECTED"
    value["evidence_gate_classification"] = "OBSERVABILITY_REJECTED"
    evidence.validate_evidence(value, require_complete=True)
    assert value["route_result"] == "UNKNOWN"
    value["final_attempt_classification"] = "ACCEPTED"
    value["evidence_gate_classification"] = "ACCEPTED"
    with pytest.raises(evidence.EvidenceError):
        evidence.validate_evidence(value, require_complete=True)


def test_not_applicable_remains_not_applicable() -> None:
    value = _completed_evidence()
    assert value["freshness_result"] == "NOT_APPLICABLE"
    evidence.validate_evidence(value, require_complete=True)
    assert value["freshness_result"] == "NOT_APPLICABLE"


def test_exposure_remains_exposure_not_violation() -> None:
    value = _completed_evidence("V0P-S4")
    value["freshness_result"] = "EXPOSURE"
    evidence.validate_evidence(value, require_complete=True)
    assert value["freshness_result"] == "EXPOSURE"
    assert value["freshness_result"] != "VIOLATION"


def test_compact_template_does_not_fabricate_pass() -> None:
    value = evidence.template("V0P-S5")
    evidence.validate_evidence(value, require_complete=False)
    assert value["template_only"] is True
    assert value["route_result"] is None
    assert value["freshness_result"] is None
    assert value["final_attempt_classification"] is None


def test_cleanup_detects_residual_process_fixture() -> None:
    record = {
        "land_result_present": True,
        "disarm_result_present": True,
        "runner_exit_status": 0,
        "collectors_closed": True,
        "file_flush_complete": True,
        "expected_artifacts": ["route_trace.jsonl"],
        "closed_artifacts": ["route_trace.jsonl"],
    }
    result = cleanup.evaluate(
        record,
        residue_fixture={
            "processes": [
                {
                    "pid": 42,
                    "ppid": 1,
                    "executable": "px4",
                    "command": "px4 -i 0",
                }
            ]
        },
    )
    assert result["status"] == "RESIDUAL_PROCESS"
    assert result["accepted_classification_permitted"] is False


def test_cleanup_detects_occupied_port_fixture() -> None:
    record = {
        "land_result_present": True,
        "disarm_result_present": True,
        "runner_exit_status": 0,
        "collectors_closed": True,
        "file_flush_complete": True,
        "expected_artifacts": ["route_trace.jsonl"],
        "closed_artifacts": ["route_trace.jsonl"],
    }
    result = cleanup.evaluate(
        record,
        residue_fixture={"ports": [{"port": 8888, "protocol": "UDP"}]},
    )
    assert result["status"] == "OCCUPIED_PORT"
    assert result["accepted_classification_permitted"] is False


def test_residue_checker_has_deterministic_fixture_exit_codes() -> None:
    assert residue.evaluate("preflight", fixture={})["exit_code"] == 0
    assert (
        residue.evaluate(
            "preflight", fixture={"ports": [{"port": 8888, "protocol": "TCP"}]}
        )["exit_code"]
        == 11
    )


@pytest.mark.parametrize("field", safety.FINITE_FIELDS)
def test_safety_rejects_non_finite_values(field: str) -> None:
    fixture = _safety_pass_fixture()
    fixture[field] = [math.nan]
    result = safety.evaluate(fixture)
    assert result["status"] == "FORMAL_SAFETY_STOP"
    assert any("non_finite" in reason for reason in result["reasons"])


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("minimum_altitude_m", 1.49, "height_boundary_exceeded"),
        (
            "maximum_commanded_horizontal_speed_m_s",
            0.51,
            "commanded_horizontal_speed_boundary_exceeded",
        ),
        (
            "maximum_observed_horizontal_speed_m_s",
            0.51,
            "observed_horizontal_speed_boundary_exceeded",
        ),
        (
            "maximum_commanded_vertical_speed_abs_m_s",
            0.21,
            "commanded_vertical_speed_boundary_exceeded",
        ),
        (
            "maximum_observed_vertical_speed_abs_m_s",
            0.51,
            "observed_vertical_speed_boundary_exceeded",
        ),
        (
            "maximum_attitude_excursion_deg",
            45.01,
            "attitude_boundary_exceeded",
        ),
        ("maximum_body_rate_rad_s", 3.01, "body_rate_boundary_exceeded"),
    ],
)
def test_safety_enforces_frozen_physical_boundaries(
    field: str, value: float, reason: str
) -> None:
    fixture = _safety_pass_fixture()
    fixture[field] = value
    result = safety.evaluate(fixture)
    assert result["status"] == "FORMAL_SAFETY_STOP"
    assert reason in result["reasons"]
    assert result["W1_or_B1_envelope_used"] is False


def test_safety_missing_data_is_not_safe() -> None:
    fixture = _safety_pass_fixture()
    del fixture["route_epoch_present"]
    result = safety.evaluate(fixture)
    assert result["status"] == "MEASUREMENT_INSUFFICIENT"


def test_jazzy_environment_identity_is_statically_available() -> None:
    result = validate_environment()
    assert result["status"] == "STATICALLY_AVAILABLE"
    assert result["ros_distribution"] == "jazzy"
    assert result["runtime_started"] is False
    assert result["flight_communication_started"] is False


def test_attempt_ledgers_remain_zero() -> None:
    qualification = yaml.safe_load(QUALIFICATION_LEDGER.read_text(encoding="utf-8"))
    campaign = yaml.safe_load(FROZEN_LEDGER.read_text(encoding="utf-8"))
    assert qualification["status"] == "NOT_AUTHORIZED"
    assert qualification["formal_attempts"] == 0
    assert qualification["accepted_attempts"] == 0
    assert qualification["attempts"] == []
    assert campaign["formal_attempts"] == 0
    assert campaign["qualification_attempts"] == 0
    assert campaign["attempts"] == []


def test_original_activation_decision_remains_declined() -> None:
    decision = json.loads(ORIGINAL_DECISION.read_text(encoding="utf-8"))
    assert decision["decision"] == "DECLINE_IMPLEMENTATION_NOT_READY"
    assert decision["status"] == "QUALIFICATION_NOT_AUTHORIZED"
    assert decision["qualification_authorized"] is False
    assert decision["runtime_authorized"] is False
    assert decision["comparison_runtime_authorized"] is False
    assert decision["current_formal_attempts"] == 0


def test_comparison_budgets_remain_frozen() -> None:
    campaign = yaml.safe_load(
        (
            ROOT / "experiments/fuzzer_v0/family_a/campaign_matrix.yaml"
        ).read_text(encoding="utf-8")
    )
    assert campaign["budget_rules"]["total_future_formal_comparison_attempts"] == 36
    assert campaign["budget_rules"]["unused_budget_transfer_between_arms"] is False
    assert campaign["budget_rules"]["qualification_budget_is_not_comparison_budget"] is True
    assert {
        phase["strategy"]: phase["maximum_future_formal_attempts"]
        for phase in campaign["phases"]
        if "strategy" in phase
    } == {
        "OFFICIAL_SEQUENCE": 12,
        "BOUNDED_RANDOM_TIMING_COMPARATOR": 12,
        "STATE_AWARE_MUTATION": 12,
    }


def test_no_tracked_raw_files() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "runs"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert tracked == []


def test_runner_never_imports_pre_m_final_executor_or_route_oracle_0_3() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "scripts.fuzzer.executor" not in text
    assert "scripts/fuzzer/executor.py" not in text
    assert '"0.3"' not in text
    assert "Route Oracle 0.3" not in text
