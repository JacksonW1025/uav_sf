#!/usr/bin/env python3
"""Run or close one preregistered formal Family A attempt."""

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

from scripts.accounting.study import StudyLedger, verify_study_ledger
from scripts.evaluator.plan import validate_plan
from scripts.runtime.make_plan import create_plan
from scripts.runtime.run_campaign import CampaignError, attempt_cell, validate_matrix


ROOT = Path(__file__).resolve().parents[2]


class FormalAttemptError(RuntimeError):
    """A formal attempt cannot be started or unambiguously closed."""


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FormalAttemptError(f"JSON root is not an object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _write_new(path: Path, value: Any) -> None:
    if path.exists():
        raise FormalAttemptError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _cell(matrix: dict[str, Any], attempt_id: str) -> dict[str, Any]:
    try:
        return attempt_cell(matrix, attempt_id)
    except CampaignError as exc:
        raise FormalAttemptError(str(exc)) from exc


def _preflight(image: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--runtime",
            "runc",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec",
            image,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FormalAttemptError("formal image preflight returned invalid JSON") from exc
    if result.returncode != 0 or value.get("status") != "PASS":
        raise FormalAttemptError("formal image preflight failed")
    return value


def _compact_evidence(attempt_root: Path, output_root: Path) -> dict[str, str]:
    derived = attempt_root / "derived"
    sources = {
        "raw_manifest": derived / "raw-evidence.manifest.json",
        "ulog_summary": derived / "ulog-summary.json",
        "evaluation": derived / "evaluation.json",
        "processing_result": attempt_root / "processing_result.json",
        "runtime_result": attempt_root / "runtime_result.json",
        "container_driver_result": attempt_root / "container-driver.result.json",
    }
    retained: dict[str, str] = {}
    for label, source in sources.items():
        if not source.is_file():
            continue
        target = output_root / f"{label.replace('_', '-')}.json"
        if target.exists():
            raise FormalAttemptError(f"compact evidence already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        retained[label] = _sha256(target)
    return retained


def run(args: argparse.Namespace) -> dict[str, Any]:
    phase = getattr(args, "phase", "all")
    if phase not in {"live", "finalize", "all"}:
        raise FormalAttemptError("unsupported formal attempt phase")
    matrix = _read_object(args.matrix)
    attestation = _read_object(args.attestation)
    if matrix.get("schema_version") != "1.0":
        raise FormalAttemptError("unsupported matrix schema")
    try:
        validate_matrix(matrix)
    except CampaignError as exc:
        raise FormalAttemptError(str(exc)) from exc
    study_id = str(matrix.get("study_id", ""))
    cell = _cell(matrix, args.attempt_id)
    cell_id = str(cell["cell_id"])
    runtime = cell["runtime"]
    try:
        attempt_ordinal = int(args.attempt_id.rsplit("-", 1)[1])
        simulation_seed = int(runtime["simulation_seed_base"]) + attempt_ordinal
    except (IndexError, TypeError, ValueError) as exc:
        raise FormalAttemptError("formal simulation seed cannot be derived") from exc
    image_id = str(
        attestation["attestation_payload"]["container"]["image_id"]
    )
    if matrix["container_image_id"] != image_id:
        raise FormalAttemptError("matrix and attestation image identities differ")
    if matrix["environment_attestation_digest"] != _sha256(args.attestation):
        raise FormalAttemptError("environment attestation digest differs from the matrix")
    method_path = ROOT / "config/method.defaults.json"
    safety_path = ROOT / "config/safety_limits.formal.json"
    if matrix["method_defaults_digest"] != _sha256(method_path):
        raise FormalAttemptError("method defaults digest differs from the matrix")
    if matrix["safety_limits_digest"] != _sha256(safety_path):
        raise FormalAttemptError("formal safety limits digest differs from the matrix")
    if _read_object(method_path).get("thresholds") != matrix["thresholds"]:
        raise FormalAttemptError("matrix thresholds differ from the frozen method defaults")
    candidate = attestation["attestation_payload"]["container"]["candidate"]
    if candidate["repository_revision"] != matrix.get("repository_revision"):
        raise FormalAttemptError("matrix and formal image repository revisions differ")
    if attestation["execution_environment"]["environment_id"] != matrix.get(
        "environment_id"
    ):
        raise FormalAttemptError("matrix and attested environment identities differ")
    image_inspect = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", args.image],
        text=True,
        capture_output=True,
        check=False,
    )
    if image_inspect.returncode != 0 or image_inspect.stdout.strip() != image_id:
        raise FormalAttemptError("local formal image differs from the attested image")
    preflight = _preflight(args.image)
    environment_copy = args.run_root / study_id / "environment.json"
    if environment_copy.exists():
        if _sha256(environment_copy) != _sha256(args.attestation):
            raise FormalAttemptError("retained run environment differs from attestation")
    else:
        environment_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.attestation, environment_copy)

    ledger = StudyLedger(args.study_root / "attempt-ledger.jsonl", study_id=study_id)
    state = verify_study_ledger(ledger.path)
    plan_spec = cell["plan"]
    plan = create_plan(
        attestation=attestation,
        run_id=args.attempt_id,
        plan_id=f"{args.attempt_id}-plan",
        source_route=plan_spec["source_route"],
        target_route=plan_spec["target_route"],
        expected_successor=plan_spec["expected_successor"],
        expected_fallback=plan_spec["expected_fallback"],
        target_activation_expected=plan_spec["target_activation_expected"],
        registration_rejection_expected=plan_spec[
            "registration_rejection_expected"
        ],
        activation_rejection_expected=plan_spec["activation_rejection_expected"],
        completion_expected=plan_spec["completion_expected"],
        fault_expected=plan_spec["fault_expected"],
        fallback_expected=plan_spec["fallback_expected"],
        thresholds=matrix["thresholds"],
        strategy=plan_spec.get("strategy", "official_sequence"),
        simulation_seed=simulation_seed,
        seed=plan_spec.get("seed"),
        timing_bounds_ns=plan_spec.get("timing_bounds_ns"),
        target_activation_count=plan_spec.get("target_activation_count"),
    )
    validate_plan(plan)
    plan_path = args.run_root / study_id / "plans" / f"{args.attempt_id}.json"
    attempt_root = args.run_root / study_id / args.attempt_id
    existing = state["attempts"].get(args.attempt_id)
    launch_returncode = -1
    if phase == "finalize":
        if existing is None or existing["state"] != "LAUNCHED":
            raise FormalAttemptError("finalization requires one launched attempt")
        if not plan_path.is_file() or _read_object(plan_path) != plan:
            raise FormalAttemptError("retained plan differs from the frozen matrix")
        driver_path = attempt_root / "container-driver.result.json"
        if driver_path.is_file():
            launch_returncode = int(_read_object(driver_path).get("returncode", -1))
    else:
        if existing is not None:
            raise FormalAttemptError("attempt ID has already entered the formal ledger")
        cell_attempts = [
            value for value in state["attempts"].values() if value["cell_id"] == cell_id
        ]
        accepted = sum(value["outcome"] == "ACCEPTED" for value in cell_attempts)
        if accepted >= int(cell["accepted_target"]):
            raise FormalAttemptError("cell accepted target has already been reached")
        if len(cell_attempts) >= int(cell["launch_cap"]):
            raise FormalAttemptError(
                "cell launch cap is exhausted: MEASUREMENT_INSUFFICIENT"
            )
        _write_new(plan_path, plan)
        plan_digest = _sha256(plan_path)
        ledger.append(
            attempt_id=args.attempt_id,
            cell_id=cell_id,
            state="REGISTERED",
            payload={"plan_digest": plan_digest},
        )
        ledger.append(
            attempt_id=args.attempt_id,
            cell_id=cell_id,
            state="LAUNCHED",
            payload={"image_id": image_id, "preflight_status": preflight["status"]},
        )

        command = [
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
            study_id,
            "--run-id",
            args.attempt_id,
            "--mechanism",
            runtime["mechanism"],
            "--source-route",
            plan_spec["source_route"],
            "--setpoint-kind",
            runtime.get("setpoint_kind", "trajectory"),
            "--fault-mode",
            runtime.get("fault_mode", "normal"),
            "--successor-route",
            runtime.get("successor_route", "internal_land"),
            "--repeat-count",
            str(runtime.get("repeat_count", 1)),
            "--slot",
            str(args.slot),
            "--cpu-set",
            args.cpu_set,
            "--memory",
            args.memory,
            "--active-s",
            str(runtime.get("active_s", 8.0)),
            "--simulation-seed",
            str(simulation_seed),
            "--attempt-timeout-s",
            str(runtime.get("attempt_timeout_s", 90.0)),
            "--outer-timeout-s",
            str(runtime.get("outer_timeout_s", 160.0)),
            "--safety-limits",
            "/opt/uav_sf/config/safety_limits.formal.json",
        ]
        if runtime.get("health_loss"):
            command.append("--health-loss")
        if runtime.get("duplicate_registration"):
            command.append("--duplicate-registration")
        if runtime.get("manual_land_offset_s") is not None:
            command.extend(
                ["--manual-land-offset-s", str(runtime["manual_land_offset_s"])]
            )
        launch = subprocess.run(command, text=True, capture_output=True, check=False)
        launch_returncode = launch.returncode
        if phase == "live":
            return {
                "schema_version": "1.0",
                "study_id": study_id,
                "attempt_id": args.attempt_id,
                "phase": "LIVE_COMPLETE",
                "runtime_driver_returncode": launch_returncode,
                "runtime_result_present": (attempt_root / "runtime_result.json").is_file(),
            }

    plan_digest = _sha256(plan_path)
    runtime_result_path = attempt_root / "runtime_result.json"
    runtime_outcome = "ENVIRONMENT_FAILURE"
    if runtime_result_path.is_file():
        runtime_outcome = str(_read_object(runtime_result_path).get("outcome"))

    process_command = [
        "docker",
        "run",
        "--rm",
        "--runtime",
        "runc",
        "--network",
        "none",
        "--read-only",
        "--user",
        f"{args.uid}:{args.gid}",
        "--mount",
        f"type=bind,src={args.run_root.resolve()},dst=/runs",
        args.image,
        "python3",
        "-m",
        "scripts.runtime.process_attempt",
        "--attempt-root",
        f"/runs/{study_id}/{args.attempt_id}",
        "--plan",
        f"/runs/{study_id}/plans/{args.attempt_id}.json",
        "--environment",
        f"/runs/{study_id}/environment.json",
        "--maximum-clock-uncertainty-ns",
        str(matrix["maximum_clock_uncertainty_ns"]),
    ]
    processing = subprocess.run(
        process_command, text=True, capture_output=True, check=False
    )
    processing_path = attempt_root / "processing_result.json"
    if processing_path.is_file():
        processing_result = _read_object(processing_path)
        outcome = str(processing_result["outcome"])
    else:
        processing_result = {
            "outcome": runtime_outcome,
            "processing_error": processing.stderr.strip() or processing.stdout.strip(),
        }
        outcome = runtime_outcome
    compact_root = args.study_root / "results" / args.attempt_id
    retained = _compact_evidence(attempt_root, compact_root)
    closure = {
        "schema_version": "1.0",
        "study_id": study_id,
        "cell_id": cell_id,
        "attempt_id": args.attempt_id,
        "execution_model": "two_phase_barrier" if phase == "finalize" else "single_attempt",
        "outcome": outcome,
        "plan_digest": plan_digest,
        "image_id": image_id,
        "runtime_driver_returncode": launch_returncode,
        "processing_returncode": processing.returncode,
        "compact_evidence": retained,
    }
    _write_new(compact_root / "closure.json", closure)
    ledger.append(
        attempt_id=args.attempt_id,
        cell_id=cell_id,
        state="CLOSED",
        payload={"outcome": outcome, "closure_digest": _sha256(compact_root / "closure.json")},
    )
    return closure


def _emergency_close(args: argparse.Namespace, reason: str) -> None:
    """Close an already-launched attempt when host orchestration itself fails."""
    try:
        matrix = _read_object(args.matrix)
        study_id = str(matrix["study_id"])
        cell = _cell(matrix, args.attempt_id)
        cell_id = str(cell["cell_id"])
        ledger_path = args.study_root / "attempt-ledger.jsonl"
        state = verify_study_ledger(ledger_path)
        attempt = state["attempts"].get(args.attempt_id)
        if attempt is None or attempt["state"] != "LAUNCHED":
            return
        compact_root = args.study_root / "results" / args.attempt_id
        closure_path = compact_root / "closure.json"
        if not closure_path.exists():
            _write_new(
                closure_path,
                {
                    "schema_version": "1.0",
                    "study_id": study_id,
                    "cell_id": cell_id,
                    "attempt_id": args.attempt_id,
                    "outcome": "ENVIRONMENT_FAILURE",
                    "host_orchestration_error": reason,
                    "compact_evidence": {},
                },
            )
        StudyLedger(ledger_path, study_id=study_id).append(
            attempt_id=args.attempt_id,
            cell_id=cell_id,
            state="CLOSED",
            payload={
                "outcome": "ENVIRONMENT_FAILURE",
                "closure_digest": _sha256(closure_path),
            },
        )
    except Exception as close_error:  # noqa: BLE001 - preserve both failures verbatim
        print(
            json.dumps(
                {
                    "status": "EMERGENCY_CLOSURE_FAILED",
                    "reason": str(close_error),
                    "original_reason": reason,
                }
            ),
            file=sys.stderr,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--study-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, default=Path("runs"))
    parser.add_argument("--image", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--slot", type=int, required=True)
    parser.add_argument("--cpu-set", required=True)
    parser.add_argument("--memory", default="24g")
    parser.add_argument(
        "--phase", choices=["live", "finalize", "all"], default="all"
    )
    parser.add_argument("--uid", type=int, default=os.getuid())
    parser.add_argument("--gid", type=int, default=os.getgid())
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, ValueError, KeyError, FormalAttemptError, subprocess.SubprocessError) as exc:
        _emergency_close(args, str(exc))
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
