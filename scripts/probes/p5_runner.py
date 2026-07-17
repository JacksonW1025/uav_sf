#!/usr/bin/env python3
"""Validate and materialize the preregistered P5 paired execution plan."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = ROOT / "experiments" / "probes" / "p5" / "scenario_matrix.yaml"
DEFAULT_DISPOSITION = ROOT / "experiments" / "probes" / "p5" / "preflight_disposition.yaml"
DEFAULT_RUN_ROOT = ROOT / "runs" / "p5" / "campaign"
ANALYSIS = ROOT / "experiments" / "probes" / "p5" / "pre_registered_analysis.yaml"
MINIMAL_LOGGER_TOPICS = ROOT / "config" / "phase_a2_minimal_logger_topics.txt"
METRICS = (
    "registration_admission_latency_ms",
    "activation_latency_ms",
    "failure_detection_latency_ms",
    "fallback_selection_latency_ms",
    "unregistration_release_latency_ms",
    "reentry_latency_ms",
    "first_target_consumption_ms",
    "old_epoch_revocation_ms",
    "target_installation_ms",
    "maximum_overlap_ms",
    "maximum_gap_ms",
    "allocator_transition_ms",
    "writer_transition_ms",
    "altitude_loss_m",
    "peak_tilt_rad",
    "position_error_m",
    "recovery_duration_ms",
)

PHYSICAL_METRICS = {"altitude_loss_m", "peak_tilt_rad", "position_error_m"}


def load_matrix(path: Path = DEFAULT_MATRIX) -> dict:
    matrix = yaml.safe_load(path.read_text(encoding="utf-8"))
    classes = [cell["transition_class"] for cell in matrix["cells"]]
    if classes != [f"T{index}" for index in range(1, 10)]:
        raise ValueError("P5 core matrix must contain T1 through T9 exactly once")
    if int(matrix["paired_repeats"]) < 5:
        raise ValueError("P5 requires at least five initial paired repeats")
    if set(matrix["mechanisms"]) != {"legacy_offboard", "dynamic_external_mode"}:
        raise ValueError("P5 requires both route mechanisms")
    return matrix


def execution_plan(matrix: dict) -> list[dict]:
    rows: list[dict] = []
    for cell_index, cell in enumerate(matrix["cells"], start=1):
        for repeat in range(1, int(matrix["paired_repeats"]) + 1):
            pair_id = f"{cell['cell_id']}_pair_r{repeat}"
            seed = 50_000 + cell_index * 100 + repeat
            for mechanism in matrix["mechanisms"]:
                rows.append(
                    {
                        "run_id": f"{pair_id}_{mechanism}",
                        "pair_id": pair_id,
                        "cell_id": cell["cell_id"],
                        "transition_class": cell["transition_class"],
                        "context": cell["context"],
                        "action": cell["action"],
                        "mechanism": mechanism,
                        "simulation_seed": seed,
                        "repeat": repeat,
                        "fault_offset_s": matrix["locked_execution"]["fault_offset_s"],
                        "fallback_mode": matrix["locked_execution"]["fallback_mode"],
                        "status": "PLANNED",
                    }
                )
    return rows


def write_plan(rows: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def load_disposition(path: Path = DEFAULT_DISPOSITION) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def command_for(row: dict[str, Any]) -> list[str] | None:
    mechanism = "offboard" if row["mechanism"] == "legacy_offboard" else "external"
    transition_class = row["transition_class"]
    run_id = row["run_id"]
    if transition_class in {"T3", "T9"}:
        return None
    if transition_class in {"T1", "T2"}:
        return [str(ROOT / "scripts/probes/run_p0_scenario.sh"), mechanism, run_id]
    if transition_class in {"T4", "T5", "T6"}:
        fault = {"T4": "sigterm", "T5": "sigkill", "T6": "sigstop_sigcont"}[
            transition_class
        ]
        return [str(ROOT / "scripts/probes/run_p2_scenario.sh"), mechanism, fault, run_id]
    if transition_class == "T7":
        return [str(ROOT / "scripts/probes/run_p3_scenario.sh"), mechanism, "on", "off", run_id]
    if transition_class == "T8":
        return [str(ROOT / "scripts/probes/run_p3_scenario.sh"), mechanism, "off", "on", run_id]
    raise ValueError(f"unsupported transition class: {transition_class}")


def environment_for(row: dict[str, Any], campaign_root: Path, attempt_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "ROS_DISTRO_SETUP": "/opt/ros/humble/setup.bash",
            "ROS_WORKSPACE_SETUP": str(ROOT / "ros2_ws_humble_live/install/setup.bash"),
            "MICROXRCE_AGENT_BIN": "/usr/local/bin/MicroXRCEAgent",
            "MICROXRCE_AGENT_LD_LIBRARY_PATH": "/usr/local/lib",
            "PX4_OBSERVABILITY_DIR": str(
                ROOT / "external/PX4-Autopilot-oracle-validation-control"
            ),
            "ROUTE_EXTERNAL_MODE_BIN": str(
                ROOT
                / "ros2_ws_humble_live/install/route_transition_external_mode/lib/route_transition_external_mode/route_transition_external_mode"
            ),
            "ROUTE_EXPERIMENT_FAULT_OFFSET_S": str(row["fault_offset_s"]),
            # The bridge discards startup backlog before fitting. Forty monitor
            # samples leave at least the preregistered 20 usable fit samples even
            # for Hold-replacement runs with a shorter post-takeoff lifecycle.
            "ROUTE_EXPERIMENT_MIN_CLOCK_SAMPLES": "40",
            "ROUTE_EXPERIMENT_BEHAVIOR_CONTEXT": str(row["context"]),
            "ROUTE_EXPERIMENT_SIMULATION_SEED": str(row["simulation_seed"]),
            "ROUTE_EXPERIMENT_SDLOG_PROFILE": "0",
            "ROUTE_EXPERIMENT_LOGGER_TOPICS_FILE": str(MINIMAL_LOGGER_TOPICS),
            "ROUTE_EXPERIMENT_RAW_ROOT": str(attempt_root / "raw"),
            "ROUTE_EXPERIMENT_PROCESSED_ROOT": str(attempt_root),
            "P0_RUN_ROOT": str(campaign_root),
            "P0_PROCESSED_ROOT": str(campaign_root),
            "P0_SDLOG_PROFILE": "0",
            "P0_LOGGER_TOPICS_FILE": str(MINIMAL_LOGGER_TOPICS),
            "P0_OBSERVATION_PROFILE": "TRANSITION",
            "P0_UORB_QUEUE_LENGTH": "4",
            "P0_SIMULATION_SEED": str(row["simulation_seed"]),
        }
    )
    if row["transition_class"] == "T1":
        env.update({"P0_ACTIVE_DURATION_S": "4", "P0_HOVER_ONLY": "1"})
    elif row["transition_class"] == "T2":
        env.update({"P0_ACTIVE_DURATION_S": "8", "P0_HOVER_ONLY": "0"})
    return env


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _external_mode_id(trace: Path) -> int:
    modes: list[int] = []
    for line in trace.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event_type") == "route_epoch_changed":
            mode = event.get("declared_mode")
            if isinstance(mode, int) and mode >= 23:
                modes.append(mode)
    if not modes:
        raise ValueError("dynamic external mode route epoch was not observed")
    return modes[0]


def selected_modes(row: dict[str, Any], trace: Path) -> tuple[int, int]:
    external = 14 if row["mechanism"] == "legacy_offboard" else _external_mode_id(trace)
    if row["transition_class"] == "T1":
        return 17, external
    if row["transition_class"] == "T2":
        return external, 4
    monitor = _json(trace.parent / "raw/monitor_result.json")
    observed_fallback = monitor.get("fallback_nav_state")
    if not isinstance(observed_fallback, int):
        raise ValueError("independently observed fallback route is unavailable")
    return external, observed_fallback


def run_selected_oracle(row: dict[str, Any], attempt_root: Path) -> dict[str, Any]:
    trace = attempt_root / "route_trace.jsonl"
    source, target = selected_modes(row, trace)
    output = attempt_root / "p5_route_oracle.json"
    subprocess.run(
        [
            "python3",
            str(ROOT / "scripts/oracles/route_oracle_v0.py"),
            "--trace",
            str(trace),
            "--clock-bridge",
            str(attempt_root / "clock_bridge.json"),
            "--transition-source-mode",
            str(source),
            "--transition-target-mode",
            str(target),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return _json(output)


def classify_attempt(
    row: dict[str, Any], attempt_root: Path, return_code: int
) -> tuple[str, list[str], dict[str, Any] | None]:
    reasons: list[str] = []
    required = [
        attempt_root / "route_trace.jsonl",
        attempt_root / "clock_bridge.json",
        attempt_root / "raw/flight.ulg",
    ]
    if return_code != 0:
        reasons.append(f"runner_return_code:{return_code}")
    for path in required:
        if not path.is_file():
            reasons.append(f"missing_artifact:{path.name}")
    if reasons:
        px4_log = attempt_root / "raw/px4.log"
        px4_text = (
            px4_log.read_text(encoding="utf-8", errors="replace")
            if px4_log.exists()
            else ""
        )
        runner_result_path = attempt_root / "raw/runner_result.json"
        runner_result = _json(runner_result_path) if runner_result_path.exists() else {}
        if (
            runner_result.get("reason") == "timeout in REQUEST_HOLD_AFTER_COMPLETION"
            and "stack smashing detected" not in px4_text
            and " Aborted " not in px4_text
        ):
            return "CAMPAIGN_CONFIGURATION_FAILURE", reasons, None
        return "ENVIRONMENT_FAILURE", reasons, None
    clock = _json(attempt_root / "clock_bridge.json")
    if clock.get("status") != "VALID":
        reasons.append(f"clock_bridge:{clock.get('status')}")
    try:
        oracle = run_selected_oracle(row, attempt_root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return "MEASUREMENT_UNKNOWN", [f"selected_oracle:{exc}"], None
    window = (
        oracle.get("clauses", {})
        .get("exclusivity", {})
        .get("metrics", {})
        .get("critical_window", {})
    )
    if window.get("coverage_verdict") != "COMPLETE":
        reasons.append(f"critical_window:{window.get('coverage_verdict')}")
    result_name = "runner_result.json" if row["transition_class"] in {"T1", "T2"} else "monitor_result.json"
    result = _json(attempt_root / "raw" / result_name)
    if result.get("status") != "PASS":
        reasons.append(f"scenario_status:{result.get('status')}")
    if row["transition_class"] in {"T4", "T5", "T6"}:
        fault = _json(attempt_root / "raw/fault_record.json")
        if float(fault.get("requested_delay_seconds", -1)) != float(row["fault_offset_s"]):
            reasons.append("fault_offset_mismatch")
    phase = {
        "hover": "hover",
        "straight": "straight_line",
        "turn": "low_speed_turn",
        "descent": "stable_descent",
    }[row["context"]]
    evidence_files = [attempt_root / "route_trace.jsonl"]
    if (attempt_root / "raw/external_mode.log").exists():
        evidence_files.append(attempt_root / "raw/external_mode.log")
    context_seen = any(phase in path.read_text(encoding="utf-8", errors="replace") for path in evidence_files)
    if not context_seen:
        reasons.append(f"behavior_context_missing:{phase}")
    return ("VALID" if not reasons else "MEASUREMENT_UNKNOWN"), reasons, oracle


def _metric_row(
    row: dict[str, Any], attempt_root: Path, oracle: dict[str, Any]
) -> dict[str, Any]:
    output: dict[str, Any] = {key: "" for key in METRICS}
    clock = _json(attempt_root / "clock_bridge.json")
    uncertainty_ms = float(clock["uncertainty_ns"]) / 1_000_000.0
    transition_us = float(oracle["transition"]["timestamp_us"])
    clauses = oracle["clauses"]
    installation = clauses["installation"]["metrics"]
    revocation = clauses["revocation"]["metrics"]
    continuity = clauses["continuity"]["metrics"]
    exclusivity = clauses["exclusivity"]["metrics"]
    output["first_target_consumption_ms"] = (
        float(installation["first_target_consumption_us"]) - transition_us
    ) / 1000.0
    output["old_epoch_revocation_ms"] = float(revocation["revocation_latency_ms"])
    output["target_installation_ms"] = float(installation["installation_latency_ms"])
    output["maximum_overlap_ms"] = 0.0 if not exclusivity["old_new_epoch_overlap"] else ""
    output["maximum_gap_ms"] = float(continuity["maximum_unowned_window_ms"])
    output["writer_transition_ms"] = (
        float(installation["first_target_writer_us"]) - transition_us
    ) / 1000.0
    output["allocator_transition_ms"] = output["target_installation_ms"]
    if row["transition_class"] == "T1":
        output["registration_admission_latency_ms"] = output["target_installation_ms"]
        output["activation_latency_ms"] = output["first_target_consumption_ms"]
    if row["transition_class"] in {"T2", "T4"}:
        output["unregistration_release_latency_ms"] = output["target_installation_ms"]
    monitor_path = attempt_root / "raw/monitor_result.json"
    if monitor_path.exists():
        monitor = _json(monitor_path)
        detection = monitor.get("failure_detection_latency_ms")
        if detection is not None:
            output["failure_detection_latency_ms"] = float(detection)
            output["fallback_selection_latency_ms"] = float(detection)
            output["recovery_duration_ms"] = float(detection) + float(
                output["target_installation_ms"]
            )
        physical = monitor.get("physical_recovery", {})
        if physical.get("altitude_loss_m") is not None:
            output["altitude_loss_m"] = float(physical["altitude_loss_m"])
        if physical.get("peak_tilt_rad") is not None:
            output["peak_tilt_rad"] = float(physical["peak_tilt_rad"])
    analysis = yaml.safe_load(ANALYSIS.read_text(encoding="utf-8"))
    physical_resolution = analysis["uncertainty_model"]["physical_resolution"]
    for metric in METRICS:
        if output[metric] == "":
            output[f"{metric}_uncertainty"] = ""
        elif metric in PHYSICAL_METRICS:
            output[f"{metric}_uncertainty"] = float(physical_resolution[metric])
        else:
            output[f"{metric}_uncertainty"] = uncertainty_ms
    return output


def _refresh_accepted_metrics(
    row: dict[str, Any], accepted: dict[str, Any]
) -> dict[str, Any]:
    """Recompute derived metrics without changing which preserved attempt was accepted."""
    attempt_root = ROOT / str(accepted["artifact_root"])
    oracle = run_selected_oracle(row, attempt_root)
    refreshed = {**accepted, **_metric_row(row, attempt_root, oracle)}
    (attempt_root.parent / "accepted_result.json").write_text(
        json.dumps(refreshed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return refreshed


def execute_plan(
    rows: list[dict[str, Any]],
    campaign_root: Path,
    max_attempts: int,
    *,
    max_new_sides: int = 2,
    max_environment_attempts: int = 3,
    batch_time_limit_seconds: float = 1200.0,
) -> list[dict[str, Any]]:
    disposition = load_disposition()
    matched = set(disposition["matched_cells"])
    results: list[dict[str, Any]] = []
    campaign_root.mkdir(parents=True, exist_ok=True)
    batch_started = time.monotonic()
    new_sides = 0
    for row in rows:
        if row["cell_id"] not in matched:
            continue
        logical_root = campaign_root / row["run_id"]
        accepted_record = logical_root / "accepted_result.json"
        if accepted_record.exists():
            results.append(_refresh_accepted_metrics(row, _json(accepted_record)))
            continue
        # A corrected validity rule may make a preserved, fully collected attempt
        # acceptable without rerunning SITL. Never promote a nonzero-return attempt.
        for prior_result_path in sorted(logical_root.glob("**/attempt_result.json")):
            prior = _json(prior_result_path)
            if int(prior.get("return_code", 1)) != 0:
                continue
            prior_root = prior_result_path.parent
            prior_validity, prior_reasons, prior_oracle = classify_attempt(row, prior_root, 0)
            if prior_validity != "VALID" or prior_oracle is None:
                continue
            attempt_number = int(prior["attempt"])
            accepted = {
                **row,
                "validity": "VALID",
                "accepted_attempt": attempt_number,
                "environment_retry_count": attempt_number - 1,
                "artifact_root": str(prior_root.resolve().relative_to(ROOT)),
                "clock_status": "VALID",
                "critical_window": "COMPLETE",
                "observed_fallback_nav_state": prior_oracle["transition"]["target_mode"],
                "accepted_after_classifier_correction": True,
                **_metric_row(row, prior_root, prior_oracle),
            }
            accepted_record.parent.mkdir(parents=True, exist_ok=True)
            accepted_record.write_text(
                json.dumps(accepted, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            results.append(accepted)
            break
        if accepted_record.exists():
            continue
        attempts: list[dict[str, Any]] = []
        existing_attempt_numbers = []
        existing_environment_attempts = 0
        for path in logical_root.glob("**/*attempt_*"):
            match = re.search(r"attempt_(\d+)$", path.name)
            if path.is_dir() and match:
                existing_attempt_numbers.append(int(match.group(1)))
        for path in logical_root.glob("**/attempt_result.json"):
            prior = _json(path)
            validity, _, _ = classify_attempt(
                row, path.parent, int(prior.get("return_code", 1))
            )
            if validity == "ENVIRONMENT_FAILURE":
                existing_environment_attempts += 1
        if existing_environment_attempts >= max_environment_attempts:
            results.append(
                {
                    **row,
                    "validity": "BLOCKED_ENVIRONMENT",
                    "accepted_attempt": "",
                    "environment_retry_count": existing_environment_attempts,
                    "artifact_root": "",
                    "clock_status": "",
                    "critical_window": "",
                    **{key: "" for key in METRICS},
                    **{f"{key}_uncertainty": "" for key in METRICS},
                }
            )
            continue
        if new_sides >= max_new_sides or (
            time.monotonic() - batch_started >= batch_time_limit_seconds
        ):
            break
        new_sides += 1
        first_attempt = max(existing_attempt_numbers, default=0) + 1
        accepted_this_side = False
        terminal_validity = "ENVIRONMENT_FAILURE"
        environment_attempts = existing_environment_attempts
        for attempt in range(first_attempt, first_attempt + max_attempts):
            attempt_root = logical_root / f"attempt_{attempt}"
            attempt_root.mkdir(parents=True, exist_ok=True)
            command_row = dict(row)
            command_row["run_id"] = f"{row['run_id']}__attempt_{attempt}"
            command = command_for(command_row)
            assert command is not None
            env = environment_for(command_row, campaign_root, attempt_root)
            # P0 appends the run ID, so place that attempt at the common artifact root.
            if row["transition_class"] in {"T1", "T2"}:
                env["P0_RUN_ROOT"] = str(logical_root)
                env["P0_PROCESSED_ROOT"] = str(logical_root)
                attempt_root = logical_root / command_row["run_id"]
            started = time.time_ns()
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            (attempt_root / "campaign_console.log").write_text(
                completed.stdout, encoding="utf-8"
            )
            validity, reasons, oracle = classify_attempt(row, attempt_root, completed.returncode)
            attempt_record = {
                "attempt": attempt,
                "artifact_root": str(attempt_root.resolve().relative_to(ROOT)),
                "return_code": completed.returncode,
                "started_time_ns": started,
                "finished_time_ns": time.time_ns(),
                "validity": validity,
                "reasons": reasons,
            }
            attempts.append(attempt_record)
            (attempt_root / "attempt_result.json").write_text(
                json.dumps(attempt_record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            if validity == "VALID" and oracle is not None:
                accepted = {
                    **row,
                    "validity": validity,
                    "accepted_attempt": attempt,
                    "environment_retry_count": attempt - 1,
                    "artifact_root": str(attempt_root.resolve().relative_to(ROOT)),
                    "clock_status": "VALID",
                    "critical_window": "COMPLETE",
                    "observed_fallback_nav_state": oracle["transition"]["target_mode"],
                    **_metric_row(row, attempt_root, oracle),
                }
                accepted_record.parent.mkdir(parents=True, exist_ok=True)
                accepted_record.write_text(
                    json.dumps(accepted, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                results.append(accepted)
                accepted_this_side = True
                break
            terminal_validity = validity
            if validity == "ENVIRONMENT_FAILURE":
                environment_attempts += 1
                if environment_attempts >= max_environment_attempts:
                    terminal_validity = "BLOCKED_ENVIRONMENT"
                    break
            elif validity == "CAMPAIGN_CONFIGURATION_FAILURE":
                break
        if not accepted_this_side:
            results.append(
                {
                    **row,
                    "validity": terminal_validity,
                    "accepted_attempt": "",
                    "environment_retry_count": environment_attempts,
                    "artifact_root": "",
                    "clock_status": "",
                    "critical_window": "",
                    **{key: "" for key in METRICS},
                    **{f"{key}_uncertainty": "" for key in METRICS},
                }
            )
        print(
            json.dumps(
                {
                    "run_id": row["run_id"],
                    "validity": results[-1]["validity"],
                    "completed": len(results),
                }
            ),
            flush=True,
        )
    return results


def write_results(rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "runs" / "p5" / "execution_plan.tsv"
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--campaign-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--results", type=Path, default=ROOT / "runs/p5/accepted_runs.tsv")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument(
        "--max-new-sides",
        type=int,
        default=2,
        help="maximum previously incomplete mechanism sides to attempt in this batch",
    )
    parser.add_argument("--max-environment-attempts", type=int, default=3)
    parser.add_argument("--batch-time-limit-seconds", type=float, default=1200.0)
    args = parser.parse_args()
    matrix = load_matrix(args.matrix)
    rows = execution_plan(matrix)
    write_plan(rows, args.output)
    if args.execute:
        if args.max_attempts < 1 or args.max_new_sides < 1:
            parser.error("--max-attempts and --max-new-sides must be positive")
        results = execute_plan(
            rows,
            args.campaign_root,
            args.max_attempts,
            max_new_sides=args.max_new_sides,
            max_environment_attempts=args.max_environment_attempts,
            batch_time_limit_seconds=args.batch_time_limit_seconds,
        )
        write_results(results, args.results)
        print(
            json.dumps(
                {
                    "accepted_valid_runs": sum(row["validity"] == "VALID" for row in results),
                    "attempted_applicable_runs": len(results),
                }
            )
        )
    else:
        print(json.dumps({"paired_cells": len(matrix["cells"]), "planned_runs": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
