#!/usr/bin/env python3
"""Create one exact Family A plan from a retained environment attestation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.evaluator.plan import validate_plan


ROOT = Path(__file__).resolve().parents[2]
OWNERS = {
    "legacy_offboard": ("family_a_offboard_controller", "none"),
    "dynamic_external_mode": ("family_a_external_mode", "none"),
    "mode_executor": ("family_a_mode_executor", "family_a_mode_executor"),
}
BASE_REQUIRED_EVENTS = [
    "collection_started",
    "environment_attested",
    "revocation",
    "activation",
    "command_consumed",
    "controller_output",
    "allocator_output",
    "actuator_write",
    "collection_stopped",
]


class PlanCreationError(ValueError):
    """The retained identity cannot support the requested plan."""


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PlanCreationError(f"JSON root is not an object: {path}")
    return value


def create_plan(
    *,
    attestation: dict[str, Any],
    run_id: str,
    plan_id: str,
    source_route: str,
    target_route: str,
    expected_successor: str,
    expected_fallback: str,
    target_activation_expected: bool,
    registration_rejection_expected: bool,
    activation_rejection_expected: bool,
    completion_expected: bool,
    fault_expected: bool,
    fallback_expected: bool,
    thresholds: dict[str, Any],
    strategy: str = "official_sequence",
    seed: int | None = None,
) -> dict[str, Any]:
    try:
        candidate = attestation["attestation_payload"]["container"]["candidate"]
        environment = attestation["execution_environment"]
        lifecycle_owner, executor_owner = OWNERS[target_route]
        dependency_digest = candidate["locks"]["dependencies"]
        repository_revision = candidate["repository_revision"]
    except (KeyError, TypeError) as exc:
        raise PlanCreationError("attestation lacks a frozen candidate identity") from exc
    required = [*BASE_REQUIRED_EVENTS[:2], BASE_REQUIRED_EVENTS[-1]]
    if target_activation_expected:
        required.extend(["transition_requested", *BASE_REQUIRED_EVENTS[2:-1]])
    if activation_rejection_expected:
        required.append("activation_requested")
    if registration_rejection_expected:
        required.append("registration")
    if completion_expected:
        required.append("completion")
    if fault_expected:
        required.append("fault_detected")
    if fallback_expected:
        required.append("fallback_triggered")
    plan = {
        "schema_version": "1.1",
        "plan_id": plan_id,
        "run_id": run_id,
        "strategy": {
            "name": strategy,
            "seed": seed,
            "timing_bounds_ns": {},
        },
        "transition": {
            "source_route": source_route,
            "target_route": target_route,
            "expected_successor": expected_successor,
            "expected_fallback": expected_fallback,
            "expected_lifecycle_owner": lifecycle_owner,
            "expected_executor_owner": executor_owner,
            "target_activation_expected": target_activation_expected,
            "registration_rejection_expected": registration_rejection_expected,
            "activation_rejection_expected": activation_rejection_expected,
            "completion_expected": completion_expected,
            "fault_expected": fault_expected,
            "fallback_expected": fallback_expected,
        },
        "thresholds": thresholds,
        "required_event_kinds": required,
        "source_identity": {
            "repository_commit": repository_revision,
            "dependency_lock_digest": dependency_digest,
        },
        "execution_environment": environment,
        "cleanup": {
            "require_landed": True,
            "require_disarmed": True,
            "safe_terminal_routes": ["internal_land", "internal_recovery"],
        },
    }
    validate_plan(plan)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--plan-id", required=True)
    parser.add_argument(
        "--source-route", choices=["px4_internal", "internal_hold", "internal_rtl"], required=True
    )
    parser.add_argument("--target-route", choices=sorted(OWNERS), required=True)
    parser.add_argument(
        "--expected-successor",
        choices=["internal_hold", "internal_rtl", "internal_land"],
        required=True,
    )
    parser.add_argument(
        "--expected-fallback",
        choices=["internal_hold", "internal_rtl", "internal_land", "internal_recovery"],
        default="internal_land",
    )
    parser.add_argument("--completion-expected", action="store_true")
    parser.add_argument("--fault-expected", action="store_true")
    parser.add_argument("--fallback-expected", action="store_true")
    parser.add_argument("--registration-rejection-expected", action="store_true")
    parser.add_argument("--activation-rejection-expected", action="store_true")
    parser.add_argument(
        "--target-activation-expected",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--strategy",
        choices=["official_sequence", "bounded_random_timing", "state_aware"],
        default="official_sequence",
    )
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=ROOT / "config/method.defaults.json",
    )
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise PlanCreationError(f"refusing to overwrite: {args.output}")
        attestation = _read_object(args.attestation)
        threshold_document = _read_object(args.thresholds)
        thresholds = threshold_document.get("thresholds", threshold_document)
        if not isinstance(thresholds, dict):
            raise PlanCreationError("threshold document lacks a thresholds object")
        plan = create_plan(
            attestation=attestation,
            run_id=args.run_id,
            plan_id=args.plan_id,
            source_route=args.source_route,
            target_route=args.target_route,
            expected_successor=args.expected_successor,
            expected_fallback=args.expected_fallback,
            target_activation_expected=args.target_activation_expected,
            registration_rejection_expected=args.registration_rejection_expected,
            activation_rejection_expected=args.activation_rejection_expected,
            completion_expected=args.completion_expected,
            fault_expected=args.fault_expected,
            fallback_expected=args.fallback_expected,
            thresholds=thresholds,
            strategy=args.strategy,
            seed=args.seed,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "PASS", "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
