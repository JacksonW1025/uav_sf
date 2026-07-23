from __future__ import annotations

import copy
import csv
import json
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
from scripts.fuzzer_v0.family_a.common import ContractError


ROOT = Path(__file__).resolve().parents[1]
REREVIEW = ROOT / "experiments/fuzzer_v0/family_a/activation_rereview"
AMENDMENT = ROOT / "experiments/fuzzer_v0/family_a/readiness_amendment"
ORIGINAL_DECISION = (
    ROOT
    / "experiments/fuzzer_v0/family_a/activation_review/"
    "qualification_activation_decision.json"
)
BLOCKERS = [
    "E-11",
    "E-12",
    "F-07",
    "F-08",
    "H-16",
    "J-12",
    "J-13",
    "J-14",
    "K-09",
]


def _yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


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
        "commit": "bae879484abab51e369af13ed46db5762f457242",
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


def _cleanup_pass_fixture() -> dict[str, object]:
    return {
        "land_result_present": True,
        "disarm_result_present": True,
        "runner_exit_status": 0,
        "collectors_closed": True,
        "file_flush_complete": True,
        "expected_artifacts": ["route", "clock", "evidence"],
        "closed_artifacts": ["route", "clock", "evidence"],
    }


def test_rereview_checker_passes() -> None:
    process = subprocess.run(
        [
            sys.executable,
            "scripts/validation/check_family_a_fuzzer_v0_activation_rereview.py",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr
    assert "blocking_clauses=9" in process.stdout
    assert "formal_attempts=0" in process.stdout


def test_decision_validates_and_declines_all_runtime() -> None:
    decision = json.loads(
        (REREVIEW / "qualification_activation_decision.json").read_text(
            encoding="utf-8"
        )
    )
    schema = json.loads(
        (
            ROOT
            / "data/schemas/family_a_fuzzer_v0_qualification_rereview.schema.json"
        ).read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(decision)
    assert decision["decision"] == "DECLINE_IMPLEMENTATION_NOT_READY"
    assert decision["blocking_clauses"] == BLOCKERS
    for field in (
        "qualification_runtime_authorized",
        "comparison_runtime_authorized",
        "official_sequence_authorized",
        "bounded_random_timing_authorized",
        "state_aware_authorized",
    ):
        assert decision[field] is False


def test_checklist_failures_are_exact_and_independent() -> None:
    with (REREVIEW / "independent_checklist.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    failures = [
        row["clause_id"]
        for row in rows
        if row["status"] == "FAIL" and row["blocking"] == "true"
    ]
    assert failures == BLOCKERS
    assert len(rows) == 124
    assert all(row["independent_validation"] for row in rows)


def test_test_manifest_has_no_runtime_result() -> None:
    manifest = _yaml(REREVIEW / "independent_test_manifest.yaml")
    tests = manifest["tests"]
    assert len(tests) == 31
    assert manifest["runtime_started"] is False
    assert all(item["runtime_started"] is False for item in tests)
    assert all(item["status"] == "PASS" for item in tests)


def test_six_slots_join_only_accepted_current_runtime_seeds() -> None:
    with (ROOT / "experiments/fuzzer_v0/family_a/seed_catalog.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        seeds = {
            row["seed_id"]: row for row in csv.DictReader(handle, delimiter="\t")
        }
    with (AMENDMENT / "qualification_scenario_map.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        slots = list(csv.DictReader(handle, delimiter="\t"))
    assert len(seeds) == 61
    assert len(slots) == 6
    for slot in slots:
        seed = seeds[slot["seed_id"]]
        assert seed["inclusion_status"] == "ACCEPTED_RUNTIME_SEED"
        assert seed["current_or_historical"] == "CURRENT"
        assert seed["runtime_or_replay"] == "RUNTIME"
        assert seed["source_campaign"] not in {
            "R1",
            "W1",
            "B1",
            "ORACLE_VALIDATION",
        }


def test_required_approval_contract_is_rejected_by_runner(tmp_path: Path) -> None:
    candidate = {
        "decision": "APPROVE_QUALIFICATION_ONLY",
        "status": "QUALIFICATION_AUTHORIZED_NOT_STARTED",
        "qualification_authorized": True,
        "runtime_authorized": True,
        "qualification_runtime_authorized": True,
        "comparison_runtime_authorized": False,
        "requires_independent_activation_rereview": False,
    }
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(json.dumps(candidate), encoding="utf-8")
    with pytest.raises(ContractError, match="later independent APPROVE"):
        runner._validate_independent_authority(
            decision_path=decision_path,
            ledger_path=REREVIEW / "qualification_attempt_ledger.yaml",
            activation_commit="bae879484abab51e369af13ed46db5762f457242",
            attempt_id="V0P-A1",
            seed_id="P0_A_OFFBOARD_ADMISSION",
        )


def test_runner_does_not_enforce_pushed_ledger_identity() -> None:
    source = (
        ROOT / "scripts/fuzzer_v0/family_a/run_v0p_qualification.py"
    ).read_text(encoding="utf-8")
    assert "origin/main" not in source
    assert "ledger_path.resolve().relative_to" not in source
    assert "authorization_decision_commit" not in source


def test_manifest_declarations_are_not_complete_scenario_invocations() -> None:
    p0 = (ROOT / "scripts/probes/run_p0_scenario.sh").read_text(encoding="utf-8")
    route = (
        ROOT / "scripts/probes/run_route_experiment.sh"
    ).read_text(encoding="utf-8")
    c1 = (
        ROOT / "scripts/probes/run_c1_concurrency.sh"
    ).read_text(encoding="utf-8")
    assert "successor_progression_oracle.py" not in p0
    assert "pre_revocation_freshness_oracle.py" not in route
    assert "route_oracle_v0.py" not in c1
    assert "successor_progression_oracle.py" not in c1


def test_scenarios_do_not_produce_runner_evidence_inputs() -> None:
    scenarios = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "scripts/probes/run_p0_scenario.sh",
            "scripts/probes/run_route_experiment.sh",
            "scripts/probes/run_c1_concurrency.sh",
        )
    )
    runner_source = (
        ROOT / "scripts/fuzzer_v0/family_a/run_v0p_qualification.py"
    ).read_text(encoding="utf-8")
    for name in (
        "safety_evidence.json",
        "cleanup_evidence.json",
        "compact_evidence.json",
    ):
        assert name in runner_source
        assert name not in scenarios


def test_safety_is_post_scenario_and_ledger_has_no_write_path() -> None:
    source = (
        ROOT / "scripts/fuzzer_v0/family_a/run_v0p_qualification.py"
    ).read_text(encoding="utf-8")
    assert source.index("process = subprocess.run(command") < source.index(
        '"scripts/fuzzer_v0/family_a/check_v0p_safety.py"'
    )
    for token in (
        "yaml.safe_dump",
        "attempts.append",
        "write_text(",
        "formal_attempts +=",
    ):
        assert token not in source


def test_environment_lacks_complete_image_and_active_checks() -> None:
    lock = _yaml(AMENDMENT / "environment_lock.yaml")
    dockerfile = (ROOT / "docker/Dockerfile").read_text(encoding="utf-8")
    checker = (
        ROOT / "scripts/setup/verify_family_a_v0p_environment.py"
    ).read_text(encoding="utf-8")
    assert "qualification_image_digest" not in lock
    assert "apt-get install" in dockerfile
    assert "packages.ros.org" in dockerfile
    assert "ros2 --help" not in checker
    assert "importlib" not in checker


def test_c1_defaults_are_not_jazzy_manifest_bound() -> None:
    source = (
        ROOT / "scripts/probes/run_c1_concurrency.sh"
    ).read_text(encoding="utf-8")
    runner_source = (
        ROOT / "scripts/fuzzer_v0/family_a/run_v0p_qualification.py"
    ).read_text(encoding="utf-8")
    assert "runs/freshness_agent_build" in source
    assert "runs/c1_harness_build" in source
    assert '"MICROXRCE_AGENT_BIN"' not in runner_source
    assert '"C1_MODE_BIN"' not in runner_source


def test_complete_compact_evidence_fixture_passes() -> None:
    evidence.validate_evidence(_completed_evidence(), require_complete=True)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (("repository_identity", "commit", None), "repository_identity.commit"),
        (("raw_artifact_manifest_hashes", None, {}), "raw artifact manifest"),
        (("critical_window_status", None, None), "critical_window_status"),
    ],
)
def test_compact_evidence_rejects_missing_required_evidence(
    mutation: tuple[str, str | None, object], message: str
) -> None:
    value = _completed_evidence()
    field, child, replacement = mutation
    if child is None:
        value[field] = replacement
    else:
        value[field][child] = replacement
    with pytest.raises(evidence.EvidenceError, match=message):
        evidence.validate_evidence(value, require_complete=True)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("clock_status", "INVALID", "clock"),
        ("route_result", "UNKNOWN", "UNKNOWN"),
        ("route_result", "NOT_APPLICABLE", "cannot be NOT_APPLICABLE"),
        ("cleanup_result", "RESIDUAL_PROCESS", "cleanup"),
        ("safety_result", "FORMAL_SAFETY_STOP", "safety"),
    ],
)
def test_compact_evidence_rejects_invalid_accepted_semantics(
    field: str, replacement: str, message: str
) -> None:
    value = _completed_evidence()
    value[field] = replacement
    with pytest.raises(evidence.EvidenceError, match=message):
        evidence.validate_evidence(value, require_complete=True)


