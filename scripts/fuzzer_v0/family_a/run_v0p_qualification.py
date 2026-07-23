#!/usr/bin/env python3
"""Unique V0-P qualification runner with safe plan, preflight, and execute modes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.fuzzer_v0.family_a.check_v0p_runtime_residue import (
    evaluate as residue_check,
)
from scripts.fuzzer_v0.family_a.common import (
    ALLOWED_PHASE,
    ALLOWED_STRATEGY,
    AMENDMENT_BASE,
    DECISION_PATH,
    FAMILY_BASE,
    QUALIFICATION_LEDGER_PATH,
    ROOT,
    ContractError,
    enforce_scope,
    git_text,
    load_manifest,
    load_scenario_map,
    original_authority_state,
    read_json,
    read_yaml,
    sha256,
    validate_manifest,
)
from scripts.setup.verify_family_a_v0p_environment import (
    validate as validate_environment,
)


EXIT_SCOPE_REFUSAL = 2
EXIT_PREFLIGHT_FAILURE = 3
EXIT_AUTHORITY_REFUSAL = 4
EXIT_EXECUTION_FAILURE = 5
FROZEN_HASH_SOURCE = FAMILY_BASE / "activation_review/review_source_lock.yaml"


def _binding_map() -> dict[str, dict[str, Any]]:
    manifest = load_manifest()
    return {
        str(item["slot_id"]): item for item in manifest["orchestration_bindings"]
    }


def build_plan(seed_id: str | None = None) -> dict[str, Any]:
    rows = load_scenario_map()
    bindings = _binding_map()
    if seed_id is not None:
        rows = [row for row in rows if row["seed_id"] == seed_id]
    slots: list[dict[str, Any]] = []
    for row in rows:
        binding = bindings[row["slot_id"]]
        slots.append(
            {
                "slot_id": row["slot_id"],
                "attempt_id": row["attempt_id"],
                "seed_id": row["seed_id"],
                "simulation_seed": int(row["simulation_seed"]),
                "scenario_family": row["scenario_family"],
                "source_route": row["source_route"],
                "target_or_retained_route": row["target_or_retained_route"],
                "expected_oracles": row["expected_oracles"].split("|"),
                "runner_adapter": row["runner_adapter"],
                "scenario_entry": binding["scenario_entry"],
                "adapter_entries": binding["adapter_entries"],
                "collector_bundle": binding["collector_bundle"],
                "oracle_bundle": binding["oracle_bundle"],
                "evidence_profile": binding["evidence_profile"],
                "safety_profile": binding["safety_profile"],
                "cleanup_profile": binding["cleanup_profile"],
            }
        )
    return {
        "schema_version": "1.0",
        "status": "STATIC_PLAN_PASS",
        "phase": ALLOWED_PHASE,
        "strategy": ALLOWED_STRATEGY,
        "slot_count": len(slots),
        "qualification_target_accepted": 3,
        "qualification_maximum_formal_attempts": 6,
        "comparison_arms_reachable": False,
        "runtime_started": False,
        "slots": slots,
    }


def _validate_frozen_hashes() -> list[str]:
    errors: list[str] = []
    source_lock = read_yaml(FROZEN_HASH_SOURCE)
    for item in source_lock["frozen_bundle"]:
        path = ROOT / item["path"]
        if not path.is_file() or sha256(path) != item["sha256"]:
            errors.append(f"frozen identity mismatch: {item['path']}")
    return errors


def _git_clean() -> bool:
    return git_text("status", "--porcelain") == ""


def preflight(*, require_clean: bool = True) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    try:
        plan = build_plan()
        checks["scenario_mapping"] = {
            "status": "PASS" if plan["slot_count"] == 6 else "FAIL",
            "slot_count": plan["slot_count"],
        }
    except (ContractError, KeyError, ValueError) as exc:
        checks["scenario_mapping"] = {"status": "FAIL", "error": str(exc)}
    try:
        counts = validate_manifest()
        checks["implementation_manifest"] = {"status": "PASS", **counts}
    except (ContractError, KeyError, ValueError) as exc:
        checks["implementation_manifest"] = {"status": "FAIL", "error": str(exc)}
    frozen_errors = _validate_frozen_hashes()
    checks["frozen_identity"] = {
        "status": "PASS" if not frozen_errors else "FAIL",
        "errors": frozen_errors,
    }
    environment = validate_environment()
    checks["ros_jazzy_environment"] = {
        "status": "PASS" if environment["status"] == "STATICALLY_AVAILABLE" else "FAIL",
        "environment_status": environment["status"],
        "errors": environment["errors"],
    }
    residue = residue_check("preflight")
    checks["process_port_audit"] = {
        "status": "PASS" if residue["status"] == "CLEAN" else "FAIL",
        "audit_status": residue["status"],
        "processes": residue["processes"],
        "occupied_ports": residue["occupied_ports"],
    }
    authority = original_authority_state()
    authority_static = (
        authority["decision"] == "DECLINE_IMPLEMENTATION_NOT_READY"
        and authority["decision_status"] == "QUALIFICATION_NOT_AUTHORIZED"
        and authority["qualification_authorized"] is False
        and authority["runtime_authorized"] is False
        and authority["comparison_runtime_authorized"] is False
        and authority["formal_attempts"] == 0
        and authority["accepted_attempts"] == 0
        and authority["comparison_attempts"] == 0
        and authority["runtime_executed"] is False
    )
    checks["current_authority_and_accounting"] = {
        "status": "PASS" if authority_static else "FAIL",
        **authority,
    }
    clean = _git_clean()
    checks["worktree"] = {
        "status": "PASS" if clean or not require_clean else "FAIL",
        "clean": clean,
        "required": require_clean,
    }
    passed = all(item["status"] == "PASS" for item in checks.values())
    return {
        "schema_version": "1.0",
        "status": "STATIC_PREFLIGHT_PASS" if passed else "STATIC_PREFLIGHT_FAIL",
        "phase": ALLOWED_PHASE,
        "strategy": ALLOWED_STRATEGY,
        "checks": checks,
        "runtime_started": False,
        "flight_communication_started": False,
        "formal_attempt_registered": False,
    }


def _validate_independent_authority(
    *,
    decision_path: Path,
    ledger_path: Path,
    activation_commit: str,
    attempt_id: str,
    seed_id: str,
) -> None:
    current = read_json(DECISION_PATH)
    if (
        current.get("decision") != "DECLINE_IMPLEMENTATION_NOT_READY"
        or current.get("status") != "QUALIFICATION_NOT_AUTHORIZED"
    ):
        raise ContractError("the original activation decision identity changed")
    decision = read_json(decision_path)
    if decision_path.resolve() == DECISION_PATH.resolve():
        raise ContractError("the original DECLINE decision cannot authorize execute")
    if (
        decision.get("decision") != "APPROVE_QUALIFICATION"
        or decision.get("status") != "AUTHORIZED_NOT_STARTED"
        or decision.get("qualification_authorized") is not True
        or decision.get("runtime_authorized") is not True
        or decision.get("comparison_runtime_authorized") is not False
        or decision.get("requires_independent_activation_rereview") is not False
    ):
        raise ContractError("a later independent APPROVE decision is required")
    if (
        not isinstance(activation_commit, str)
        or len(activation_commit) != 40
        or git_text("rev-parse", activation_commit) != activation_commit
    ):
        raise ContractError("an independent activation decision commit is required")
    try:
        decision_relative = decision_path.resolve().relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ContractError("independent activation decision must be repository-relative") from exc
    decision_blob = subprocess.run(
        ["git", "show", f"{activation_commit}:{decision_relative}"],
        cwd=ROOT,
        capture_output=True,
    )
    if decision_blob.returncode != 0:
        raise ContractError("activation decision is not present in the supplied commit")
    if sha256(decision_path) != hashlib.sha256(decision_blob.stdout).hexdigest():
        raise ContractError("activation decision does not match the supplied commit")
    ledger = read_yaml(ledger_path)
    if (
        ledger.get("status") != "AUTHORIZED_NOT_STARTED"
        or ledger.get("formal_attempts") != 0
        or ledger.get("accepted_attempts") != 0
        or ledger.get("attempts") != []
        or ledger.get("next_attempt_id") != attempt_id
    ):
        raise ContractError("qualification ledger is not AUTHORIZED_NOT_STARTED")
    row = next(
        item for item in load_scenario_map() if item["attempt_id"] == attempt_id
    )
    if row["seed_id"] != seed_id:
        raise ContractError("authorized attempt does not match the fixed schedule")


def _scenario_command(row: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    attempt_id = row["attempt_id"]
    adapter = row["runner_adapter"]
    raw_root = ROOT / f"runs/fuzzer_v0/family_a/qualification/{attempt_id}/raw"
    compact_root = (
        ROOT / f"data/processed/fuzzer_v0/family_a/qualification/{attempt_id}"
    )
    env = {
        "V0P_PHASE": ALLOWED_PHASE,
        "V0P_STRATEGY": ALLOWED_STRATEGY,
        "V0P_SLOT_ID": row["slot_id"],
        "V0P_SEED_ID": row["seed_id"],
        "V0P_SIMULATION_SEED": row["simulation_seed"],
        "V0P_RAW_ROOT": str(raw_root),
        "V0P_COMPACT_ROOT": str(compact_root),
    }
    if adapter == "P0_OFFBOARD_CANONICAL":
        env.update(
            {
                "P0_RUN_ROOT": str(raw_root.parent.parent),
                "P0_PROCESSED_ROOT": str(compact_root),
                "P0_SIMULATION_SEED": row["simulation_seed"],
            }
        )
        command = ["scripts/probes/run_p0_scenario.sh", "offboard", attempt_id]
    elif adapter == "P0_DYNAMIC_CANONICAL":
        env.update(
            {
                "P0_RUN_ROOT": str(raw_root.parent.parent),
                "P0_PROCESSED_ROOT": str(compact_root),
                "P0_SIMULATION_SEED": row["simulation_seed"],
            }
        )
        command = ["scripts/probes/run_p0_scenario.sh", "external", attempt_id]
    elif adapter == "P0_EXECUTOR_CANONICAL":
        env.update(
            {
                "P0_RUN_ROOT": str(raw_root.parent.parent),
                "P0_PROCESSED_ROOT": str(compact_root),
                "P0_SIMULATION_SEED": row["simulation_seed"],
            }
        )
        command = ["scripts/probes/run_p0_scenario.sh", "executor", attempt_id]
    elif adapter == "P3_OFFBOARD_RETAINED_CANONICAL":
        env.update(
            {
                "ROUTE_EXPERIMENT_RAW_ROOT": str(raw_root),
                "ROUTE_EXPERIMENT_PROCESSED_ROOT": str(compact_root),
                "ROUTE_EXPERIMENT_SIMULATION_SEED": row["simulation_seed"],
            }
        )
        command = [
            "scripts/probes/run_p3_scenario.sh",
            "offboard",
            "on",
            "off",
            attempt_id,
        ]
    elif adapter == "P2_DYNAMIC_SIGTERM_CANONICAL":
        env.update(
            {
                "ROUTE_EXPERIMENT_RAW_ROOT": str(raw_root),
                "ROUTE_EXPERIMENT_PROCESSED_ROOT": str(compact_root),
                "ROUTE_EXPERIMENT_SIMULATION_SEED": row["simulation_seed"],
            }
        )
        command = [
            "scripts/probes/run_p2_scenario.sh",
            "external",
            "sigterm",
            attempt_id,
        ]
    elif adapter == "C1_PAIR_B_CANONICAL":
        env.update(
            {
                "C1_RUN_ID": attempt_id,
                "C1_EVENT_PAIR": "B",
                "C1_TIMING_ORDER": "A_FIRST",
                "C1_SIMULATION_SEED": row["simulation_seed"],
                "C1_RAW_ROOT": str(raw_root),
                "C1_PROCESSED_ROOT": str(compact_root),
                "ROS_DISTRO_SETUP": "/opt/ros/jazzy/setup.bash",
                "ROS_WORKSPACE_SETUP": str(ROOT / "ros2_ws/install/setup.bash"),
            }
        )
        command = ["scripts/probes/run_c1_concurrency.sh"]
    else:
        raise ContractError(f"unrecognized qualification runner adapter: {adapter}")
    return command, env


def execute_authorized(row: dict[str, str]) -> int:
    command, additions = _scenario_command(row)
    environment = os.environ.copy()
    environment.update(additions)
    process = subprocess.run(command, cwd=ROOT, env=environment)
    if process.returncode:
        return process.returncode
    # The reused scenario owns collection and Oracle invocation. These required
    # post-path records prevent an incomplete run from being treated as accepted.
    raw_root = Path(additions["V0P_RAW_ROOT"])
    compact_root = Path(additions["V0P_COMPACT_ROOT"])
    required = (
        raw_root / "safety_evidence.json",
        raw_root / "cleanup_evidence.json",
        compact_root / "compact_evidence.json",
    )
    if not all(path.is_file() for path in required):
        return EXIT_EXECUTION_FAILURE
    commands = (
        [
            sys.executable,
            "scripts/fuzzer_v0/family_a/check_v0p_safety.py",
            "--input",
            str(required[0]),
            "--output",
            str(compact_root / "safety_result.json"),
        ],
        [
            sys.executable,
            "scripts/fuzzer_v0/family_a/check_v0p_cleanup.py",
            "--input",
            str(required[1]),
            "--run-dir",
            str(raw_root.parent),
            "--output",
            str(compact_root / "cleanup_result.json"),
        ],
        [
            sys.executable,
            "scripts/fuzzer_v0/family_a/build_v0p_compact_evidence.py",
            "validate",
            "--input",
            str(required[2]),
        ],
    )
    for post_command in commands:
        result = subprocess.run(post_command, cwd=ROOT)
        if result.returncode:
            return result.returncode
    return residue_check("post-attempt", run_dir=raw_root.parent)["exit_code"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    for name in ("plan", "preflight"):
        child = subparsers.add_parser(name)
        child.add_argument("--phase", default=ALLOWED_PHASE)
        child.add_argument("--strategy", default=ALLOWED_STRATEGY)
        child.add_argument("--seed-id")
    execute = subparsers.add_parser("execute")
    execute.add_argument("--phase", required=True)
    execute.add_argument("--strategy", required=True)
    execute.add_argument("--seed-id", required=True)
    execute.add_argument("--attempt-id", required=True)
    execute.add_argument("--activation-decision", type=Path, default=DECISION_PATH)
    execute.add_argument(
        "--ledger", type=Path, default=QUALIFICATION_LEDGER_PATH
    )
    execute.add_argument("--activation-commit", required=True)
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_SCOPE_REFUSAL
    try:
        enforce_scope(
            phase=args.phase,
            strategy=args.strategy,
            seed_id=args.seed_id,
            attempt_id=getattr(args, "attempt_id", None),
        )
        if args.command == "plan":
            print(json.dumps(build_plan(args.seed_id), indent=2, sort_keys=True))
            return 0
        if args.command == "preflight":
            result = preflight()
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["status"] == "STATIC_PREFLIGHT_PASS" else EXIT_PREFLIGHT_FAILURE

        _validate_independent_authority(
            decision_path=args.activation_decision,
            ledger_path=args.ledger,
            activation_commit=args.activation_commit,
            attempt_id=args.attempt_id,
            seed_id=args.seed_id,
        )
        static = preflight()
        if static["status"] != "STATIC_PREFLIGHT_PASS":
            raise ContractError("all static preflight clauses must pass before execute")
        row = next(
            item
            for item in load_scenario_map()
            if item["attempt_id"] == args.attempt_id
        )
        return execute_authorized(row)
    except ContractError as exc:
        output = {
            "status": (
                "EXECUTE_REFUSED"
                if args.command == "execute"
                else "STATIC_REQUEST_REFUSED"
            ),
            "reason": str(exc),
            "runtime_started": False,
            "formal_attempt_registered": False,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return (
            EXIT_AUTHORITY_REFUSAL
            if args.command == "execute"
            else EXIT_SCOPE_REFUSAL
        )


if __name__ == "__main__":
    sys.exit(main())
