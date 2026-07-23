#!/usr/bin/env python3
"""Validate the independent Family A Fuzzer v0 activation re-review."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterator

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]
FAMILY_BASE = ROOT / "experiments/fuzzer_v0/family_a"
REREVIEW_BASE = FAMILY_BASE / "activation_rereview"
AMENDMENT_BASE = FAMILY_BASE / "readiness_amendment"
DECISION_PATH = REREVIEW_BASE / "qualification_activation_decision.json"
SCHEMA_PATH = (
    ROOT
    / "data/schemas/family_a_fuzzer_v0_qualification_rereview.schema.json"
)
STARTING_HEAD = "bae879484abab51e369af13ed46db5762f457242"
PREREGISTRATION_COMMIT = "426f4c7316e973c6a4dab84a202fdb75ea65b7c1"
ORIGINAL_REVIEW_COMMIT = "5db3934c58553e491b19fe8da106948fe8cd1d16"
READINESS_IMPLEMENTATION_COMMIT = "e6128fdf5028c91673392d42f9736cbd5ac5b562"
BLOCKING_CLAUSES = [
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
NEXT_ACTION = (
    "create an independent blocker-resolution amendment for the new review findings"
)
CHECKLIST_FIELDS = [
    "clause_id",
    "category",
    "requirement",
    "frozen_source",
    "implementation_evidence",
    "independent_validation",
    "observed_value",
    "expected_value",
    "status",
    "blocking",
    "notes",
]


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def _tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    return fields, rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str, check: bool = True) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _identity_records(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            yield value
        for item in value.values():
            yield from _identity_records(item)
    elif isinstance(value, list):
        for item in value:
            yield from _identity_records(item)


def _assert_ancestor(commit: str) -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=ROOT,
        check=True,
    )


def _assert_zero_ledger(value: dict[str, Any]) -> None:
    assert value["formal_attempts"] == 0
    if "accepted_attempts" in value:
        assert value["accepted_attempts"] == 0
    assert value["attempts"] == []


def validate() -> dict[str, Any]:
    required = {
        "README.md",
        "independent_checklist.tsv",
        "independent_test_manifest.yaml",
        "qualification_activation_decision.json",
        "qualification_attempt_ledger.yaml",
        "qualification_execution_authorization.yaml",
        "qualification_runbook_review.md",
        "rereview_source_lock.yaml",
    }
    assert required == {
        path.name for path in REREVIEW_BASE.iterdir() if path.is_file()
    }

    decision = _json(DECISION_PATH)
    schema = _json(SCHEMA_PATH)
    jsonschema.Draft202012Validator(schema).validate(decision)
    source_lock = _yaml(REREVIEW_BASE / "rereview_source_lock.yaml")
    authorization = _yaml(
        REREVIEW_BASE / "qualification_execution_authorization.yaml"
    )
    ledger = _yaml(REREVIEW_BASE / "qualification_attempt_ledger.yaml")

    assert source_lock["starting_head"] == source_lock["starting_origin_main"]
    assert source_lock["starting_head"] == STARTING_HEAD
    assert source_lock["starting_ahead"] == source_lock["starting_behind"] == 0
    assert source_lock["preregistration_commit"] == PREREGISTRATION_COMMIT
    assert (
        source_lock["original_activation_review_commit"] == ORIGINAL_REVIEW_COMMIT
    )
    assert (
        source_lock["readiness_implementation_commit"]
        == READINESS_IMPLEMENTATION_COMMIT
    )
    assert source_lock["readiness_identity_lock_commit"] == STARTING_HEAD
    for commit in source_lock["required_ancestor_commits"]:
        assert re.fullmatch(r"[0-9a-f]{40}", commit)
        _assert_ancestor(commit)

    for section in ("frozen_bundle", "readiness_inputs"):
        for item in source_lock[section]:
            path = ROOT / item["path"]
            assert path.is_file(), item["path"]
            assert _sha256(path) == item["sha256"], item["path"]
    assert (
        _sha256(AMENDMENT_BASE / "implementation_manifest.yaml")
        == source_lock["implementation_manifest_sha256"]
    )
    assert (
        _sha256(AMENDMENT_BASE / "environment_lock.yaml")
        == source_lock["environment_lock_sha256"]
    )
    assert (
        _sha256(AMENDMENT_BASE / "qualification_scenario_map.tsv")
        == source_lock["scenario_map_sha256"]
    )

    original_decision = _json(
        FAMILY_BASE / "activation_review/qualification_activation_decision.json"
    )
    amendment = _yaml(AMENDMENT_BASE / "amendment.yaml")
    amendment_gate = _json(AMENDMENT_BASE / "static_readiness_gate.json")
    assert original_decision["decision"] == "DECLINE_IMPLEMENTATION_NOT_READY"
    assert original_decision["status"] == "QUALIFICATION_NOT_AUTHORIZED"
    assert original_decision["blocking_clause_count"] == 11
    assert amendment["status"] == "READINESS_RESOLVED_PENDING_INDEPENDENT_REVIEW"
    assert amendment["resolution"] == {
        "original_blocking_clauses": 11,
        "resolved_clauses": 11,
        "remaining_clauses": 0,
        "environment_proof": "LOCKED_REPRODUCIBLE_CONTAINER_STATICALLY_AVAILABLE",
    }
    assert amendment_gate["qualification_authorized"] is False
    assert amendment_gate["runtime_authorized"] is False
    assert amendment_gate["comparison_runtime_authorized"] is False

    checklist_fields, checklist = _tsv(
        REREVIEW_BASE / "independent_checklist.tsv"
    )
    assert checklist_fields == CHECKLIST_FIELDS
    assert len(checklist) >= 100
    assert len({row["clause_id"] for row in checklist}) == len(checklist)
    assert all(
        row["status"] in {"PASS", "FAIL", "NOT_APPLICABLE"}
        for row in checklist
    )
    assert all(row["blocking"] in {"true", "false"} for row in checklist)
    blockers = [
        row["clause_id"]
        for row in checklist
        if row["status"] == "FAIL" and row["blocking"] == "true"
    ]
    assert blockers == BLOCKING_CLAUSES
    assert not [
        row
        for row in checklist
        if row["status"] == "FAIL" and row["blocking"] == "false"
    ]

    test_manifest = _yaml(REREVIEW_BASE / "independent_test_manifest.yaml")
    tests = test_manifest["tests"]
    assert len(tests) >= 25
    assert len({item["test_id"] for item in tests}) == len(tests)
    test_fields = {
        "test_id",
        "reviewed_clause",
        "command_or_fixture",
        "source_under_review",
        "expected_result",
        "observed_result",
        "exit_code",
        "runtime_started",
        "artifact_hash",
        "status",
    }
    assert all(set(item) == test_fields for item in tests)
    assert all(item["runtime_started"] is False for item in tests)
    assert all(item["status"] == "PASS" for item in tests)
    assert test_manifest["runtime_started"] is False

    seed_fields, seeds = _tsv(FAMILY_BASE / "seed_catalog.tsv")
    assert seed_fields
    assert len(seeds) == len({row["seed_id"] for row in seeds}) == 61
    runtime_seeds = [
        row
        for row in seeds
        if row["inclusion_status"] == "ACCEPTED_RUNTIME_SEED"
        and row["current_or_historical"] == "CURRENT"
        and row["runtime_or_replay"] == "RUNTIME"
    ]
    historical = [
        row
        for row in seeds
        if row["inclusion_status"] == "ACCEPTED_REPLAY_BENCHMARK"
    ]
    excluded = [
        row for row in seeds if row["inclusion_status"] == "EXCLUDED"
    ]
    assert len(runtime_seeds) == 50
    assert len(historical) == 1
    assert len(excluded) == 10
    assert len(runtime_seeds) + len(historical) + len(excluded) == 61

    map_fields, scenario_rows = _tsv(
        AMENDMENT_BASE / "qualification_scenario_map.tsv"
    )
    assert map_fields
    assert len(scenario_rows) == 6
    assert [row["slot_id"] for row in scenario_rows] == [
        f"V0P-S{number}" for number in range(1, 7)
    ]
    assert [row["attempt_id"] for row in scenario_rows] == [
        f"V0P-A{number}" for number in range(1, 7)
    ]
    seed_by_id = {row["seed_id"]: row for row in seeds}
    joined_fields = (
        "source_campaign",
        "source_artifact",
        "mechanism",
        "source_route",
        "target_or_retained_route",
        "setpoint_level",
    )
    for row in scenario_rows:
        seed = seed_by_id[row["seed_id"]]
        assert seed in runtime_seeds
        assert all(row[field] == seed[field] for field in joined_fields)
        assert row["expected_lifecycle_sequence"] == seed["lifecycle_sequence"]
        assert seed["source_campaign"] not in {
            "R1",
            "W1",
            "B1",
            "ORACLE_VALIDATION",
        }
        assert seed["setpoint_level"] != "DIRECT_ACTUATOR"

    manifest = _yaml(AMENDMENT_BASE / "implementation_manifest.yaml")
    components = manifest["components"]
    bindings = manifest["orchestration_bindings"]
    assert len(components) == 25
    assert len(bindings) == 6
    component_paths = {item["path"] for item in components}
    for component in components:
        path = ROOT / component["path"]
        assert path.is_file()
        assert _sha256(path) == component["sha256"]
    required_binding_fields = (
        "scenario_entry",
        "adapter_entries",
        "collector_bundle",
        "oracle_bundle",
        "evidence_profile",
        "safety_profile",
        "cleanup_profile",
    )
    for row, binding in zip(scenario_rows, bindings, strict=True):
        assert row["slot_id"] == binding["slot_id"]
        assert row["runner_adapter"] == binding["runner_adapter"]
        for field in required_binding_fields:
            value = binding[field]
            values = value if isinstance(value, list) else [value]
            assert values
            assert all(item in component_paths for item in values)
        oracle_names = set(row["expected_oracles"].split("|"))
        oracle_paths = set(binding["oracle_bundle"])
        expected_paths = {
            "ROUTE": "scripts/oracles/route_oracle_v0.py",
            "FRESHNESS": "scripts/oracles/pre_revocation_freshness_oracle.py",
            "SUCCESSOR": "scripts/oracles/successor_progression_oracle.py",
            "LINEARIZATION": (
                "scripts/oracles/authority_event_linearization_oracle.py"
            ),
        }
        assert {expected_paths[name] for name in oracle_names} <= oracle_paths

    oracle_lock = _yaml(FAMILY_BASE / "oracle_lock.yaml")
    oracle_identities = list(_identity_records(oracle_lock))
    assert len(oracle_identities) == 22
    for item in oracle_identities:
        path = ROOT / item["path"]
        assert path.is_file(), item["path"]
        assert _sha256(path) == item["sha256"], item["path"]
    assert oracle_lock["route_oracle"]["version"] == "0.4"
    assert (
        oracle_lock["route_oracle"]["transition_profile"]["profile_id"]
        == "route-oracle-v0.3-default"
    )
    assert (
        oracle_lock["identity_consistency"]["old_Route_Oracle_0_3_identity_used"]
        is False
    )

    runner_path = ROOT / "scripts/fuzzer_v0/family_a/run_v0p_qualification.py"
    runner = runner_path.read_text(encoding="utf-8")
    common = (
        ROOT / "scripts/fuzzer_v0/family_a/common.py"
    ).read_text(encoding="utf-8")
    assert runner.count("run_v0p_qualification.py") == 0
    assert len(list((ROOT / "scripts").rglob("run_v0p_qualification.py"))) == 1
    assert "scripts.fuzzer.executor" not in runner
    assert "scripts/fuzzer/executor.py" not in runner
    assert '"0.3"' not in runner

    # E-11: the required re-review approval contract cannot pass this runner.
    assert 'decision.get("decision") != "APPROVE_QUALIFICATION"' in runner
    assert 'decision.get("status") != "AUTHORIZED_NOT_STARTED"' in runner
    assert "APPROVE_QUALIFICATION_ONLY" not in runner
    assert "QUALIFICATION_AUTHORIZED_NOT_STARTED" not in runner
    assert (
        "sha256(decision_path)"
        in runner
        and "hashlib.sha256(decision_blob.stdout).hexdigest()" in runner
    )

    # E-12: no exact pushed-main or ledger-commit identity is enforced.
    assert "origin/main" not in runner
    assert "merge-base" not in runner
    assert "ledger_path.resolve().relative_to" not in runner
    assert "authorization_decision_commit" not in runner

    p0 = (ROOT / "scripts/probes/run_p0_scenario.sh").read_text(encoding="utf-8")
    route = (
        ROOT / "scripts/probes/run_route_experiment.sh"
    ).read_text(encoding="utf-8")
    c1 = (
        ROOT / "scripts/probes/run_c1_concurrency.sh"
    ).read_text(encoding="utf-8")
    assert "route_oracle_v0.py" in p0
    assert "successor_progression_oracle.py" not in p0
    assert "route_oracle_v0.py" in route
    assert "pre_revocation_freshness_oracle.py" not in route
    assert "authority_event_linearization_oracle.py" in c1
    assert "route_oracle_v0.py" not in c1
    assert "successor_progression_oracle.py" not in c1

    scenario_sources = "\n".join((p0, route, c1))
    for required_input in (
        "safety_evidence.json",
        "cleanup_evidence.json",
        "compact_evidence.json",
    ):
        assert required_input in runner
        assert required_input not in scenario_sources

    scenario_launch = runner.index("process = subprocess.run(command")
    safety_post_path = runner.index(
        '"scripts/fuzzer_v0/family_a/check_v0p_safety.py"'
    )
    assert scenario_launch < safety_post_path
    assert "check_v0p_safety.py" not in runner[:scenario_launch]

    for ledger_write_token in (
        "yaml.safe_dump",
        "attempts.append",
        "write_text(",
        "formal_attempts +=",
        "accepted_attempts +=",
    ):
        assert ledger_write_token not in runner
    assert common.count("QUALIFICATION_LEDGER_PATH") >= 1

    environment = _yaml(AMENDMENT_BASE / "environment_lock.yaml")
    dockerfile = (ROOT / "docker/Dockerfile").read_text(encoding="utf-8")
    environment_checker = (
        ROOT / "scripts/setup/verify_family_a_v0p_environment.py"
    ).read_text(encoding="utf-8")
    assert environment["environment_kind"] == "LOCKED_REPRODUCIBLE_CONTAINER"
    assert environment["ros_distribution"] == "jazzy"
    assert environment["architecture"] == "aarch64"
    assert re.fullmatch(
        r"sha256:[0-9a-f]{64}", environment["base_image_digest"]
    )
    assert "qualification_image_digest" not in environment
    assert "apt-get install" in dockerfile
    assert "python3 -m pip install" in dockerfile
    assert "packages.ros.org" in dockerfile
    assert "raw.githubusercontent.com/ros/rosdistro/master/ros.key" in dockerfile
    assert "ros2 --help" not in environment_checker
    assert "importlib" not in environment_checker
    assert "docker manifest" not in environment_checker

    assert 'C1_AGENT_BUILD:-${REPO_ROOT}/runs/freshness_agent_build' in c1
    assert (
        'C1_MODE_BIN:-${REPO_ROOT}/runs/c1_harness_build/install/'
        "route_transition_external_mode/lib/route_transition_external_mode/"
        "c1_concurrency_probe"
    ) in c1
    assert '"MICROXRCE_AGENT_BIN"' not in runner
    assert '"C1_AGENT_BUILD"' not in runner
    assert '"C1_MODE_BIN"' not in runner
    assert '"PX4_OBSERVABILITY_DIR"' not in runner

    environment_observation = source_lock["independent_environment_observation"]
    assert environment_observation["base_image_digest_resolved"] is True
    assert environment_observation["arm64_manifest_present"] is True
    assert (
        environment_observation["complete_qualification_image_digest_locked"]
        is False
    )
    assert environment_observation["selected_jazzy_environment_executed"] is False
    assert environment_observation["selected_jazzy_imports_confirmed"] is False
    assert environment_observation["host_ros_distribution"] == "humble"
    assert environment_observation["environment_status"] == "BLOCKING_FAIL"

    assert decision["decision"] == "DECLINE_IMPLEMENTATION_NOT_READY"
    assert decision["status"] == "QUALIFICATION_NOT_AUTHORIZED"
    assert decision["authorized_scope"] == "NONE"
    assert decision["blocking_clauses"] == BLOCKING_CLAUSES
    assert decision["blocking_clause_count"] == len(BLOCKING_CLAUSES)
    assert decision["non_blocking_finding_count"] == len(
        decision["non_blocking_findings"]
    )
    assert decision["non_blocking_finding_count"] == 4
    authorization_fields = (
        "qualification_authorized",
        "runtime_authorized",
        "qualification_runtime_authorized",
        "comparison_runtime_authorized",
        "official_sequence_authorized",
        "bounded_random_timing_authorized",
        "state_aware_authorized",
        "historical_replay_runtime_authorized",
        "real_workload_authorized",
        "family_b_authorized",
        "direct_actuator_authorized",
        "hitl_authorized",
        "real_flight_authorized",
    )
    assert all(decision[field] is False for field in authorization_fields)
    assert decision["qualification_target_accepted"] == 3
    assert decision["qualification_maximum_formal_attempts"] == 6
    assert decision["current_formal_attempts"] == 0
    assert decision["current_accepted_attempts"] == 0
    assert decision["formal_attempts"] == 0
    assert decision["next_attempt_id"] == "V0P-A1"
    assert decision["execution_not_started"] is True
    assert decision["runtime_executed_during_review"] is False
    assert decision["next_exact_action"] == NEXT_ACTION

    assert authorization["authorization_status"] == "NOT_AUTHORIZED"
    assert authorization["authorized_phase"] == "NONE"
    assert authorization["allowed_slots"] == []
    assert authorization["allowed_strategy"] is None
    assert authorization["comparison_strategies_authorized"] is False
    assert authorization["blockers"] == BLOCKING_CLAUSES
    assert authorization["formal_attempts"] == 0
    assert authorization["accepted_attempts"] == 0
    assert authorization["execution_requires_separate_task"] is True

    assert ledger["status"] == "NOT_AUTHORIZED"
    assert ledger["activation_decision"] == "DECLINE_IMPLEMENTATION_NOT_READY"
    assert ledger["qualification_target_accepted"] == 3
    assert ledger["qualification_maximum_formal_attempts"] == 6
    assert ledger["next_attempt_id"] == "V0P-A1"
    _assert_zero_ledger(ledger)
    _assert_zero_ledger(_yaml(FAMILY_BASE / "attempt_ledger.yaml"))
    _assert_zero_ledger(
        _yaml(FAMILY_BASE / "activation_review/qualification_attempt_ledger.yaml")
    )

    runtime_observation = source_lock["runtime_observation"]
    assert all(
        value is False
        for key, value in runtime_observation.items()
        if key.endswith("_started")
    )
    assert runtime_observation["ULog_created"] is False
    assert runtime_observation["rosbag_created"] is False
    assert runtime_observation["qualification_attempts_created"] == 0
    assert runtime_observation["comparison_attempts_created"] == 0

    tracked_runs = _git("ls-files", "runs").splitlines()
    assert tracked_runs == []
    checked_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (
            list(REREVIEW_BASE.iterdir())
            + [
                ROOT / "docs/design/FAMILY_A_FUZZER_V0_ACTIVATION_REREVIEW.md",
                SCHEMA_PATH,
            ]
        )
        if path.is_file()
    )
    assert "/home/" not in checked_text
    assert "/mnt/" not in checked_text
    credential = re.compile(
        r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|"
        r"-----BEGIN [^-]*PRIVATE KEY-----"
    )
    assert credential.search(checked_text) is None

    return {
        "decision": decision["decision"],
        "blocking_clauses": len(blockers),
        "non_blocking_findings": decision["non_blocking_finding_count"],
        "checklist_clauses": len(checklist),
        "independent_tests": len(tests),
        "seed_records": len(seeds),
        "runtime_seeds": len(runtime_seeds),
        "historical_replay_seeds": len(historical),
        "excluded_seeds": len(excluded),
        "scenario_slots": len(scenario_rows),
        "oracle_identity_records": len(oracle_identities),
        "formal_attempts": ledger["formal_attempts"],
        "accepted_attempts": ledger["accepted_attempts"],
        "tracked_raw_files": len(tracked_runs),
    }


def main() -> None:
    result = validate()
    print("Family A Fuzzer v0 activation re-review consistency check passed")
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
