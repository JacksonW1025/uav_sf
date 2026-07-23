#!/usr/bin/env python3
"""Strict final checker for Family A Fuzzer v0 full readiness."""

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

from scripts.fuzzer_v0.family_a.execution_graph import validate_graph


ROOT = Path(__file__).resolve().parents[2]
FAMILY = ROOT / "experiments/fuzzer_v0/family_a"
READINESS = FAMILY / "full_readiness"
SCHEMAS = ROOT / "data/schemas"
FINDINGS = {"E-11", "E-12", "F-07", "F-08", "H-16", "J-12", "J-13", "J-14", "K-09"}
REQUIRED_FILES = {
    "source_lock.yaml",
    "full_environment_lock.yaml",
    "package_inventory.json",
    "binary_manifest.json",
    "component_manifest.yaml",
    "slot_execution_graph.yaml",
    "authorization_contract.yaml",
    "authorization_identity_manifest.json",
    "attempt_accounting_contract.yaml",
    "full_readiness_gate.json",
    "validation_manifest.yaml",
    "independent_review_checklist.tsv",
    "independent_test_manifest.yaml",
    "qualification_activation_decision.json",
    "initial_qualification_ledger.yaml",
    "README.md",
}
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class FullReadinessError(RuntimeError):
    """A final readiness invariant is false."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FullReadinessError(f"{path}: expected an object")
    return value


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FullReadinessError(f"{path}: expected a mapping")
    return value


def _git(*args: str, check: bool = True) -> str:
    process = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True
    )
    if check and process.returncode:
        raise FullReadinessError(
            f"git {' '.join(args)} failed: {process.stderr.strip()}"
        )
    return process.stdout.strip()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FullReadinessError(message)


def _schema(instance: dict[str, Any], schema_name: str) -> None:
    jsonschema.Draft202012Validator(
        _json(SCHEMAS / schema_name)
    ).validate(instance)


def _verify_git_state() -> dict[str, Any]:
    branch = _git("symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    head = _git("rev-parse", "HEAD")
    origin = _git("rev-parse", "origin/main")
    counts = _git("rev-list", "--left-right", "--count", "HEAD...origin/main").split()
    _require(branch == "main", "final readiness requires attached branch main")
    _require(not _git("status", "--porcelain"), "final readiness worktree is dirty")
    _require(head == origin and counts == ["0", "0"], "HEAD is not exact pushed origin/main")
    return {"branch": branch, "head": head, "origin_main": origin, "ahead_behind": [0, 0]}


def _verify_frozen_design() -> dict[str, Any]:
    source_lock = _yaml(READINESS / "source_lock.yaml")
    for record in source_lock["frozen_assets"]:
        path = ROOT / record["path"]
        _require(path.is_file(), f"frozen asset is missing: {record['path']}")
        _require(_sha256(path) == record["sha256"], f"frozen asset changed: {record['path']}")
    rows = list(
        csv.DictReader(
            (FAMILY / "seed_catalog.tsv").open(encoding="utf-8"),
            delimiter="\t",
        )
    )
    dispositions = [row["inclusion_status"] for row in rows]
    _require(len(rows) == 61, "seed catalog does not contain 61 records")
    _require(
        dispositions.count("ACCEPTED_RUNTIME_SEED") == 50
        and dispositions.count("ACCEPTED_REPLAY_BENCHMARK") == 1
        and dispositions.count("EXCLUDED") == 10,
        "frozen seed disposition counts changed",
    )
    ledger = _yaml(FAMILY / "attempt_ledger.yaml")
    _require(
        ledger.get("formal_attempts") == 0
        and ledger.get("qualification_attempts") == 0
        and ledger.get("attempts") == [],
        "frozen formal attempt ledger is not zero",
    )
    tracked_runs = _git("ls-files", "runs")
    _require(not tracked_runs, "raw run artifacts are tracked")
    _require(
        not (ROOT / "runs/fuzzer_v0/family_a/v0p/V0P-A1").exists()
        and not (FAMILY / "qualification_attempts/V0P-A1").exists(),
        "V0P-A1 was created",
    )
    return {"seed_records": 61, "formal_attempts": 0, "V0P_A1_created": False}


def _verify_environment() -> dict[str, Any]:
    environment = _yaml(READINESS / "full_environment_lock.yaml")
    inventory = _json(READINESS / "package_inventory.json")
    binaries = _json(READINESS / "binary_manifest.json")
    _schema(environment, "family_a_fuzzer_v0_full_environment_lock.schema.json")
    _schema(binaries, "family_a_fuzzer_v0_binary_manifest.schema.json")
    _require(environment["status"] == "LOCKED_CONTAINER_READY", "container is not locked ready")
    image_id = environment["full_image"].get("image_id")
    _require(image_id == binaries["image_id"] == inventory["image_id"], "image identities differ")
    _require(
        environment["base_image"]["oci_index_digest"]
        == "sha256:31daab66eef9139933379fb67159449944f4e2dcf2e22c2d12cc715f29873e0f",
        "base OCI index digest differs",
    )
    _require(
        environment["base_image"]["platform_digest"]
        == "sha256:b82a5ba3869a81196414cf34e4fc25c7935aab78b1f5187570ca9362c478cdbd",
        "base arm64 platform digest differs",
    )
    _require(inventory["architecture"] == "aarch64", "captured architecture differs")
    _require(inventory["environment"]["ROS_DISTRO"] == "jazzy", "captured ROS is not Jazzy")
    _require(
        inventory["environment"]["RMW_IMPLEMENTATION"] == "rmw_fastrtps_cpp",
        "captured RMW identity differs",
    )
    for path, expected in environment["lock_hashes"].items():
        locked = ROOT / path
        _require(locked.is_file() and _sha256(locked) == expected, f"lock hash mismatch: {path}")
    required_binaries = {
        "px4_sitl",
        "micro_xrce_dds_agent",
        "px4_ros2_cpp",
        "adapter_dynamic",
        "adapter_executor",
        "adapter_c1",
        "evaluator_runner",
        "safety_supervisor",
        "route_collector",
        "clock_collector",
        "writer_collector",
        "route_oracle_0_4",
        "freshness_oracle_0_1",
        "successor_oracle_0_1",
        "linearization_oracle_0_2",
        "n1_collector",
        "p5_collector",
    }
    by_id = {record["component_id"]: record for record in binaries["binaries"]}
    _require(required_binaries <= set(by_id), "formal binary manifest is incomplete")
    for record in binaries["binaries"]:
        _require(record["read_only_entry_check"]["status"] == "PASS", "read-only check failed")
        linkage = "\n".join(record["linked_libraries"]).lower()
        _require(
            "/home/" not in linkage and "/mnt/" not in linkage and "humble" not in linkage,
            f"host/Humble binary linkage: {record['component_id']}",
        )
    _require(
        by_id["adapter_c1"]["ros_distro"] == "jazzy"
        and by_id["adapter_c1"]["output_path"].startswith("/opt/family_a/workspace/ros/install/"),
        "C1 is not the Jazzy workspace binary",
    )
    return {
        "image_id": image_id,
        "binary_count": len(binaries["binaries"]),
        "dpkg_package_count": len(inventory["dpkg_packages"]),
    }


def _verify_validation_evidence() -> dict[str, Any]:
    validation = _yaml(READINESS / "validation_manifest.yaml")
    review_tests = _yaml(READINESS / "independent_test_manifest.yaml")
    _require(validation.get("status") == "PASS", "container validation manifest is not PASS")
    _require(validation.get("runtime_started") is False, "container validation started runtime")
    checks = validation.get("checks")
    _require(isinstance(checks, list) and len(checks) >= 20, "container checks are incomplete")
    for check in checks:
        _require(check.get("status") == "PASS", f"container check failed: {check.get('check_id')}")
        _require(check.get("runtime_started") is False, "a container check started runtime")
        _require(check.get("container_identity") == validation.get("image_id"), "check image differs")
    _require(review_tests.get("status") == "PASS", "independent test manifest is not PASS")
    _require(review_tests.get("clean_clone") is True, "review was not from a clean clone")
    _require(review_tests.get("runtime_started") is False, "independent review started runtime")
    for test in review_tests.get("tests", []):
        _require(test.get("status") == "PASS", f"independent test failed: {test.get('test_id')}")
    with (READINESS / "independent_review_checklist.tsv").open(encoding="utf-8") as handle:
        checklist = list(csv.DictReader(handle, delimiter="\t"))
    clauses = {row["clause_id"] for row in checklist if row["blocking"] == "true"}
    _require(clauses == FINDINGS, "independent checklist does not cover exactly nine findings")
    _require(all(row["status"] == "PASS" for row in checklist), "independent checklist is not all PASS")
    return {"container_checks": len(checks), "independent_tests": len(review_tests.get("tests", []))}


def _verify_authorization(git_state: dict[str, Any]) -> dict[str, Any]:
    decision = _json(READINESS / "qualification_activation_decision.json")
    ledger = _yaml(READINESS / "initial_qualification_ledger.yaml")
    manifest = _json(READINESS / "authorization_identity_manifest.json")
    _schema(manifest, "family_a_fuzzer_v0_authorization_manifest.schema.json")
    expected_decision = {
        "decision": "APPROVE_QUALIFICATION_ONLY",
        "status": "QUALIFICATION_AUTHORIZED_NOT_STARTED",
        "authorized_scope": "V0_P_QUALIFICATION_ONLY",
        "qualification_target_accepted": 3,
        "qualification_maximum_formal_attempts": 6,
        "current_formal_attempts": 0,
        "current_accepted_attempts": 0,
        "next_attempt_id": "V0P-A1",
        "qualification_runtime_authorized": True,
        "qualification_execution_requires_separate_task": True,
        "comparison_runtime_authorized": False,
        "official_sequence_authorized": False,
        "bounded_random_timing_authorized": False,
        "state_aware_authorized": False,
        "real_workload_authorized": False,
        "family_b_authorized": False,
        "direct_actuator_authorized": False,
        "hitl_authorized": False,
        "real_flight_authorized": False,
        "execution_not_started": True,
    }
    for field, expected in expected_decision.items():
        _require(decision.get(field) == expected, f"activation decision mismatch: {field}")
    _require(
        ledger.get("formal_attempts") == 0
        and ledger.get("accepted_attempts") == 0
        and ledger.get("attempts") == []
        and ledger.get("next_attempt_id") == "V0P-A1",
        "initial qualification ledger is not pristine",
    )
    for label in ("decision", "initial_ledger"):
        record = manifest[label]
        path = ROOT / record["path"]
        _require(path.is_file() and _sha256(path) == record["sha256"], f"{label} hash differs")
    for label, record in manifest["locked_assets"].items():
        path = ROOT / record["path"]
        _require(path.is_file() and _sha256(path) == record["sha256"], f"locked asset differs: {label}")
    for label, commit in manifest["commits"].items():
        _require(HEX40.fullmatch(commit) is not None, f"invalid commit identity: {label}")
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, git_state["head"]],
            cwd=ROOT,
        )
        _require(ancestor.returncode == 0, f"commit not in HEAD ancestry: {label}")
    authorization_commit = _git(
        "log",
        "-1",
        "--format=%H",
        "--",
        "experiments/fuzzer_v0/family_a/full_readiness/authorization_identity_manifest.json",
    )
    blob = subprocess.run(
        [
            "git",
            "show",
            f"{authorization_commit}:experiments/fuzzer_v0/family_a/full_readiness/authorization_identity_manifest.json",
        ],
        cwd=ROOT,
        capture_output=True,
    )
    _require(
        blob.returncode == 0
        and blob.stdout == (READINESS / "authorization_identity_manifest.json").read_bytes(),
        "authorization identity-lock commit does not contain the exact manifest",
    )
    return {
        "decision": decision["decision"],
        "status": decision["status"],
        "authorization_identity_lock_commit": authorization_commit,
    }


def validate() -> dict[str, Any]:
    missing = sorted(name for name in REQUIRED_FILES if not (READINESS / name).is_file())
    _require(not missing, f"required full-readiness files are missing: {missing}")
    git_state = _verify_git_state()
    frozen = _verify_frozen_design()
    graph = validate_graph(
        READINESS / "slot_execution_graph.yaml",
        READINESS / "component_manifest.yaml",
    )
    environment = _verify_environment()
    evidence = _verify_validation_evidence()
    gate = _json(READINESS / "full_readiness_gate.json")
    _schema(gate, "family_a_fuzzer_v0_full_readiness_gate.schema.json")
    _require(
        gate["status"] == "PASS"
        and gate["blocking_findings"] == []
        and set(gate["checks"]) == FINDINGS
        and all(value == "PASS" for value in gate["checks"].values()),
        "nine-finding readiness gate is not exact PASS",
    )
    authorization = _verify_authorization(git_state)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "git": git_state,
        "frozen_design": frozen,
        "environment": environment,
        "execution_graph": graph,
        "validation": evidence,
        "readiness_findings_resolved": 9,
        "remaining_findings": [],
        "authorization": authorization,
        "runtime_started": False,
        "formal_attempts": 0,
    }


def main() -> int:
    try:
        result = validate()
    except (
        FullReadinessError,
        json.JSONDecodeError,
        jsonschema.ValidationError,
        yaml.YAMLError,
    ) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