def test_exposure_remains_exposure() -> None:
    value = _completed_evidence()
    value["route_result"] = "EXPOSURE"
    evidence.validate_evidence(value, require_complete=True)
    assert value["route_result"] == "EXPOSURE"


def test_safety_pass_fixture_uses_frozen_family_a_bounds() -> None:
    result = safety.evaluate(_safety_pass_fixture())
    assert result["status"] == "PASS"
    assert result["W1_or_B1_envelope_used"] is False
    assert result["bounds_source"].endswith("family_a/safety_rules.yaml")


@pytest.mark.parametrize(
    ("field", "replacement", "expected"),
    [
        ("command_values", [float("nan")], "FORMAL_SAFETY_STOP"),
        ("observed_controller_values", [float("inf")], "FORMAL_SAFETY_STOP"),
        ("actuator_observations", [], "FORMAL_SAFETY_STOP"),
        ("minimum_altitude_m", 1.4, "FORMAL_SAFETY_STOP"),
        ("maximum_observed_horizontal_speed_m_s", 0.6, "FORMAL_SAFETY_STOP"),
        ("maximum_observed_vertical_speed_abs_m_s", 0.6, "FORMAL_SAFETY_STOP"),
        ("maximum_attitude_excursion_deg", 45.1, "FORMAL_SAFETY_STOP"),
        ("maximum_body_rate_rad_s", 3.1, "FORMAL_SAFETY_STOP"),
        ("unexpected_ground_contact", True, "FORMAL_SAFETY_STOP"),
        ("px4_abort", True, "FORMAL_SAFETY_STOP"),
        ("clock_stall", True, "FORMAL_SAFETY_STOP"),
        ("runner_timed_out", True, "FORMAL_SAFETY_STOP"),
        ("critical_window_complete", False, "MEASUREMENT_INSUFFICIENT"),
        ("route_epoch_present", False, "MEASUREMENT_INSUFFICIENT"),
        ("writer_lineage_present", False, "MEASUREMENT_INSUFFICIENT"),
        ("controller_lineage_present", False, "MEASUREMENT_INSUFFICIENT"),
        ("land_completed", False, "MEASUREMENT_INSUFFICIENT"),
        ("disarm_completed", False, "MEASUREMENT_INSUFFICIENT"),
    ],
)
def test_safety_negative_fixtures(
    field: str, replacement: object, expected: str
) -> None:
    value = _safety_pass_fixture()
    value[field] = replacement
    assert safety.evaluate(value)["status"] == expected


