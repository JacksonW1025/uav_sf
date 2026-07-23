#!/usr/bin/env python3
"""Validate the independent Family A V0-P qualification readiness amendment."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.fuzzer_v0.family_a.common import (
    ContractError,
    load_scenario_map,
    original_authority_state,
    read_json,
    read_yaml,
    sha256,
    validate_manifest,
)
from scripts.fuzzer_v0.family_a.run_v0p_qualification import (
    EXIT_AUTHORITY_REFUSAL,
    build_plan,
    preflight,
)
from scripts.setup.verify_family_a_v0p_environment import validate as environment


FAMILY_BASE = ROOT / "experiments/fuzzer_v0/family_a"
AMENDMENT_BASE = FAMILY_BASE / "readiness_amendment"
GATE_PATH = AMENDMENT_BASE / "static_readiness_gate.json"
SCHEMA_PATH = ROOT / "data/schemas/family_a_fuzzer_v0_readiness_gate.schema.json"
STARTING_COMMIT = "5db3934c58553e491b19fe8da106948fe8cd1d16"
IMPLEMENTATION_SENTINEL = "IMPLEMENTATION_COMMIT_RECORDED_BY_IDENTITY_LOCK"
MANIFEST_SENTINEL = "IMPLEMENTATION_MANIFEST_SHA256_RECORDED_BY_IDENTITY_LOCK"
IDENTITY_SENTINEL = "COMMIT_CONTAINING_THIS_IDENTITY_LOCK_REPORTED_BY_GIT_AFTER_PUSH"
BLOCKERS = [
    "G-01",
    "G-02",
    "G-05",
    "G-07",
    "G-08",
    "G-10",
    "H-01",
    "H-02",
    "H-07",
    "H-08",
    "J-03",
]
NEXT_ACTION = "perform a new independent static qualification activation review"


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_blob(commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate() -> dict[str, Any]:
    required = {
        "README.md",
        "amendment.yaml",
        "amendment_source_lock.yaml",
        "blocker_resolution_matrix.tsv",
        "environment_lock.yaml",
        "implementation_manifest.yaml",
        "qualification_scenario_map.tsv",
        "readiness_validation_report.md",
        "static_readiness_gate.json",
    }
    assert required == {
        path.name for path in AMENDMENT_BASE.iterdir() if path.is_file()
    }

    amendment = read_yaml(AMENDMENT_BASE / "amendment.yaml")
    source_lock = read_yaml(AMENDMENT_BASE / "amendment_source_lock.yaml")
    gate = read_json(GATE_PATH)
    schema = read_json(SCHEMA_PATH)
    jsonschema.Draft202012Validator(schema).validate(gate)

    assert source_lock["starting_head"] == source_lock["starting_origin_main"]
    assert source_lock["starting_head"] == STARTING_COMMIT
    assert source_lock["starting_ahead"] == source_lock["starting_behind"] == 0
    assert source_lock["original_activation_review_commit"] == STARTING_COMMIT
    assert gate["starting_commit"] == gate["review_commit"] == STARTING_COMMIT
    assert amendment["starting_commit"] == STARTING_COMMIT
    assert amendment["original_activation_review_commit"] == STARTING_COMMIT
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", STARTING_COMMIT, "HEAD"],
        cwd=ROOT,
        check=True,
    )

    review_lock = read_yaml(FAMILY_BASE / "activation_review/review_source_lock.yaml")
    for item in review_lock["frozen_bundle"]:
        path = ROOT / item["path"]
        assert path.is_file()
        assert sha256(path) == item["sha256"], item["path"]
    for item in source_lock["original_review_inputs"]:
        path = ROOT / item["path"]
        assert path.is_file()
        assert sha256(path) == item["sha256"], item["path"]
    for item in source_lock["amendment_contract_inputs"].values():
        path = ROOT / item["path"]
        assert path.is_file()
        assert sha256(path) == item["sha256"], item["path"]

    decision = read_json(
        FAMILY_BASE / "activation_review/qualification_activation_decision.json"
    )
    checklist = _csv(
        FAMILY_BASE / "activation_review/activation_review_checklist.tsv"
    )
    original_blockers = [
        row["clause_id"]
        for row in checklist
        if row["status"] == "FAIL" and row["blocking"] == "true"
    ]
    assert original_blockers == BLOCKERS
    assert decision["blocking_clauses"] == BLOCKERS
    assert decision["decision"] == "DECLINE_IMPLEMENTATION_NOT_READY"
    assert decision["status"] == "QUALIFICATION_NOT_AUTHORIZED"
    assert decision["qualification_authorized"] is False
    assert decision["runtime_authorized"] is False
    assert decision["comparison_runtime_authorized"] is False
    assert decision["current_formal_attempts"] == 0

    matrix = _csv(AMENDMENT_BASE / "blocker_resolution_matrix.tsv")
    assert list(matrix[0]) == [
        "clause_id",
        "original_status",
        "resolution_status",
        "resolution_evidence",
        "static_validation",
    ]
    assert [row["clause_id"] for row in matrix] == BLOCKERS
    assert all(row["original_status"] == "FAIL" for row in matrix)
    assert all(row["resolution_status"] == "RESOLVED" for row in matrix)
    assert all((ROOT / row["resolution_evidence"]).exists() for row in matrix)

    rows = load_scenario_map()
    counts = validate_manifest()
    assert len(rows) == 6
    assert counts == {"components": 25, "bindings": 6}
    assert build_plan()["status"] == "STATIC_PLAN_PASS"
    assert build_plan()["slot_count"] == 6
    static = preflight(require_clean=False)
    assert static["status"] == "STATIC_PREFLIGHT_PASS"
    assert static["runtime_started"] is False
    assert static["flight_communication_started"] is False
    env = environment()
    assert env["status"] == "STATICALLY_AVAILABLE"
    assert env["runtime_started"] is False

    refusal = subprocess.run(
        [
            sys.executable,
            "scripts/fuzzer_v0/family_a/run_v0p_qualification.py",
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
            STARTING_COMMIT,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert refusal.returncode == EXIT_AUTHORITY_REFUSAL
    refusal_result = json.loads(refusal.stdout)
    assert refusal_result["status"] == "EXECUTE_REFUSED"
    assert refusal_result["runtime_started"] is False
    assert refusal_result["formal_attempt_registered"] is False

    authority = original_authority_state()
    assert authority == {
        "decision": "DECLINE_IMPLEMENTATION_NOT_READY",
        "decision_status": "QUALIFICATION_NOT_AUTHORIZED",
        "qualification_authorized": False,
        "runtime_authorized": False,
        "comparison_runtime_authorized": False,
        "ledger_status": "NOT_AUTHORIZED",
        "formal_attempts": 0,
        "accepted_attempts": 0,
        "comparison_attempts": 0,
        "runtime_executed": False,
    }
    original_ledger = read_yaml(FAMILY_BASE / "attempt_ledger.yaml")
    assert original_ledger["formal_attempts"] == 0
    assert original_ledger["qualification_attempts"] == 0
    assert original_ledger["attempts"] == []

    assert gate["status"] == "READINESS_RESOLVED_PENDING_INDEPENDENT_REVIEW"
    assert gate["original_decision"] == "DECLINE_IMPLEMENTATION_NOT_READY"
    assert gate["original_blocking_clause_count"] == 11
    assert gate["resolved_clause_count"] == len(gate["resolved_clauses"]) == 11
    assert gate["resolved_clauses"] == BLOCKERS
    assert gate["remaining_clause_count"] == len(gate["remaining_clauses"]) == 0
    readiness_flags = (
        "runner_ready",
        "scenario_mapping_ready",
        "collectors_bound",
        "evidence_generator_ready",
        "cleanup_checker_ready",
        "v0p_only_enforced",
        "safety_monitor_ready",
        "physical_bounds_integrated",
        "residual_process_checker_ready",
        "port_checker_ready",
        "ros_jazzy_environment_ready",
        "static_plan_passed",
        "static_preflight_passed",
        "execute_refusal_passed",
        "focused_tests_passed",
        "repository_validation_passed",
    )
    assert all(gate[field] is True for field in readiness_flags)
    assert gate["formal_attempts"] == 0
    assert gate["qualification_authorized"] is False
    assert gate["runtime_authorized"] is False
    assert gate["formal_attempts_authorized"] is False
    assert gate["comparison_runtime_authorized"] is False
    assert gate["requires_independent_activation_rereview"] is True
    assert gate["next_exact_action"] == NEXT_ACTION
    assert amendment["next_exact_action"] == NEXT_ACTION

    amendment_commit = gate["amendment_commit"]
    assert amendment_commit == source_lock["amendment_commit"]
    assert amendment_commit == amendment["implementation_commit"]
    manifest_hash = sha256(AMENDMENT_BASE / "implementation_manifest.yaml")
    assert gate["implementation_manifest_sha256"] == source_lock[
        "implementation_manifest_sha256"
    ]
    if amendment_commit == IMPLEMENTATION_SENTINEL:
        assert gate["implementation_manifest_sha256"] == MANIFEST_SENTINEL
    else:
        assert re.fullmatch(r"[0-9a-f]{40}", amendment_commit)
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", amendment_commit, "HEAD"],
            cwd=ROOT,
            check=True,
        )
        assert gate["implementation_manifest_sha256"] == manifest_hash
        blob_hash = _sha_bytes(
            _git_blob(
                amendment_commit,
                "experiments/fuzzer_v0/family_a/readiness_amendment/implementation_manifest.yaml",
            )
        )
        assert blob_hash == manifest_hash
    assert gate["identity_lock_commit"] == source_lock["identity_lock_commit"]
    assert gate["identity_lock_commit"] == amendment["identity_lock_commit"]
    assert gate["identity_lock_commit"] == IDENTITY_SENTINEL or re.fullmatch(
        r"[0-9a-f]{40}", gate["identity_lock_commit"]
    )

    runner_text = (
        ROOT / "scripts/fuzzer_v0/family_a/run_v0p_qualification.py"
    ).read_text(encoding="utf-8")
    assert "scripts.fuzzer.executor" not in runner_text
    assert "scripts/fuzzer/executor.py" not in runner_text
    assert '"0.3"' not in runner_text
    assert len(list((ROOT / "scripts").rglob("run_v0p_qualification.py"))) == 1

    tracked_runs = _git("ls-files", "runs").splitlines()
    assert tracked_runs == []
    checked_paths = (
        list(AMENDMENT_BASE.iterdir())
        + [
            ROOT / "docs/design/FAMILY_A_FUZZER_V0_READINESS_AMENDMENT.md",
            SCHEMA_PATH,
            ROOT
            / "data/schemas/family_a_fuzzer_v0_compact_evidence.schema.json",
            ROOT / "scripts/fuzzer_v0/family_a/run_v0p_qualification.py",
            ROOT
            / "scripts/fuzzer_v0/family_a/build_v0p_compact_evidence.py",
            ROOT / "scripts/fuzzer_v0/family_a/check_v0p_cleanup.py",
            ROOT / "scripts/fuzzer_v0/family_a/check_v0p_safety.py",
            ROOT / "scripts/fuzzer_v0/family_a/check_v0p_runtime_residue.py",
        ]
    )
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in checked_paths
        if path.is_file()
    )
    assert "/home/" not in text
    assert "/mnt/" not in text
    credential = re.compile(
        r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN [^-]*PRIVATE KEY-----"
    )
    assert credential.search(text) is None

    return {
        "original_blockers": len(original_blockers),
        "resolved_blockers": len(matrix),
        "remaining_blockers": gate["remaining_clause_count"],
        "scenario_slots": len(rows),
        "implementation_components": counts["components"],
        "orchestration_bindings": counts["bindings"],
        "ros_jazzy_environment": env["status"],
        "static_plan": "PASS",
        "static_preflight": "PASS",
        "execute_refusal": "PASS",
        "formal_attempts": authority["formal_attempts"],
        "tracked_raw_files": len(tracked_runs),
    }


def main() -> None:
    result = validate()
    print("Family A Fuzzer v0 V0-P readiness amendment check passed")
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
