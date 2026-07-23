#!/usr/bin/env python3
"""Unique command entry for Family A State-Space Evaluator v0."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.fuzzer_v0.family_a import attempt_accounting
from scripts.fuzzer_v0.family_a.attempt_accounting import (
    AccountingError,
    append_event,
)
from scripts.fuzzer_v0.family_a.authorization import (
    AuthorizationError,
    verify_authorization,
)
from scripts.fuzzer_v0.family_a.check_v0p_runtime_residue import (
    evaluate as residue_check,
)
from scripts.fuzzer_v0.family_a.environment_contract import verify as verify_environment
from scripts.fuzzer_v0.family_a.execution_graph import (
    GraphError,
    execute_fixture,
    validate_graph,
)
from scripts.fuzzer_v0.family_a.strategies import (
    StrategyError,
    require_comparison_authorization,
)


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = Path(os.environ.get("FAMILY_A_AUTHORIZATION_REPO", str(ROOT)))
FAMILY = CONTRACT_ROOT / "experiments/fuzzer_v0/family_a"
READINESS = FAMILY / "full_readiness"
GRAPH = READINESS / "slot_execution_graph.yaml"
COMPONENTS = READINESS / "component_manifest.yaml"
AUTH_MANIFEST = READINESS / "authorization_identity_manifest.json"
IMAGE = "uav_sf/family-a-fuzzer-v0:jazzy-arm64"
CONTAINER_DIR = ROOT / "containers/family_a_fuzzer_v0"
EXIT_SCOPE = 2
EXIT_PREFLIGHT = 3
EXIT_AUTHORIZATION = 4
EXIT_EXECUTION = 5


class EvaluatorError(RuntimeError):
    """The evaluator request is invalid or unsafe."""


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvaluatorError(f"{path}: expected an object")
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvaluatorError(f"{path}: expected a mapping")
    return value


def _docker_prefix() -> list[str]:
    direct = subprocess.run(
        ["docker", "info"],
        capture_output=True,
    )
    if direct.returncode == 0:
        return []
    membership = subprocess.run(
        ["getent", "group", "docker"], capture_output=True, text=True
    ).stdout
    user = os.environ.get("USER", "")
    if user and user in membership:
        return ["sg", "docker", "-c"]
    raise EvaluatorError(
        "Docker daemon is unavailable; the host ROS environment was not used as a fallback"
    )


def _docker_run(command: list[str], *, capture: bool = False) -> int:
    prefix = _docker_prefix()
    if prefix:
        shell_command = shlex.join(command)
        process = subprocess.run(
            [*prefix, shell_command],
            cwd=ROOT,
            capture_output=capture,
            text=capture,
        )
    else:
        process = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=capture,
            text=capture,
        )
    if capture:
        sys.stdout.write(process.stdout)
        sys.stderr.write(process.stderr)
    return process.returncode


def env_build() -> int:
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    if status:
        raise EvaluatorError(
            "env-build requires a committed clean source identity; commit first"
        )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    origin = subprocess.run(
        ["git", "rev-parse", "origin/main"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if head != origin:
        raise EvaluatorError("env-build requires HEAD == origin/main")
    output_root = ROOT / "runs/fuzzer_v0/family_a/environment"
    output_root.mkdir(parents=True, exist_ok=True)
    metadata = output_root / "build-metadata.json"
    log = output_root / "build.log"
    command = [
        "docker",
        "buildx",
        "bake",
        "--file",
        str(CONTAINER_DIR / "docker-bake.hcl"),
        "--load",
        "--metadata-file",
        str(metadata),
        "qualification",
    ]
    prefix = _docker_prefix()
    selected = [*prefix, shlex.join(command)] if prefix else command
    with log.open("w", encoding="utf-8") as handle:
        process = subprocess.Popen(
            selected,
            cwd=ROOT,
            env={**os.environ, "REPOSITORY_COMMIT": head},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            handle.write(line)
        code = process.wait()
    if code:
        return code
    inspect = ["docker", "image", "inspect", IMAGE]
    return _docker_run(inspect, capture=True)


def _container_dispatch(args: list[str], *, writable_repository: bool = False) -> int:
    repository_mode = "rw" if writable_repository else "ro"
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--ipc",
        "private",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=1g",
        "--mount",
        f"type=bind,src={ROOT},dst=/authorization/repository,{repository_mode}",
    ]
    if writable_repository:
        command.remove("--read-only")
    if args and args[0] in {"execute", "close"}:
        attempt_root = ROOT / "runs/fuzzer_v0/family_a/v0p"
        attempt_root.mkdir(parents=True, exist_ok=True)
        command.extend(
            [
                "--mount",
                f"type=bind,src={attempt_root},dst=/attempts,rw",
            ]
        )
    command.extend(
        [
            IMAGE,
            "python3",
            "/opt/family_a/repository/scripts/fuzzer_v0/family_a/state_space_evaluator.py",
            "--inside-container",
            *args,
        ]
    )
    return _docker_run(command)


def build_plan(seed_id: str | None = None) -> dict[str, Any]:
    validate_graph(GRAPH, COMPONENTS)
    graph = _load_yaml(GRAPH)
    slots = graph["slots"]
    if seed_id is not None:
        slots = [slot for slot in slots if slot["seed_id"] == seed_id]
        if not slots:
            raise EvaluatorError("seed is not one of the six frozen qualification slots")
    return {
        "schema_version": "1.0",
        "status": "STATIC_PLAN_PASS",
        "phase": "V0_P_QUALIFICATION",
        "strategy": "QUALIFICATION",
        "slot_count": len(slots),
        "node_count_per_slot": len(graph["pipeline"]),
        "qualification_target_accepted": 3,
        "qualification_maximum_formal_attempts": 6,
        "comparison_arms_reachable": False,
        "runtime_started": False,
        "slots": slots,
    }


def preflight(*, require_clean: bool = True) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    try:
        graph = validate_graph(GRAPH, COMPONENTS)
        checks["six_slot_graph"] = {"status": "PASS", **graph}
    except GraphError as exc:
        checks["six_slot_graph"] = {"status": "FAIL", "reason": str(exc)}

    seed_rows = (
        FAMILY / "seed_catalog.tsv"
    ).read_text(encoding="utf-8").splitlines()[1:]
    accepted = sum("\tACCEPTED_RUNTIME_SEED\t" in f"\t{row}\t" for row in seed_rows)
    historical = sum("\tACCEPTED_REPLAY_BENCHMARK\t" in f"\t{row}\t" for row in seed_rows)
    excluded = sum("\tEXCLUDED\t" in f"\t{row}\t" for row in seed_rows)
    seed_ok = len(seed_rows) == 61 and accepted == 50 and historical == 1 and excluded == 10
    checks["frozen_seed_accounting"] = {
        "status": "PASS" if seed_ok else "FAIL",
        "rows": len(seed_rows),
        "accepted_current": accepted,
        "historical_replay": historical,
        "excluded": excluded,
    }

    ledger = _load_yaml(FAMILY / "attempt_ledger.yaml")
    ledger_ok = (
        ledger.get("formal_attempts") == 0
        and ledger.get("qualification_attempts") == 0
        and all(int(value) == 0 for value in ledger.get("strategy_counts", {}).values())
        and ledger.get("attempts") == []
    )
    checks["frozen_attempt_ledger"] = {
        "status": "PASS" if ledger_ok else "FAIL",
        "formal_attempts": ledger.get("formal_attempts"),
        "qualification_attempts": ledger.get("qualification_attempts"),
    }

    residue = residue_check("preflight")
    checks["process_port_audit"] = {
        "status": "PASS" if residue["status"] == "CLEAN" else "FAIL",
        "observed": residue["status"],
        "processes": residue["processes"],
        "occupied_ports": residue["occupied_ports"],
    }

    if os.getenv("FAMILY_A_FORMAL_CONTAINER") == "1":
        environment = verify_environment(CONTRACT_ROOT)
        checks["locked_container"] = {
            "status": environment["status"],
            "failed_checks": environment["failed_checks"],
        }
    else:
        checks["locked_container"] = {
            "status": "PASS",
            "observed": "HOST_STATIC_ONLY_CONTAINER_CHECK_DEFERRED_TO_WRAPPER",
        }

    worktree = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=CONTRACT_ROOT,
        capture_output=True,
        text=True,
    ).stdout
    checks["worktree"] = {
        "status": "PASS" if not worktree or not require_clean else "FAIL",
        "clean": not bool(worktree),
        "required": require_clean,
    }
    passed = all(record["status"] == "PASS" for record in checks.values())
    return {
        "schema_version": "1.0",
        "status": "STATIC_PREFLIGHT_PASS" if passed else "STATIC_PREFLIGHT_FAIL",
        "checks": checks,
        "runtime_started": False,
        "formal_attempt_registered": False,
        "flight_communication_started": False,
    }


def status() -> dict[str, Any]:
    decision_candidates = [
        READINESS / "qualification_activation_decision.json",
        FAMILY / "activation_rereview/qualification_activation_decision.json",
    ]
    decision = next(
        (_load_json(path) for path in decision_candidates if path.is_file()), {}
    )
    return {
        "schema_version": "1.0",
        "environment": (
            "LOCKED_CONTAINER_READY"
            if (READINESS / "full_environment_lock.yaml").is_file()
            else "IMPLEMENTATION_IN_PROGRESS"
        ),
        "qualification": decision.get("status", "QUALIFICATION_NOT_AUTHORIZED"),
        "decision": decision.get("decision", "DECLINE_IMPLEMENTATION_NOT_READY"),
        "formal_attempts": decision.get("current_formal_attempts", 0),
        "accepted_attempts": decision.get("current_accepted_attempts", 0),
        "next_attempt_id": decision.get("next_attempt_id", "V0P-A1"),
        "comparison_arms": "IMPLEMENTED_STATICALLY_LOCKED_NOT_AUTHORIZED",
        "runtime_started": False,
    }


def _registration_path(attempt_id: str) -> Path:
    return (
        FAMILY
        / "qualification_attempts"
        / attempt_id
        / "registration.json"
    )


def register(args: argparse.Namespace) -> dict[str, Any]:
    if os.getenv("FAMILY_A_FORMAL_CONTAINER") != "1":
        raise EvaluatorError("formal registration must run in the locked container")
    state = verify_authorization(
        repo=CONTRACT_ROOT,
        manifest_path=AUTH_MANIFEST,
        authorization_commit=args.authorization_commit,
    )
    plan = build_plan()
    slot = next(
        (
            item
            for item in plan["slots"]
            if item["attempt_id"] == args.attempt_id
            and item["slot_id"] == args.slot_id
            and item["seed_id"] == args.seed_id
        ),
        None,
    )
    if slot is None or state.next_attempt_id != args.attempt_id:
        raise EvaluatorError("registration does not match the fixed next slot")
    path = _registration_path(args.attempt_id)
    if path.exists():
        raise EvaluatorError("attempt registration already exists and cannot be overwritten")
    path.parent.mkdir(parents=True, exist_ok=False)
    record = {
        "schema_version": "1.0",
        "status": "REGISTERED_PRELAUNCH_PENDING_PUSH",
        "attempt_id": args.attempt_id,
        "slot_id": args.slot_id,
        "seed_id": args.seed_id,
        "repository_commit": state.repository_commit,
        "authorization_commit": state.authorization_commit,
        "formal_runtime_started": False,
    }
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        **record,
        "registration_path": str(path.relative_to(CONTRACT_ROOT)),
        "next_action": "commit and push this exact registration before execute",
    }


def _formal_execute(args: argparse.Namespace) -> dict[str, Any]:
    if os.getenv("FAMILY_A_QUALIFICATION_TASK_ACK") != "V0_P_QUALIFICATION_ONLY":
        raise EvaluatorError(
            "execute requires a separate qualification task acknowledgement"
        )
    registration = _registration_path(args.attempt_id)
    state = verify_authorization(
        repo=CONTRACT_ROOT,
        manifest_path=AUTH_MANIFEST,
        authorization_commit=args.authorization_commit,
        require_registration_commit=args.registration_commit,
        registration_path=registration,
    )
    plan = build_plan()
    slot = next(
        (
            item
            for item in plan["slots"]
            if item["attempt_id"] == args.attempt_id
            and item["slot_id"] == args.slot_id
            and item["seed_id"] == args.seed_id
        ),
        None,
    )
    if slot is None:
        raise EvaluatorError("execute request differs from fixed qualification slot")
    attempt_root = Path("/attempts") / args.attempt_id
    if attempt_root.exists():
        raise EvaluatorError("attempt output already exists and cannot be overwritten")
    # Import only after every no-runtime gate has passed.
    from scripts.fuzzer_v0.family_a.formal_orchestrator import execute

    return execute(
        slot=slot,
        attempt_root=attempt_root,
        repository_commit=state.repository_commit,
        authorization_commit=state.authorization_commit,
        registration_commit=args.registration_commit,
    )


def fixture_register(root: Path, slot_id: str) -> dict[str, Any]:
    stream = root / slot_id / "events.jsonl"
    commit = "a" * 40
    event = append_event(
        stream,
        attempt_id=f"FIXTURE-{slot_id}",
        slot_id=slot_id,
        seed_id="FIXTURE_SEED",
        event_type="REGISTERED_PRELAUNCH",
        repository_commit=commit,
        authorization_commit="b" * 40,
        registration_commit="c" * 40,
        payload={"fixture": True},
        allow_fixture=True,
        timestamp="2026-07-23T00:00:00.000000Z",
    )
    return {"status": "PASS", "event": event, "path": str(stream), "runtime_started": False}


def fixture_close(root: Path, slot_id: str) -> dict[str, Any]:
    stream = root / slot_id / "events.jsonl"
    commit = "a" * 40
    for index, event_type in enumerate(
        (
            "AUTHORIZATION_VERIFIED",
            "PREFLIGHT_PASSED",
            "LAUNCH_STARTED",
            "SCENARIO_COMPLETED",
            "COLLECTION_CLOSED",
            "ORACLES_COMPLETED",
            "CLEANUP_COMPLETED",
            "CLASSIFIED",
            "CLOSED",
        ),
        1,
    ):
        append_event(
            stream,
            attempt_id=f"FIXTURE-{slot_id}",
            slot_id=slot_id,
            seed_id="FIXTURE_SEED",
            event_type=event_type,
            repository_commit=commit,
            authorization_commit="b" * 40,
            registration_commit="c" * 40,
            payload={"fixture": True, "step": event_type},
            allow_fixture=True,
            timestamp=f"2026-07-23T00:00:{index:02d}.000000Z",
        )
    result = attempt_accounting.aggregate([stream], allow_fixture=True)
    return {"status": "PASS", **result, "runtime_started": False}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", action="store_true")
    parser.add_argument("--inside-container", action="store_true", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("env-build")
    sub.add_parser("env-verify")
    plan = sub.add_parser("plan")
    plan.add_argument("--seed-id")
    preflight_parser = sub.add_parser("preflight")
    preflight_parser.add_argument("--allow-dirty-static", action="store_true")
    register_parser = sub.add_parser("register")
    for item in (register_parser,):
        item.add_argument("--attempt-id", required=True)
        item.add_argument("--slot-id", required=True)
        item.add_argument("--seed-id", required=True)
        item.add_argument("--authorization-commit", required=True)
    execute_parser = sub.add_parser("execute")
    execute_parser.add_argument("--attempt-id", required=True)
    execute_parser.add_argument("--slot-id", required=True)
    execute_parser.add_argument("--seed-id", required=True)
    execute_parser.add_argument("--authorization-commit", required=True)
    execute_parser.add_argument("--registration-commit", required=True)
    execute_parser.add_argument(
        "--qualification-task-ack",
        choices=("V0_P_QUALIFICATION_ONLY",),
    )
    close_parser = sub.add_parser("close")
    close_parser.add_argument("--attempt-id", required=True)
    sub.add_parser("review")
    sub.add_parser("status")
    fixture_reg = sub.add_parser("fixture-register")
    fixture_reg.add_argument("--root", type=Path)
    fixture_reg.add_argument("--slot-id", default="V0P-S1")
    fixture_refusal = sub.add_parser("fixture-execute-refusal")
    fixture_refusal.add_argument(
        "--strategy", default="OFFICIAL_SEQUENCE", choices=(
            "OFFICIAL_SEQUENCE",
            "BOUNDED_RANDOM_TIMING_COMPARATOR",
            "STATE_AWARE_MUTATION",
        )
    )
    fixture_close_parser = sub.add_parser("fixture-close")
    fixture_close_parser.add_argument("--root", type=Path)
    fixture_close_parser.add_argument("--slot-id", default="V0P-S1")
    fixture_graph = sub.add_parser("fixture-graph")
    fixture_graph.add_argument("--root", type=Path)
    fixture_graph.add_argument("--slot-id", default="V0P-S1")
    fixture_graph.add_argument("--fail-node")
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_SCOPE
    try:
        if args.container and not args.inside_container:
            if args.command == "env-build":
                return env_build()
            forwarded = sys.argv[1:]
            forwarded.remove("--container")
            writable = args.command in {"register", "close"}
            return _container_dispatch(forwarded, writable_repository=writable)
        if args.command == "env-build":
            if args.inside_container:
                raise EvaluatorError("env-build is a host Docker/BuildKit command")
            return env_build()
        if not args.inside_container and args.command in {
            "env-verify",
            "register",
            "execute",
            "close",
        }:
            raise EvaluatorError("this command requires --container")
        if args.command == "env-verify":
            result = verify_environment(CONTRACT_ROOT)
        elif args.command == "plan":
            result = build_plan(args.seed_id)
        elif args.command == "preflight":
            result = preflight(require_clean=not args.allow_dirty_static)
        elif args.command == "status":
            result = status()
        elif args.command == "register":
            result = register(args)
        elif args.command == "execute":
            if args.qualification_task_ack:
                os.environ["FAMILY_A_QUALIFICATION_TASK_ACK"] = (
                    args.qualification_task_ack
                )
            result = _formal_execute(args)
        elif args.command == "close":
            raise EvaluatorError(
                "formal close is performed by the orchestrator after classification; "
                "manual close cannot bypass the event chain"
            )
        elif args.command == "review":
            process = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/validation/check_family_a_fuzzer_v0_full_readiness.py"),
                ],
                cwd=CONTRACT_ROOT,
            )
            return process.returncode
        elif args.command in {"fixture-register", "fixture-close", "fixture-graph"}:
            root = args.root or Path(
                tempfile.mkdtemp(prefix="family-a-fixture-")
            )
            if args.command == "fixture-register":
                result = fixture_register(root, args.slot_id)
            elif args.command == "fixture-close":
                result = fixture_close(root, args.slot_id)
            else:
                result = execute_fixture(
                    slot_id=args.slot_id,
                    root=root,
                    fail_node=args.fail_node,
                    graph_path=GRAPH,
                    component_path=COMPONENTS,
                )
        elif args.command == "fixture-execute-refusal":
            decision = {
                "authorized_scope": "V0_P_QUALIFICATION_ONLY",
                "comparison_runtime_authorized": False,
            }
            try:
                require_comparison_authorization(decision, args.strategy)
            except StrategyError as exc:
                result = {
                    "status": "EXECUTE_REFUSED",
                    "reason": str(exc),
                    "runtime_started": False,
                }
            else:
                raise EvaluatorError("comparison strategy refusal unexpectedly passed")
        else:
            raise EvaluatorError(f"unsupported command: {args.command}")
        print(json.dumps(result, indent=2, sort_keys=True))
        if result.get("status") in {
            "FAIL",
            "STATIC_PREFLIGHT_FAIL",
        }:
            return EXIT_PREFLIGHT
        return 0
    except (EvaluatorError, AuthorizationError, AccountingError, GraphError) as exc:
        print(
            json.dumps(
                {
                    "status": (
                        "EXECUTE_REFUSED"
                        if args.command in {"register", "execute", "close"}
                        else "REQUEST_REFUSED"
                    ),
                    "reason": str(exc),
                    "runtime_started": False,
                    "formal_attempt_registered": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return (
            EXIT_AUTHORIZATION
            if args.command in {"register", "execute", "close"}
            else EXIT_SCOPE
        )


if __name__ == "__main__":
    sys.exit(main())