def test_cleanup_clean_fixture_terminates_nothing() -> None:
    result = cleanup.evaluate(
        _cleanup_pass_fixture(),
        residue_fixture={
            "processes": [],
            "ports": [],
            "stale_state": [],
            "incomplete_run_directory": [],
        },
    )
    assert result["status"] == "CLEAN"
    assert result["terminated_processes"] == []


@pytest.mark.parametrize(
    "marker",
    ["px4", "gz sim", "ros2 launch", "MicroXRCEAgent", "route_trace_collector.py"],
)
def test_cleanup_detects_every_residual_process_class(marker: str) -> None:
    result = cleanup.evaluate(
        _cleanup_pass_fixture(),
        residue_fixture={
            "processes": [{"pid": 10, "command": marker}],
            "ports": [],
            "stale_state": [],
            "incomplete_run_directory": [],
        },
    )
    assert result["status"] == "RESIDUAL_PROCESS"
    assert result["terminated_processes"] == []


@pytest.mark.parametrize("protocol", ["UDP", "TCP"])
def test_cleanup_detects_occupied_8888(protocol: str) -> None:
    result = cleanup.evaluate(
        _cleanup_pass_fixture(),
        residue_fixture={
            "processes": [],
            "ports": [{"port": 8888, "protocol": protocol}],
            "stale_state": [],
            "incomplete_run_directory": [],
        },
    )
    assert result["status"] == "OCCUPIED_PORT"


def test_cleanup_detects_stale_and_incomplete_state() -> None:
    stale = residue.evaluate(
        "post-attempt",
        fixture={
            "processes": [],
            "ports": [],
            "stale_state": ["runner.pid", "attempt.lock"],
            "incomplete_run_directory": [],
        },
    )
    incomplete = residue.evaluate(
        "post-attempt",
        fixture={
            "processes": [],
            "ports": [],
            "stale_state": [],
            "incomplete_run_directory": ["evidence.partial"],
        },
    )
    assert stale["status"] == "STALE_STATE"
    assert incomplete["status"] == "INCOMPLETE_RUN_DIRECTORY"
    assert stale["terminated_processes"] == []
    assert incomplete["terminated_processes"] == []


def test_cleanup_detects_artifact_and_terminal_failures() -> None:
    artifact = _cleanup_pass_fixture()
    artifact["closed_artifacts"] = ["route"]
    terminal = _cleanup_pass_fixture()
    terminal["disarm_result_present"] = False
    clean_residue = {
        "processes": [],
        "ports": [],
        "stale_state": [],
        "incomplete_run_directory": [],
    }
    assert (
        cleanup.evaluate(artifact, residue_fixture=clean_residue)["status"]
        == "INCOMPLETE_ARTIFACT_CLOSE"
    )
    assert (
        cleanup.evaluate(terminal, residue_fixture=clean_residue)["status"]
        == "MISSING_TERMINAL_STATE"
    )
