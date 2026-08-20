#!/usr/bin/env python3
"""Run or process one explicitly non-formal Thor qualification attempt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.corpus.core_actions import live_profile
from scripts.runtime.live_strategy_backend import (
    CONTRACTS,
    create_corpus_decision,
    create_live_decision,
)
from scripts.runtime.make_plan import create_plan


class QualificationError(RuntimeError):
    """The qualification attempt cannot be started without ambiguity."""


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QualificationError(f"JSON root is not an object: {path}")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise QualificationError(f"qualification artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    phase = getattr(args, "phase", "all")
    if phase not in {"live", "process", "all"}:
        raise QualificationError("unsupported qualification phase")
    attestation = _read(args.attestation)
    environment_path = args.run_root / args.study_id / "environment.json"
    if environment_path.exists():
        if _digest(environment_path) != _digest(args.attestation):
            raise QualificationError("qualification environment identity changed")
    else:
        environment_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.attestation, environment_path)
    plan_path = args.run_root / args.study_id / "plans" / f"{args.run_id}.json"
    decision_path = (
        args.run_root / args.study_id / "strategy-decisions" / f"{args.run_id}.json"
    )
    image_id = attestation["attestation_payload"]["container"]["image_id"]
    launch_returncode = -1
    if phase == "process":
        if not plan_path.is_file():
            raise QualificationError(f"qualification plan is missing: {plan_path}")
        driver_path = args.run_root / args.study_id / args.run_id / "container-driver.result.json"
        if driver_path.is_file():
            launch_returncode = int(_read(driver_path).get("returncode", -1))
    else:
        thresholds_document = _read(args.thresholds)
        thresholds = thresholds_document.get("thresholds", thresholds_document)
        timing_bounds: dict[str, list[int]] = {}
        if args.manual_land_offset_s is not None:
            expected_ns = int(
                (args.active_s + args.manual_land_offset_s) * 1_000_000_000
            )
            tolerance_ns = 100_000_000
            timing_bounds["adjacent_after_activation_ns"] = [
                max(0, expected_ns - tolerance_ns),
                expected_ns + tolerance_ns,
            ]
            if args.manual_land_offset_s < 0:
                timing_bounds["adjacent_before_completion_ns"] = [
                    100_000_000,
                    400_000_000,
                ]
            elif args.manual_land_offset_s > 0:
                timing_bounds["completion_before_adjacent_ns"] = [
                    100_000_000,
                    400_000_000,
                ]
            else:
                timing_bounds["adjacent_completion_distance_ns"] = [0, 100_000_000]
        timing_bounds.update(args.timing_bounds_ns)
        corpus = tuple(getattr(args, "corpus", None) or ())
        corpus_decision = None
        if corpus:
            # The action is selected before the flight, so the flight must be
            # launched to perform exactly that action and the plan must carry
            # exactly that action's obligations.
            corpus_decision = create_corpus_decision(
                strategy=args.strategy,
                seed=args.strategy_seed,
                mechanism=args.mechanism,
                corpus=corpus,
                timing_bounds_ns=args.timing_bounds_ns,
                official_action=str(args.official_action),
                official_offset_ns=int(args.stall_after_s * 1_000_000_000),
                covered_units=set(args.covered_boundary),
            )
            profile = live_profile(str(corpus_decision["action"]))
            args.fault_mode = profile.fault_mode
            args.repeat_count = profile.repeat_count
            args.target_activation_count = profile.activation_count
            args.scheduled_action = str(corpus_decision["action"])
            args.completion_expected = profile.completion_expected
            args.fault_expected = profile.fault_expected
            args.fallback_expected = profile.fallback_expected
            args.registration_rejection_expected = profile.registration_rejection_expected
            # The extra components are refused by design, so their nonzero exit
            # must be expected rather than read as an environment failure.
            args.duplicate_registration = profile.registration_rejection_expected
            if isinstance(args.workload, dict):
                args.workload = {
                    **args.workload,
                    "phases": list(profile.workload_phases),
                }
        plan = create_plan(
            attestation=attestation,
            run_id=args.run_id,
            plan_id=f"{args.run_id}-qualification-plan",
            source_route=args.source_route,
            target_route=args.mechanism,
            expected_successor=args.successor_route,
            expected_fallback=args.expected_fallback,
            target_activation_expected=args.target_activation_expected,
            registration_rejection_expected=args.registration_rejection_expected,
            activation_rejection_expected=args.activation_rejection_expected,
            completion_expected=args.completion_expected,
            fault_expected=args.fault_expected,
            fallback_expected=args.fallback_expected,
            thresholds=thresholds,
            simulation_seed=args.simulation_seed,
            strategy=args.strategy,
            seed=args.strategy_seed,
            timing_bounds_ns=timing_bounds,
            target_activation_count=[
                args.target_activation_count
                if args.target_activation_count is not None
                else (args.repeat_count if args.target_activation_expected else 0),
                args.target_activation_count
                if args.target_activation_count is not None
                else (args.repeat_count if args.target_activation_expected else 0),
            ],
            workload=args.workload,
        )
        if plan_path.exists():
            raise QualificationError(f"qualification plan already exists: {plan_path}")
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if corpus_decision is not None:
            _write_new(decision_path, corpus_decision)
        elif args.live_strategy_backend is not None:
            if args.live_strategy_backend not in CONTRACTS:
                raise QualificationError("unsupported qualification live strategy backend")
            decision = create_live_decision(
                strategy=args.strategy,
                seed=args.strategy_seed,
                timing_bounds_ns=timing_bounds,
                official_offset_ns=int(args.stall_after_s * 1_000_000_000),
                covered_boundaries=set(args.covered_boundary),
                backend=args.live_strategy_backend,
            )
            _write_new(decision_path, decision)
        launch = [
            sys.executable,
            "-m",
            "scripts.runtime.run_container",
            "--image",
            args.image,
            "--expected-image-id",
            image_id,
            "--run-root",
            str(args.run_root),
            "--study-id",
            args.study_id,
            "--run-id",
            args.run_id,
            "--mechanism",
            args.mechanism,
            "--source-route",
            args.source_route,
            "--setpoint-kind",
            args.setpoint_kind,
            "--fault-mode",
            args.fault_mode,
            "--successor-route",
            args.successor_route,
            "--repeat-count",
            str(args.repeat_count),
            "--scheduled-action",
            str(getattr(args, "scheduled_action", "") or ""),
            "--slot",
            str(args.slot),
            "--cpu-set",
            args.cpu_set,
            "--memory",
            args.memory,
            "--active-s",
            str(args.active_s),
            "--stall-after-s",
            str(args.stall_after_s),
            "--workload-profile",
            args.workload_profile,
            "--motion-settle-s",
            str(args.motion_settle_s),
            "--motion-speed-m-s",
            str(args.motion_speed_m_s),
            "--motion-distance-m",
            str(args.motion_distance_m),
            "--motion-entry-progress-m",
            str(args.motion_entry_progress_m),
            "--motion-completion-progress-m",
            str(args.motion_completion_progress_m),
            "--simulation-seed",
            str(args.simulation_seed),
            "--attempt-timeout-s",
            str(args.attempt_timeout_s),
            "--outer-timeout-s",
            str(args.outer_timeout_s),
            "--safety-limits",
            args.safety_limits,
        ]
        if corpus_decision is not None or args.live_strategy_backend is not None:
            launch.extend(["--strategy-decision", str(decision_path)])
        if args.health_loss:
            launch.append("--health-loss")
        if args.duplicate_registration:
            launch.append("--duplicate-registration")
        if args.manual_land_offset_s is not None:
            launch.extend(["--manual-land-offset-s", str(args.manual_land_offset_s)])
        launch_result = subprocess.run(
            launch, text=True, capture_output=True, check=False
        )
        launch_returncode = launch_result.returncode
        if phase == "live":
            return {
                "schema_version": "1.0",
                "study_id": args.study_id,
                "attempt_id": args.run_id,
                "phase": "LIVE_COMPLETE",
                "runtime_driver_returncode": launch_returncode,
                "runtime_result_present": (
                    args.run_root / args.study_id / args.run_id / "runtime_result.json"
                ).is_file(),
            }

    process = [
        "docker",
        "run",
        "--rm",
        "--runtime",
        "runc",
        "--network",
        "none",
        "--read-only",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--mount",
        f"type=bind,src={args.run_root.resolve()},dst=/runs",
        args.image,
        "python3",
        "-m",
        "scripts.runtime.process_attempt",
        "--attempt-root",
        f"/runs/{args.study_id}/{args.run_id}",
        "--plan",
        f"/runs/{args.study_id}/plans/{args.run_id}.json",
        "--environment",
        f"/runs/{args.study_id}/environment.json",
        "--maximum-clock-uncertainty-ns",
        str(args.maximum_clock_uncertainty_ns),
    ]
    process_result = subprocess.run(process, text=True, capture_output=True, check=False)
    result_path = args.run_root / args.study_id / args.run_id / "processing_result.json"
    if not result_path.is_file():
        raise QualificationError(
            "attempt processing did not close: "
            + (process_result.stderr.strip() or process_result.stdout.strip())
        )
    result = _read(result_path)
    result["execution_model"] = (
        "two_phase_barrier" if phase == "process" else "single_attempt"
    )
    result["launch_driver_returncode"] = launch_returncode
    result["processing_driver_returncode"] = process_result.returncode
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, default=Path("runs"))
    parser.add_argument("--study-id", default="thor-qualification-current")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--phase", choices=["live", "process", "all"], default="all")
    parser.add_argument(
        "--mechanism",
        choices=["legacy_offboard", "dynamic_external_mode", "mode_executor"],
        required=True,
    )
    parser.add_argument(
        "--source-route",
        choices=["px4_internal", "internal_hold", "internal_rtl"],
        required=True,
    )
    parser.add_argument(
        "--successor-route",
        choices=["internal_hold", "internal_rtl", "internal_land"],
        default="internal_land",
    )
    parser.add_argument(
        "--expected-fallback",
        choices=["internal_hold", "internal_rtl", "internal_land", "internal_recovery"],
        default="internal_land",
    )
    parser.add_argument(
        "--setpoint-kind", choices=["trajectory", "attitude", "body_rate"], default="trajectory"
    )
    parser.add_argument(
        "--fault-mode", choices=["normal", "process_exit", "setpoint_stall"], default="normal"
    )
    parser.add_argument("--health-loss", action="store_true")
    parser.add_argument("--duplicate-registration", action="store_true")
    parser.add_argument("--repeat-count", type=int, default=1)
    parser.add_argument("--target-activation-count", type=int)
    parser.add_argument("--manual-land-offset-s", type=float)
    parser.add_argument(
        "--target-activation-expected", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--registration-rejection-expected", action="store_true")
    parser.add_argument("--activation-rejection-expected", action="store_true")
    parser.add_argument("--completion-expected", action="store_true")
    parser.add_argument("--fault-expected", action="store_true")
    parser.add_argument("--fallback-expected", action="store_true")
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--cpu-set", default="0-13")
    parser.add_argument("--memory", default="24g")
    parser.add_argument("--active-s", type=float, default=8.0)
    parser.add_argument("--stall-after-s", type=float, default=5.0)
    parser.add_argument("--workload-profile", choices=["hover", "straight_line"], default="hover")
    parser.add_argument("--motion-settle-s", type=float, default=1.0)
    parser.add_argument("--motion-speed-m-s", type=float, default=0.75)
    parser.add_argument("--motion-distance-m", type=float, default=3.5)
    parser.add_argument("--motion-entry-progress-m", type=float, default=0.75)
    parser.add_argument("--motion-completion-progress-m", type=float, default=2.5)
    parser.add_argument("--simulation-seed", type=int, required=True)
    parser.add_argument("--attempt-timeout-s", type=float, default=90.0)
    parser.add_argument("--outer-timeout-s", type=float, default=160.0)
    parser.add_argument(
        "--thresholds", type=Path, default=Path("config/method.defaults.json")
    )
    parser.add_argument("--safety-limits", default="/opt/uav_sf/config/safety_limits.qualification.json")
    parser.add_argument(
        "--strategy",
        choices=["official_sequence", "bounded_random_timing", "state_aware"],
        default="official_sequence",
    )
    parser.add_argument("--strategy-seed", type=int)
    parser.add_argument("--live-strategy-backend", choices=sorted(CONTRACTS))
    parser.add_argument("--corpus", action="append", default=[])
    parser.add_argument("--official-action")
    parser.add_argument("--covered-boundary", action="append", default=[])
    parser.set_defaults(timing_bounds_ns={}, workload=None)
    parser.add_argument("--maximum-clock-uncertainty-ns", type=int, default=20_000_000)
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, ValueError, KeyError, QualificationError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["outcome"] == "ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
