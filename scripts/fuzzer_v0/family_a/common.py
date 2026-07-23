#!/usr/bin/env python3
"""Shared static contracts for the Family A V0-P qualification path."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
FAMILY_BASE = ROOT / "experiments/fuzzer_v0/family_a"
AMENDMENT_BASE = FAMILY_BASE / "readiness_amendment"
SCENARIO_MAP_PATH = AMENDMENT_BASE / "qualification_scenario_map.tsv"
MANIFEST_PATH = AMENDMENT_BASE / "implementation_manifest.yaml"
ENVIRONMENT_LOCK_PATH = AMENDMENT_BASE / "environment_lock.yaml"
DECISION_PATH = (
    FAMILY_BASE / "activation_review/qualification_activation_decision.json"
)
QUALIFICATION_LEDGER_PATH = (
    FAMILY_BASE / "activation_review/qualification_attempt_ledger.yaml"
)
ALLOWED_PHASE = "V0_P_QUALIFICATION"
ALLOWED_STRATEGY = "QUALIFICATION"
COMPARISON_STRATEGIES = {
    "OFFICIAL_SEQUENCE",
    "BOUNDED_RANDOM_TIMING_COMPARATOR",
    "STATE_AWARE_MUTATION",
}
SLOT_IDS = tuple(f"V0P-S{number}" for number in range(1, 7))
ATTEMPT_IDS = tuple(f"V0P-A{number}" for number in range(1, 7))
SCHEDULE = (
    ("V0P-S1", "V0P-A1", "P0_A_OFFBOARD_ADMISSION", 410101),
    ("V0P-S2", "V0P-A2", "P0_B_DYNAMIC_ADMISSION", 410102),
    ("V0P-S3", "V0P-A3", "P0_C_EXECUTOR_COMPLETION", 410103),
    ("V0P-S4", "V0P-A4", "P3_OFFBOARD_H1_S0", 410104),
    ("V0P-S5", "V0P-A5", "P2_DYNAMIC_SIGTERM", 410105),
    ("V0P-S6", "V0P-A6", "C1_PAIR_B", 410106),
)
REQUIRED_SCENARIO_FIELDS = (
    "slot_id",
    "attempt_id",
    "simulation_seed",
    "seed_id",
    "source_campaign",
    "source_artifact",
    "mechanism",
    "scenario_family",
    "source_route",
    "target_or_retained_route",
    "setpoint_level",
    "expected_lifecycle_sequence",
    "expected_oracles",
    "runner_adapter",
    "collector_profile",
    "safety_profile",
    "cleanup_profile",
    "accepted_target_role",
    "maximum_slot_use",
    "integrity_status",
)


class ContractError(ValueError):
    """A static qualification contract is inconsistent."""


def read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError(f"{path}: root must be a mapping")
    return value


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError(f"{path}: root must be an object")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_text(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def load_seed_catalog() -> dict[str, dict[str, str]]:
    path = FAMILY_BASE / "seed_catalog.tsv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(rows) != 61 or len({row["seed_id"] for row in rows}) != 61:
        raise ContractError("seed catalog must contain 61 unique rows")
    return {row["seed_id"]: row for row in rows}


def load_scenario_map(path: Path = SCENARIO_MAP_PATH) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
        fields = tuple(reader.fieldnames or ())
    if fields != REQUIRED_SCENARIO_FIELDS:
        raise ContractError(
            "qualification scenario map fields differ from the locked readiness contract"
        )
    validate_scenario_rows(rows)
    return rows


def validate_scenario_rows(rows: list[dict[str, str]]) -> None:
    if len(rows) != 6:
        raise ContractError("qualification scenario map must contain exactly six slots")
    seeds = load_seed_catalog()
    observed_schedule = tuple(
        (
            row["slot_id"],
            row["attempt_id"],
            row["seed_id"],
            int(row["simulation_seed"]),
        )
        for row in rows
    )
    if observed_schedule != SCHEDULE:
        raise ContractError("qualification scenario schedule differs from the fixed runbook")
    if len({row["seed_id"] for row in rows}) != 6:
        raise ContractError("qualification scenario seeds must be unique")
    for row in rows:
        seed = seeds.get(row["seed_id"])
        if seed is None:
            raise ContractError(f"unknown qualification seed: {row['seed_id']}")
        for field in (
            "source_campaign",
            "source_artifact",
            "mechanism",
            "source_route",
            "target_or_retained_route",
            "setpoint_level",
        ):
            if row[field] != seed[field]:
                raise ContractError(f"{row['slot_id']}: frozen seed field mismatch: {field}")
        if row["expected_lifecycle_sequence"] != seed["lifecycle_sequence"]:
            raise ContractError(
                f"{row['slot_id']}: frozen lifecycle sequence was not preserved"
            )
        expected = set(row["expected_oracles"].split("|"))
        seed_oracles = set(seed["applicable_oracles"].split("|"))
        if not seed_oracles <= expected:
            raise ContractError(f"{row['slot_id']}: applicable Oracle binding is missing")
        if row["seed_id"] == "C1_PAIR_B" and "LINEARIZATION" not in expected:
            raise ContractError("C1_PAIR_B requires the Linearization Oracle")
        if (
            seed["inclusion_status"] != "ACCEPTED_RUNTIME_SEED"
            or seed["current_or_historical"] != "CURRENT"
            or seed["runtime_or_replay"] != "RUNTIME"
            or seed["source_campaign"] in {"R1", "W1", "B1", "ORACLE_VALIDATION"}
            or seed["setpoint_level"] == "DIRECT_ACTUATOR"
        ):
            raise ContractError(f"{row['slot_id']}: seed is outside current Family A scope")
        if row["accepted_target_role"] != "QUALIFICATION_ACCEPTED_TARGET":
            raise ContractError(f"{row['slot_id']}: invalid accepted target role")
        if row["maximum_slot_use"] != "1" or row["integrity_status"] != "PASS":
            raise ContractError(f"{row['slot_id']}: slot use or integrity is invalid")


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest = read_yaml(path)
    if manifest.get("schema_version") != "1.0":
        raise ContractError("implementation manifest schema version must be 1.0")
    return manifest


def validate_manifest(path: Path = MANIFEST_PATH) -> dict[str, int]:
    manifest = load_manifest(path)
    components = manifest.get("components")
    bindings = manifest.get("orchestration_bindings")
    if not isinstance(components, list) or not isinstance(bindings, list):
        raise ContractError("implementation manifest components and bindings are required")
    if len(bindings) != 6:
        raise ContractError("implementation manifest must bind exactly six slots")
    component_paths: set[str] = set()
    for record in components:
        if not isinstance(record, dict):
            raise ContractError("component record must be a mapping")
        required = {
            "path",
            "version",
            "sha256",
            "interface",
            "role",
            "reused_or_new",
            "static_validation_status",
        }
        if set(record) != required:
            raise ContractError(f"component fields are invalid: {record}")
        relative = str(record["path"])
        if relative in component_paths:
            raise ContractError(f"duplicate component path: {relative}")
        component_paths.add(relative)
        component = ROOT / relative
        if not component.is_file() or sha256(component) != record["sha256"]:
            raise ContractError(f"component identity mismatch: {relative}")
        if record["static_validation_status"] != "PASS":
            raise ContractError(f"component is not statically validated: {relative}")
        if record["reused_or_new"] not in {"REUSED", "NEW"}:
            raise ContractError(f"invalid reuse status: {relative}")

    rows = {row["slot_id"]: row for row in load_scenario_map()}
    if [item.get("slot_id") for item in bindings] != list(SLOT_IDS):
        raise ContractError("orchestration bindings do not follow the six-slot schedule")
    for binding in bindings:
        slot_id = str(binding["slot_id"])
        row = rows[slot_id]
        if binding.get("runner_adapter") != row["runner_adapter"]:
            raise ContractError(f"{slot_id}: runner adapter binding mismatch")
        for field in (
            "scenario_entry",
            "adapter_entries",
            "collector_bundle",
            "oracle_bundle",
            "evidence_profile",
            "safety_profile",
            "cleanup_profile",
        ):
            value = binding.get(field)
            values = value if isinstance(value, list) else [value]
            if not values or any(item not in component_paths for item in values):
                raise ContractError(f"{slot_id}: unresolved {field}")
    return {"components": len(components), "bindings": len(bindings)}


def enforce_scope(
    *,
    phase: str,
    strategy: str,
    seed_id: str | None = None,
    attempt_id: str | None = None,
) -> None:
    if phase != ALLOWED_PHASE:
        raise ContractError(f"phase must be {ALLOWED_PHASE}")
    if strategy != ALLOWED_STRATEGY:
        if strategy in COMPARISON_STRATEGIES:
            raise ContractError(f"comparison strategy is not authorized: {strategy}")
        raise ContractError(f"strategy must be {ALLOWED_STRATEGY}")
    rows = load_scenario_map()
    if seed_id is not None and seed_id not in {row["seed_id"] for row in rows}:
        raise ContractError(f"seed is not in the qualification scenario map: {seed_id}")
    if attempt_id is not None:
        match = re.fullmatch(r"V0P-A([0-9]+)", attempt_id)
        if match is None:
            raise ContractError("attempt ID must use the V0P-A<number> format")
        number = int(match.group(1))
        if number > 6:
            raise ContractError("qualification maximum is six formal attempts")
        if attempt_id not in ATTEMPT_IDS:
            raise ContractError(f"attempt ID is not a fixed qualification slot: {attempt_id}")
        expected = next(row for row in rows if row["attempt_id"] == attempt_id)
        if seed_id is not None and seed_id != expected["seed_id"]:
            raise ContractError("attempt ID and seed ID do not match the fixed schedule")


def original_authority_state() -> dict[str, Any]:
    decision = read_json(DECISION_PATH)
    ledger = read_yaml(QUALIFICATION_LEDGER_PATH)
    return {
        "decision": decision["decision"],
        "decision_status": decision["status"],
        "qualification_authorized": decision["qualification_authorized"],
        "runtime_authorized": decision["runtime_authorized"],
        "comparison_runtime_authorized": decision["comparison_runtime_authorized"],
        "ledger_status": ledger["status"],
        "formal_attempts": ledger["formal_attempts"],
        "accepted_attempts": ledger["accepted_attempts"],
        "comparison_attempts": ledger["comparison_attempts"],
        "runtime_executed": ledger["runtime_executed"],
    }
