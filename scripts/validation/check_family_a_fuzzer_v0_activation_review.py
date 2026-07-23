#!/usr/bin/env python3
"""Validate the independent Family A Fuzzer v0 qualification activation review."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]
FAMILY_BASE = ROOT / "experiments/fuzzer_v0/family_a"
REVIEW_BASE = FAMILY_BASE / "activation_review"
DECISION_PATH = REVIEW_BASE / "qualification_activation_decision.json"
SCHEMA_PATH = (
    ROOT / "data/schemas/family_a_fuzzer_v0_qualification_activation.schema.json"
)
CHECKLIST_PATH = REVIEW_BASE / "activation_review_checklist.tsv"
NEXT_ACTION = (
    "create an independent amendment or readiness-resolution plan for the recorded blockers"
)


def read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_blob(commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def assert_ancestor(commit: str) -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def iter_identity_records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            yield value
        for child in value.values():
            yield from iter_identity_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_identity_records(child)


def read_checklist() -> list[dict[str, str]]:
    with CHECKLIST_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows
    return rows


def read_seeds() -> list[dict[str, str]]:
    with (FAMILY_BASE / "seed_catalog.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows
    return rows


def validate() -> dict[str, int]:
    required_assets = {
        "README.md",
        "activation_review_checklist.tsv",
        "qualification_activation_decision.json",
        "qualification_attempt_ledger.yaml",
        "qualification_runbook.md",
        "review_source_lock.yaml",
    }
    assert required_assets <= {
        path.name for path in REVIEW_BASE.iterdir() if path.is_file()
    }

    source_lock = read_yaml(REVIEW_BASE / "review_source_lock.yaml")
    decision = read_json(DECISION_PATH)
    schema = read_json(SCHEMA_PATH)
    ledger = read_yaml(REVIEW_BASE / "qualification_attempt_ledger.yaml")
    checklist = read_checklist()
    prereg = read_yaml(FAMILY_BASE / "preregistration.yaml")
    campaign = read_yaml(FAMILY_BASE / "campaign_matrix.yaml")
    oracle_lock = read_yaml(FAMILY_BASE / "oracle_lock.yaml")
    original_activation = read_json(FAMILY_BASE / "activation_gate.json")
    original_ledger = read_yaml(FAMILY_BASE / "attempt_ledger.yaml")
    seeds = read_seeds()

    jsonschema.Draft202012Validator(schema).validate(decision)
    assert source_lock["starting_head"] == source_lock["starting_origin_main"]
    assert source_lock["starting_head"] == decision["starting_repository_commit"]
    assert (
        source_lock["reviewed_preregistration_commit"]
        == decision["reviewed_preregistration_commit"]
        == "426f4c7316e973c6a4dab84a202fdb75ea65b7c1"
    )
    assert source_lock["starting_ahead"] == source_lock["starting_behind"] == 0
    for commit in source_lock["required_ancestor_commits"]:
        assert_ancestor(commit)

    frozen_paths: set[str] = set()
    for record in source_lock["frozen_bundle"]:
        path = ROOT / record["path"]
        assert path.is_file(), record["path"]
        assert sha256(path) == record["sha256"], record["path"]
        frozen_paths.add(record["path"])
    assert len(frozen_paths) == len(source_lock["frozen_bundle"]) == 15

    starting_commit = source_lock["starting_head"]
    support_paths: set[str] = set()
    for record in source_lock["review_support_at_starting_commit"]:
        assert sha256_bytes(git_blob(starting_commit, record["path"])) == record["sha256"]
        support_paths.add(record["path"])
    assert len(support_paths) == len(source_lock["review_support_at_starting_commit"]) == 5

    expected_fields = [
        "clause_id",
        "category",
        "required_condition",
        "evidence_path",
        "observed_value",
        "expected_value",
        "status",
        "blocking",
        "notes",
    ]
    assert list(checklist[0]) == expected_fields
    assert len({row["clause_id"] for row in checklist}) == len(checklist)
    assert {row["status"] for row in checklist} <= {
        "PASS",
        "FAIL",
        "NOT_APPLICABLE",
    }
    assert {row["blocking"] for row in checklist} <= {"true", "false"}
    assert {row["category"] for row in checklist} >= {
        "Authority",
        "Repository identity",
        "Scope",
        "Seeds",
        "Runtime contract readiness",
        "Oracle identities",
        "Execution readiness",
        "Safety readiness",
        "Accounting readiness",
        "Review closure",
    }
    blocking_failures = [
        row["clause_id"]
        for row in checklist
        if row["blocking"] == "true" and row["status"] == "FAIL"
    ]
    assert blocking_failures == decision["blocking_clauses"]
    assert len(blocking_failures) == decision["blocking_clause_count"] == 11

    assert decision["decision"] == "DECLINE_IMPLEMENTATION_NOT_READY"
    assert decision["status"] == "QUALIFICATION_NOT_AUTHORIZED"
    assert decision["authorized_scope"] == "NONE"
    assert decision["qualification_authorized"] is False
    assert decision["runtime_authorized"] is False
    assert decision["activation_review_complete"] is True
    assert decision["runtime_executed_during_review"] is False
    assert decision["qualification_execution_requires_separate_task"] is True
    for field in (
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
    ):
        assert decision[field] is False
    assert decision["next_exact_action"] == NEXT_ACTION
    assert len(decision["non_blocking_findings"]) == 4

    assert prereg["status"] == "PREREGISTERED_NOT_ACTIVATED"
    assert prereg["formal_scope"]["authorized_family"] == "FAMILY_A_ONLY"
    assert original_activation["campaign_activated"] is False
    assert original_activation["runtime_authorized"] is False
    assert original_activation["formal_attempts_authorized"] is False
    assert original_ledger["formal_attempts"] == 0
    assert original_ledger["qualification_attempts"] == 0
    assert set(original_ledger["strategy_counts"].values()) == {0}
    assert original_ledger["attempts"] == []

    phase = next(item for item in campaign["phases"] if item["phase_id"] == "V0-P")
    assert phase["accepted_qualification_target"] == 3
    assert phase["maximum_future_formal_attempts"] == 6
    assert phase["included_in_comparison_budget"] is False
    assert campaign["budget_rules"]["total_future_formal_comparison_attempts"] == 36
    assert campaign["budget_rules"]["qualification_budget_is_not_comparison_budget"] is True
    assert campaign["budget_rules"]["unused_budget_transfer_between_arms"] is False

    assert ledger == {
        "schema_version": "1.0",
        "campaign_id": "FAMILY_A_FUZZER_V0",
        "phase_id": "V0_P_QUALIFICATION",
        "status": "NOT_AUTHORIZED",
        "activation_decision": "DECLINE_IMPLEMENTATION_NOT_READY",
        "activation_decision_commit": (
            "COMMIT_CONTAINING_THIS_DECLINED_DECISION_REPORTED_BY_GIT_AFTER_PUSH"
        ),
        "qualification_target_accepted": 3,
        "qualification_maximum_formal_attempts": 6,
        "formal_attempts": 0,
        "accepted_attempts": 0,
        "comparison_attempts": 0,
        "next_attempt_id": "V0P-A1",
        "runtime_executed": False,
        "attempts": [],
    }

    assert len(seeds) == 61
    runtime = [row for row in seeds if row["inclusion_status"] == "ACCEPTED_RUNTIME_SEED"]
    replay = [
        row
        for row in seeds
        if row["inclusion_status"] == "ACCEPTED_REPLAY_BENCHMARK"
    ]
    excluded = [row for row in seeds if row["inclusion_status"] == "EXCLUDED"]
    unresolved = [row for row in seeds if row["inclusion_status"] == "UNRESOLVED"]
    assert (len(runtime), len(replay), len(excluded), len(unresolved)) == (50, 1, 10, 0)
    assert all(row["current_or_historical"] == "CURRENT" for row in runtime)
    assert all(row["runtime_or_replay"] == "RUNTIME" for row in runtime)
    assert all(row["source_campaign"] != "ORACLE_VALIDATION" for row in runtime)
    assert replay[0]["seed_id"] == "ISSUE162_HISTORICAL_REPLAY"
    assert replay[0]["runtime_or_replay"] == "REPLAY_ONLY"

    assert oracle_lock["route_oracle"]["version"] == "0.4"
    assert oracle_lock["freshness_oracle"]["version"] == "0.1"
    assert oracle_lock["successor_progression_oracle"]["version"] == "0.1"
    assert oracle_lock["authority_event_linearization_oracle"]["version"] == "0.2"
    assert oracle_lock["evidence_admissibility_gate"]["version"] == "1.0"
    assert oracle_lock["identity_consistency"]["old_Route_Oracle_0_3_identity_used"] is False
    identity_records = list(iter_identity_records(oracle_lock))
    for record in identity_records:
        path = ROOT / record["path"]
        assert path.is_file(), record["path"]
        assert sha256(path) == record["sha256"], record["path"]

    # The only runnable fuzzer executor is the explicitly inadmissible
    # pre-M-FINAL prototype. A decline must not silently treat it as V0-P.
    assert not (ROOT / "scripts/fuzzer/family_a_qualification_runner.py").exists()
    assert not (ROOT / "scripts/fuzzer/family_a_qualification_ledger.py").exists()
    prototype = (ROOT / "scripts/fuzzer/executor.py").read_text(encoding="utf-8")
    seed_loader = (ROOT / "scripts/fuzzer/seed_loader.py").read_text(encoding="utf-8")
    assert '"version": "0.3"' in prototype
    assert "experiments/fuzzer_v0/seed_manifest.yaml" in seed_loader

    runbook = (REVIEW_BASE / "qualification_runbook.md").read_text(encoding="utf-8")
    for attempt_id in ("V0P-A1", "V0P-A2", "V0P-A3", "V0P-A4", "V0P-A5", "V0P-A6"):
        assert attempt_id in runbook
    for seed_id in (
        "P0_A_OFFBOARD_ADMISSION",
        "P0_B_DYNAMIC_ADMISSION",
        "P0_C_EXECUTOR_COMPLETION",
        "P3_OFFBOARD_H1_S0",
        "P2_DYNAMIC_SIGTERM",
        "C1_PAIR_B",
    ):
        assert seed_id in runbook
    assert "REQUIRED_FUTURE_ENTRY" in runbook
    assert "NOT EXECUTABLE AT THIS REVIEW COMMIT" in runbook

    current_text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "README.md",
            "docs/narrative/CURRENT_NARRATIVE.md",
            "docs/repository/CURRENT_GOAL_STATE.md",
            "docs/repository/MOTIVATION_COMPLETION_STATE.md",
            "experiments/fuzzer_v0/family_a/README.md",
        )
    )
    assert "DECLINE_IMPLEMENTATION_NOT_READY" in current_text
    assert "QUALIFICATION_NOT_AUTHORIZED" in current_text
    assert NEXT_ACTION in current_text
    assert "formal attempts: `0`" in current_text
    assert "state-aware search gain: `not_established`" in current_text.lower()
    assert "full method effectiveness: `not_established`" in current_text.lower()

    reviewed_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (
            *sorted(REVIEW_BASE.iterdir()),
            ROOT / "docs/design/FAMILY_A_FUZZER_V0_ACTIVATION_REVIEW.md",
        )
        if path.is_file()
    )
    assert "/home/" not in reviewed_text
    assert "/mnt/" not in reviewed_text
    credential_pattern = re.compile(
        r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN [^-]*PRIVATE KEY-----"
    )
    assert credential_pattern.search(reviewed_text) is None

    tracked_runs = subprocess.run(
        ["git", "ls-files", "runs"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert tracked_runs == []

    return {
        "checklist_clauses": len(checklist),
        "blocking_failures": len(blocking_failures),
        "non_blocking_findings": len(decision["non_blocking_findings"]),
        "seed_records": len(seeds),
        "runtime_seeds": len(runtime),
        "historical_replay_seeds": len(replay),
        "excluded_seeds": len(excluded),
        "unresolved_seeds": len(unresolved),
        "qualification_formal_attempts": ledger["formal_attempts"],
        "comparison_attempts": ledger["comparison_attempts"],
        "tracked_raw_files": len(tracked_runs),
        "oracle_identity_records": len(identity_records),
    }


def main() -> None:
    result = validate()
    print("Family A Fuzzer v0 activation review consistency check passed")
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
