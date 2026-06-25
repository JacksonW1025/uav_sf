#!/usr/bin/env python3
"""Narrow GATE-3 position-error amplitude probe for mc_nn_control."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any

import m1_diff_runner as m1


LOGGER_TOPICS = [
    "neural_control 0",
    "trajectory_setpoint 0",
    "vehicle_local_position 0",
    "vehicle_local_position_groundtruth 0",
    "vehicle_angular_velocity 0",
    "vehicle_angular_velocity_groundtruth 0",
    "vehicle_attitude 0",
    "vehicle_attitude_groundtruth 0",
    "vehicle_status 0",
    "estimator_status 0",
    "estimator_status_flags 0",
    "failsafe_flags 0",
    "actuator_motors 0",
    "actuator_outputs 0",
    "failure_detector_status 0",
]

FLIGHT_UNSAFE_REASONS = {
    "missing_required_topics",
    "controller_mode_not_confirmed",
    "unexpected_disarm",
    "failsafe",
    "ground_contact",
    "attitude_quaternion_nonfinite",
    "attitude_diverged",
    "angular_rate_diverged",
    "active_motor_nan",
    "motor_saturation",
    "missing_position_or_setpoint_window",
}

BASELINE_SEEDS = [20261301, 20261302, 20261303, 20261304, 20261305]
ATTACK_SEEDS = [20261401, 20261402, 20261403]

COMMON_BOOT_PARAMS = {
    "MC_NN_EN": 0,
    "MC_NN_MANL_CTRL": 0,
}

COMMON_PX4_PARAMS = {
    "NAV_DLL_ACT": 0,
    "COM_DISARM_LAND": -1,
    "COM_OF_LOSS_T": 5.0,
    "IMU_GYRO_RATEMAX": 400,
    "COM_RC_IN_MODE": 4,
    "COM_RCL_EXCEPT": 8,
    "MC_NN_MANL_CTRL": 0,
    "SYS_FAILURE_EN": 1,
    "CA_FAILURE_MODE": 1,
}


@dataclass(frozen=True)
class AttackCase:
    tag: str
    delta_ned: tuple[float, float, float]
    duration_s: float
    mission_end_s: float
    description: str


DEFAULT_ATTACKS = [
    AttackCase(
        "ramp_x_12m_3s",
        (12.0, 0.0, 0.0),
        3.0,
        50.0,
        "12 m x ramp over 3 s after controller switch.",
    ),
    AttackCase(
        "ramp_x_8m_4s",
        (8.0, 0.0, 0.0),
        4.0,
        50.0,
        "8 m x ramp over 4 s after controller switch.",
    ),
    AttackCase(
        "ramp_x_6m_6s",
        (6.0, 0.0, 0.0),
        6.0,
        50.0,
        "6 m x ramp over 6 s after controller switch.",
    ),
]

COMPACT_METRIC_KEYS = [
    "safe",
    "safe_reasons",
    "control_level_unsafe_reasons",
    "infrastructure_reasons",
    "infrastructure_limited",
    "mode_confirmed",
    "target_nav_state_fraction",
    "nav_states_in_window",
    "tracking_error_max_m",
    "tracking_error_rms_m",
    "final_error_m",
    "roll_pitch_max_deg",
    "angular_rate_max_rad_s",
    "active_motor_nan_count",
    "motor_saturation_ratio",
    "motor_saturation_count",
    "min_altitude_agl_m",
]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def compact_record(record: dict[str, Any]) -> dict[str, Any]:
    metrics = {
        controller: {
            key: record.get("metrics", {}).get(controller, {}).get(key)
            for key in COMPACT_METRIC_KEYS
            if key in record.get("metrics", {}).get(controller, {})
        }
        for controller in ["classical", "mcnn"]
    }
    return {
        "tag": record.get("tag"),
        "seed": record.get("seed"),
        "role": record.get("role"),
        "theta": record.get("theta"),
        "flight": record.get("flight"),
        "d3": record.get("d3"),
        "metrics": metrics,
        "outputs": record.get("outputs"),
    }


def compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    compact = dict(payload)
    compact["baseline_records"] = [compact_record(record) for record in payload.get("baseline_records", [])]
    compact["attack_summaries"] = [
        {
            "case": item.get("case"),
            "primary_seed_count": item.get("primary_seed_count"),
            "d3_support": item.get("d3_support"),
            "records": [compact_record(record) for record in item.get("records", [])],
        }
        for item in payload.get("attack_summaries", [])
    ]
    return compact


def write_logger_topics(run_root: Path) -> None:
    logging_dir = run_root / "etc/logging"
    logging_dir.mkdir(parents=True, exist_ok=True)
    (logging_dir / "logger_topics.txt").write_text("\n".join(LOGGER_TOPICS) + "\n", encoding="utf-8")


def px4_command_script(theta: dict[str, Any], controller: str, sim_speed_factor: float) -> str:
    lines = ["sleep 4"]
    for name, value in theta.get("px4_params", {}).items():
        lines.append(m1.format_px4_param_command(name, value))
    if controller == "mcnn":
        lines.append("mc_nn_control start")
        lines.append("sleep 3")
        lines.append("mc_nn_control status")
    else:
        lines.append("sleep 3")
    lines.extend(
        [
            "commander status",
            "commander takeoff",
        ]
    )
    timing = theta["timing"]
    mission_end_s = float(timing["mission_end_s"])
    shutdown_margin_s = float(timing.get("px4_shutdown_margin_s", 8.0))
    shutdown_wall_slack_s = float(timing.get("px4_shutdown_wall_slack_s", 22.0))
    sleep_after_takeoff = int(math.ceil(mission_end_s + shutdown_margin_s + shutdown_wall_slack_s * sim_speed_factor))
    lines.extend(
        [
            f"sleep {sleep_after_takeoff}",
            "commander status",
            "listener vehicle_status 1",
            "listener vehicle_local_position 1",
            "listener vehicle_angular_velocity 1",
        ]
    )
    if controller == "mcnn":
        lines.append("mc_nn_control status")
    lines.extend(
        [
            "logger status",
            "shutdown",
        ]
    )
    return "\n".join(lines) + "\n"


def theta_common(tag: str, seed: int, description: str) -> dict[str, Any]:
    return {
        "tag": tag,
        "description": description,
        "seed": int(seed),
        "airframe": {"sim": "sih", "model": "sihsim_x500_v2", "sys_autostart": 10046},
        "timing": {
            "approach_start_s": 14.0,
            "controller_switch_s": 24.0,
            "trajectory_start_s": 31.0,
            "mission_end_s": 52.0,
            "mode_command_repeat_s": 0.5,
            "mode_command_timeout_s": 8.0,
            "px4_shutdown_margin_s": 8.0,
            "px4_shutdown_wall_slack_s": 22.0,
            "external_mode_id": 23,
        },
        "setpoint": {
            "rate_hz": 50.0,
            "hover_ned": [0.0, 0.0, -2.5],
            "yaw_rad": 0.0,
            "type": "step",
            "step": {"delta_ned": [0.0, 0.0, 0.0]},
        },
        "boot_px4_params": dict(COMMON_BOOT_PARAMS),
        "px4_params": dict(COMMON_PX4_PARAMS),
        "environment": {
            "scope": "position_error_amplitude_only",
            "uses_state_shim": False,
            "starts_raptor": False,
        },
        "faults": [],
        "sensor_perturbations": [],
    }


def baseline_theta(run_id: str, seed: int) -> dict[str, Any]:
    tag = f"{run_id}_baseline_s{seed}"
    theta = theta_common(
        tag,
        seed,
        "GATE-3 nominal denominator: finite hover after the same classical approach and optional mc_nn switch.",
    )
    theta["timing"]["trajectory_start_s"] = 32.0
    theta["timing"]["mission_end_s"] = 54.0
    theta["setpoint"]["type"] = "step"
    theta["setpoint"]["step"] = {"delta_ned": [0.0, 0.0, 0.0]}
    theta["mcnn_gate3"] = {
        "role": "baseline",
        "ratio_denominator": "tracking_error_rms_m",
    }
    return theta


def attack_theta(run_id: str, case: AttackCase, seed: int) -> dict[str, Any]:
    tag = f"{run_id}_{case.tag}_s{seed}"
    theta = theta_common(tag, seed, f"GATE-3 position-error amplitude probe: {case.description}")
    theta["timing"]["mission_end_s"] = case.mission_end_s
    theta["setpoint"]["type"] = "ramp"
    theta["setpoint"]["ramp"] = {
        "delta_ned": list(case.delta_ned),
        "duration_s": case.duration_s,
    }
    theta["mcnn_gate3"] = {
        "role": "attack",
        "channel": "position_error_amplitude",
        "case": asdict(case),
        "attack_budget_unit": "theta",
    }
    return theta


def run_one(
    repo: Path,
    theta_path: Path,
    theta: dict[str, Any],
    controller: str,
    run_dir: Path,
    env: dict[str, str],
    run_timeout_s: int,
    safety_config: Path,
) -> dict[str, Path]:
    tag = theta["tag"]
    px4_dir = repo / "external/PX4-Autopilot"
    build_dir = px4_dir / "build/px4_sitl_mcnn_sih"
    run_root = build_dir
    log_root = run_root / "log"

    prefix = f"mcnn_gate3_{tag}_{controller}"
    console_log = run_dir / f"{prefix}_px4_console.log"
    agent_log = run_dir / f"{prefix}_agent.log"
    topics_log = run_dir / f"{prefix}_topics.log"
    task_log = run_dir / f"{prefix}_task.log"
    task_json = run_dir / f"{prefix}_task.json"
    copied_ulog = run_dir / f"{prefix}.ulg"
    metrics_json = run_dir / f"{prefix}_metrics.json"

    for path in [console_log, agent_log, topics_log, task_log]:
        path.write_text("", encoding="utf-8")

    if not (build_dir / "bin/px4").exists():
        raise FileNotFoundError(f"PX4 binary missing: {build_dir / 'bin/px4'}")

    write_logger_topics(run_root)
    boot_airframe = m1.prepare_run_airframe(repo, run_root, theta)
    if log_root.exists():
        shutil.rmtree(log_root)
    log_root.mkdir(parents=True, exist_ok=True)
    for param_file in ["parameters.bson", "parameters_backup.bson"]:
        try:
            (run_root / param_file).unlink()
        except FileNotFoundError:
            pass

    agent_bin = m1.find_agent(repo)
    if not agent_bin.exists():
        raise FileNotFoundError(f"MicroXRCEAgent missing: {agent_bin}")

    px4_env = env.copy()
    px4_env.update(
        {
            "HEADLESS": "1",
            "PX4_SIMULATOR": "sihsim",
            "PX4_SIM_MODEL": theta.get("airframe", {}).get("model", "sihsim_x500_v2"),
            "PX4_SYS_AUTOSTART": str(theta.get("airframe", {}).get("sys_autostart", 10046)),
            "PX4_SIM_SPEED_FACTOR": os.environ.get("PX4_SIM_SPEED_FACTOR", "1"),
        }
    )
    sim_speed_factor = max(1.0, float(px4_env["PX4_SIM_SPEED_FACTOR"]))

    agent = None
    px4 = None
    task = None
    cmd_tmp = None
    try:
        with agent_log.open("w", encoding="utf-8") as agent_handle:
            agent = subprocess.Popen(
                [str(agent_bin), "udp4", "-p", os.environ.get("AGENT_PORT", "8888")],
                cwd=str(repo),
                env=env,
                stdout=agent_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            time.sleep(2.0)

        cmd_tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
        cmd_tmp.write(px4_command_script(theta, controller, sim_speed_factor))
        cmd_tmp.close()

        with console_log.open("w", encoding="utf-8") as console_handle, open(
            cmd_tmp.name, "r", encoding="utf-8"
        ) as stdin:
            console_handle.write(f"# mc_nn_control GATE-3 PX4 console controller={controller} tag={tag}\n")
            console_handle.write(f"PX4_DIR={px4_dir}\n")
            console_handle.write(f"PX4_SIM_MODEL={px4_env['PX4_SIM_MODEL']}\n")
            console_handle.write(f"PX4_SYS_AUTOSTART={px4_env['PX4_SYS_AUTOSTART']}\n")
            console_handle.write(f"PX4_SIM_SPEED_FACTOR={px4_env['PX4_SIM_SPEED_FACTOR']}\n")
            console_handle.write(f"THETA={theta_path}\n")
            console_handle.write(f"BOOT_AIRFRAME={boot_airframe}\n")
            console_handle.write(f"BOOT_PX4_PARAMS={json.dumps(theta.get('boot_px4_params', {}), sort_keys=True)}\n\n")
            console_handle.flush()
            px4 = subprocess.Popen(
                ["timeout", str(run_timeout_s), "./bin/px4", "."],
                cwd=str(run_root),
                env=px4_env,
                stdin=stdin,
                stdout=console_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

            if not m1.wait_for_dds_topics(repo, env, topics_log):
                raise RuntimeError(f"DDS topics did not appear for {controller}")

            with task_log.open("w", encoding="utf-8") as task_handle:
                task = subprocess.Popen(
                    [
                        sys.executable,
                        str(repo / "scripts/m1_offboard_task.py"),
                        "--theta",
                        str(theta_path),
                        "--controller",
                        controller,
                        "--result-json",
                        str(task_json),
                    ],
                    cwd=str(repo),
                    env=env,
                    stdout=task_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                try:
                    task_rc = task.wait(timeout=max(90, run_timeout_s - 20))
                except subprocess.TimeoutExpired as exc:
                    m1.terminate_process(task)
                    raise RuntimeError(f"task node timed out for {controller}") from exc

            console_handle.write(f"\n# task_rc={task_rc}\n")
            console_handle.flush()
            try:
                px4_rc = px4.wait(timeout=45)
            except subprocess.TimeoutExpired as exc:
                m1.terminate_process(px4)
                raise RuntimeError(f"PX4 did not shut down after task for {controller}") from exc
            console_handle.write(f"\n# px4_rc={px4_rc}\n")

        ulog = m1.latest_ulog(log_root)
        if ulog is None:
            raise RuntimeError(f"No ULOG found under {log_root}")
        shutil.copy2(ulog, copied_ulog)

        m1.run_checked(
            [
                sys.executable,
                str(repo / "scripts/m1_metrics.py"),
                "--ulog",
                str(copied_ulog),
                "--theta",
                str(theta_path),
                "--task-json",
                str(task_json),
                "--controller",
                controller,
                "--output",
                str(metrics_json),
                "--safety-config",
                str(safety_config),
            ],
            cwd=repo,
            log=run_dir / f"{prefix}_metrics.log",
            env=env,
        )
        return {
            "ulog": copied_ulog,
            "metrics": metrics_json,
            "task": task_json,
            "console": console_log,
            "agent": agent_log,
            "topics": topics_log,
        }
    finally:
        m1.terminate_process(task)
        m1.terminate_process(px4)
        m1.terminate_process(agent)
        if cmd_tmp is not None:
            try:
                Path(cmd_tmp.name).unlink()
            except FileNotFoundError:
                pass


def flight_safe(metrics: dict[str, Any]) -> bool:
    reasons = set(metrics.get("safe_reasons") or [])
    return not bool(reasons & FLIGHT_UNSAFE_REASONS)


def flight_quadrant(classical_ok: bool, mcnn_ok: bool) -> str:
    if classical_ok and mcnn_ok:
        return "boring_both_flight_safe"
    if not classical_ok and mcnn_ok:
        return "interesting_not_bug"
    if classical_ok and not mcnn_ok:
        return "primary_bug"
    return "too_hard_not_bug"


def finite_values(values: list[float | None]) -> list[float]:
    return [float(value) for value in values if value is not None and math.isfinite(float(value))]


def summarize_baseline(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for controller in ["classical", "mcnn"]:
        rms = finite_values([record["metrics"][controller].get("tracking_error_rms_m") for record in records])
        max_err = finite_values([record["metrics"][controller].get("tracking_error_max_m") for record in records])
        summary[controller] = {
            "tracking_error_rms_m": {
                "values": rms,
                "mean": mean(rms) if rms else None,
                "stdev": stdev(rms) if len(rms) > 1 else 0.0,
            },
            "tracking_error_max_m": {
                "values": max_err,
                "mean": mean(max_err) if max_err else None,
                "stdev": stdev(max_err) if len(max_err) > 1 else 0.0,
            },
        }
    return summary


def ratio(metric: float | None, baseline_mean: float | None) -> float | None:
    if metric is None or baseline_mean is None or baseline_mean <= 0.0:
        return None
    return float(metric) / float(baseline_mean)


def z_score(metric: float | None, baseline_mean: float | None, baseline_stdev: float | None) -> float | None:
    if metric is None or baseline_mean is None or baseline_stdev is None or baseline_stdev <= 0.0:
        return None
    return (float(metric) - float(baseline_mean)) / float(baseline_stdev)


def attach_gate3_fields(record: dict[str, Any], baseline: dict[str, Any] | None) -> None:
    metrics_by_controller = record["metrics"]
    classical = metrics_by_controller["classical"]
    mcnn = metrics_by_controller["mcnn"]
    classical_flight = flight_safe(classical)
    mcnn_flight = flight_safe(mcnn)
    classical_control_safe = classical_flight and not bool(classical.get("infrastructure_limited"))
    record["flight"] = {
        "classical_flight_safe": classical_flight,
        "mcnn_flight_safe": mcnn_flight,
        "classical_control_level_safe": classical_control_safe,
        "classical_infrastructure_limited": bool(classical.get("infrastructure_limited")),
        "flight_quadrant": flight_quadrant(classical_control_safe, mcnn_flight),
        "primary_bug": classical_control_safe and not mcnn_flight,
        "ignored_tracking_lag_reasons": {
            "classical": sorted(set(classical.get("safe_reasons") or []) - FLIGHT_UNSAFE_REASONS),
            "mcnn": sorted(set(mcnn.get("safe_reasons") or []) - FLIGHT_UNSAFE_REASONS),
        },
    }
    if baseline is None:
        return
    d3: dict[str, Any] = {}
    for controller in ["classical", "mcnn"]:
        stats = baseline[controller]["tracking_error_rms_m"]
        metric = metrics_by_controller[controller].get("tracking_error_rms_m")
        d3[controller] = {
            "tracking_error_rms_m": metric,
            "baseline_mean": stats.get("mean"),
            "baseline_stdev": stats.get("stdev"),
            "ratio_to_own_baseline": ratio(metric, stats.get("mean")),
            "z_vs_own_baseline": z_score(metric, stats.get("mean"), stats.get("stdev")),
        }
    record["d3"] = d3


def d3_support(records: list[dict[str, Any]]) -> dict[str, Any]:
    classical_ratios = finite_values(
        [record.get("d3", {}).get("classical", {}).get("ratio_to_own_baseline") for record in records]
    )
    mcnn_ratios = finite_values([record.get("d3", {}).get("mcnn", {}).get("ratio_to_own_baseline") for record in records])
    mcnn_z = finite_values([record.get("d3", {}).get("mcnn", {}).get("z_vs_own_baseline") for record in records])
    classical_median = median(classical_ratios) if classical_ratios else None
    mcnn_median = median(mcnn_ratios) if mcnn_ratios else None
    mcnn_z_median = median(mcnn_z) if mcnn_z else None
    supported = False
    if classical_median is not None and mcnn_median is not None and mcnn_z_median is not None:
        supported = mcnn_median > classical_median and mcnn_z_median > 2.0
    return {
        "classical_ratio_median": classical_median,
        "mcnn_ratio_median": mcnn_median,
        "mcnn_z_median": mcnn_z_median,
        "mcnn_ratio_minus_classical_ratio": (mcnn_median - classical_median)
        if classical_median is not None and mcnn_median is not None
        else None,
        "supportive": supported,
    }


def run_eval(
    repo: Path,
    theta: dict[str, Any],
    docs: Path,
    env: dict[str, str],
    run_timeout: int,
    safety_config: Path,
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    tag = theta["tag"]
    run_dir = docs / "evals" / tag
    run_dir.mkdir(parents=True, exist_ok=True)
    theta_path = run_dir / f"{tag}.json"
    write_json(theta_path, theta)

    outputs: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    for controller in ["classical", "mcnn"]:
        print(f"RUN_CONTROLLER={controller} TAG={tag}", flush=True)
        outputs[controller] = run_one(repo, theta_path, theta, controller, run_dir, env, run_timeout, safety_config)
        metrics[controller] = load_json(Path(outputs[controller]["metrics"]))

    record = {
        "tag": tag,
        "seed": theta.get("seed"),
        "role": theta.get("mcnn_gate3", {}).get("role"),
        "theta": theta,
        "metrics": metrics,
        "outputs": {controller: {key: str(value) for key, value in paths.items()} for controller, paths in outputs.items()},
    }
    attach_gate3_fields(record, baseline)
    write_json(run_dir / "record.json", record)
    return record


def selected_attacks(names: str | None, max_attacks: int) -> list[AttackCase]:
    max_attacks = min(max_attacks, 3)
    attacks = DEFAULT_ATTACKS
    if names:
        requested = [name.strip() for name in names.split(",") if name.strip()]
        by_tag = {case.tag: case for case in DEFAULT_ATTACKS}
        missing = sorted(set(requested) - set(by_tag))
        if missing:
            raise ValueError(f"unknown attack tag(s): {', '.join(missing)}")
        attacks = [by_tag[name] for name in requested]
    return attacks[:max_attacks]


def write_summary(docs: Path, payload: dict[str, Any]) -> None:
    baseline = payload.get("baseline_summary", {})
    attacks = payload.get("attack_summaries", [])
    decision = payload.get("decision", {})
    lines = [
        "# mc_nn_control GATE-3 Position-Error Amplitude Probe",
        "",
        f"decision: {decision.get('exit')}",
        f"run_id: `{payload.get('run_id')}`",
        f"scope: {payload.get('scope')}",
        f"attack_theta_count: {payload.get('attack_theta_count')} / {payload.get('attack_theta_budget')}",
        f"primary_bug_confirmed: {str(decision.get('primary_bug_confirmed')).lower()}",
        "",
        "## Step 0 Baseline",
        "",
        "| controller | tracking RMS mean m | tracking RMS stdev m | samples |",
        "|---|---:|---:|---:|",
    ]
    for controller in ["classical", "mcnn"]:
        stats = baseline.get(controller, {}).get("tracking_error_rms_m", {})
        values = stats.get("values") or []
        lines.append(
            f"| {controller} | {stats.get('mean')} | {stats.get('stdev')} | {len(values)} |"
        )
    lines.extend(
        [
            "",
            "## Attack Results",
            "",
            "| theta | seeds | primary seeds | flight quadrants | classical D3 median | mc_nn D3 median | mc_nn z median | D3 supportive | max error C/M median m |",
            "|---|---:|---:|---|---:|---:|---:|---|---:|",
        ]
    )
    for item in attacks:
        max_classical = finite_values([record["metrics"]["classical"].get("tracking_error_max_m") for record in item["records"]])
        max_mcnn = finite_values([record["metrics"]["mcnn"].get("tracking_error_max_m") for record in item["records"]])
        d3 = item.get("d3_support", {})
        quadrants = ",".join(sorted({record["flight"]["flight_quadrant"] for record in item["records"]}))
        lines.append(
            "| {theta} | {seeds} | {primary} | {quadrants} | {cratio} | {mratio} | {mz} | {supportive} | {cmax}/{mmax} |".format(
                theta=item.get("case", {}).get("tag"),
                seeds=len(item.get("records", [])),
                primary=item.get("primary_seed_count"),
                quadrants=quadrants,
                cratio=d3.get("classical_ratio_median"),
                mratio=d3.get("mcnn_ratio_median"),
                mz=d3.get("mcnn_z_median"),
                supportive=str(d3.get("supportive")).lower(),
                cmax=median(max_classical) if max_classical else None,
                mmax=median(max_mcnn) if max_mcnn else None,
            )
        )
    lines.extend(
        [
            "",
            "## Decision Matrix Exit",
            "",
            decision.get("rationale", ""),
            "",
            "ULOGs are written under this directory but are ignored by git. Per-run `record.json` files contain the ULOG paths, flight quadrant, and D3 ratios.",
        ]
    )
    (docs / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (docs.parent / "mcnn_gonogo_gate3_20260625.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="mcnn_gonogo_gate3_20260625")
    parser.add_argument("--docs-root", type=Path, default=m1.repo_root() / "docs")
    parser.add_argument("--run-timeout", type=int, default=160)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-baseline", action="store_true")
    parser.add_argument("--attacks")
    parser.add_argument("--max-attacks", type=int, default=3)
    parser.add_argument("--min-go-seeds", type=int, default=2)
    parser.add_argument("--safety-config", type=Path, default=m1.repo_root() / "config/m2_safety_envelope.json")
    args = parser.parse_args()

    repo = m1.repo_root()
    docs = (args.docs_root / args.run_id).resolve()
    docs.mkdir(parents=True, exist_ok=True)
    env = m1.agent_env(repo)
    if not args.skip_build:
        build_env = env.copy()
        build_env["PX4_MCNN_SIH_BUILD_LOG"] = str(docs / "px4_mcnn_sih_build.log")
        m1.run_checked([str(repo / "scripts/build_px4_mcnn_sih.sh")], cwd=repo, log=docs / "build.log", env=build_env)
    else:
        m1.run_checked([str(repo / "scripts/install_mcnn_sih_board.sh")], cwd=repo, log=docs / "build.log", env=env)
        m1.run_checked([str(repo / "scripts/install_m1_sih_x500.sh")], cwd=repo, log=docs / "build.log", env=env)

    baseline_path = docs / "baseline.json"
    if args.skip_baseline:
        baseline_records = load_json(baseline_path)["records"]
        baseline_summary = load_json(baseline_path)["summary"]
    else:
        baseline_records = []
        for seed in BASELINE_SEEDS:
            theta = baseline_theta(args.run_id, seed)
            record = run_eval(repo, theta, docs, env, args.run_timeout, args.safety_config, baseline=None)
            baseline_records.append(record)
            baseline_summary = summarize_baseline(baseline_records)
            write_json(
                baseline_path,
                {"records": [compact_record(record) for record in baseline_records], "summary": baseline_summary},
            )
        baseline_summary = summarize_baseline(baseline_records)
        write_json(
            baseline_path,
            {"records": [compact_record(record) for record in baseline_records], "summary": baseline_summary},
        )

    attack_summaries: list[dict[str, Any]] = []
    attack_theta_count = 0
    decision = {
        "exit": "NO-GO",
        "primary_bug_confirmed": False,
        "rationale": (
            "NO-GO: no tested position-error amplitude theta produced multi-seed mc_nn_control flight-unsafe "
            "behavior with classical control-level flight-safe. This is only a position-error amplitude result, "
            "not a global mc_nn_control robustness result."
        ),
    }
    payload: dict[str, Any] = {
        "run_id": args.run_id,
        "scope": "position-error amplitude channel only; no setpoint staleness, velocity, angular-velocity, shim, or RAPTOR run",
        "baseline_seeds": BASELINE_SEEDS,
        "attack_seeds": ATTACK_SEEDS,
        "attack_theta_budget": min(args.max_attacks, 3),
        "attack_theta_count": attack_theta_count,
        "baseline_summary": baseline_summary,
        "baseline_records": baseline_records,
        "attack_summaries": attack_summaries,
        "decision": decision,
    }
    write_json(docs / "results.json", compact_payload(payload))
    write_summary(docs, payload)

    for case in selected_attacks(args.attacks, args.max_attacks):
        records = []
        attack_theta_count += 1
        for seed in ATTACK_SEEDS:
            theta = attack_theta(args.run_id, case, seed)
            record = run_eval(repo, theta, docs, env, args.run_timeout, args.safety_config, baseline_summary)
            records.append(record)
        primary_count = sum(1 for record in records if record["flight"]["primary_bug"])
        support = d3_support(records)
        attack_summary = {
            "case": asdict(case),
            "records": records,
            "primary_seed_count": primary_count,
            "d3_support": support,
        }
        attack_summaries.append(attack_summary)
        if primary_count >= args.min_go_seeds and support.get("supportive"):
            decision = {
                "exit": "GO",
                "primary_bug_confirmed": True,
                "rationale": (
                    f"GO: {case.tag} produced mc_nn_control flight-unsafe behavior in {primary_count} seeds while "
                    "classical remained control-level flight-safe, and D3 ratios were supportive. Recommend committing "
                    "a full campaign next; RAPTOR should be used as the robust comparison group."
                ),
            }
            payload["decision"] = decision
            break
        payload["attack_theta_count"] = attack_theta_count
        write_json(docs / "results.json", compact_payload(payload))
        write_summary(docs, payload)

    payload["attack_theta_count"] = attack_theta_count
    payload["decision"] = decision
    write_json(docs / "results.json", compact_payload(payload))
    write_summary(docs, payload)
    print(f"RESULTS={docs / 'results.json'}")
    print(f"SUMMARY={docs / 'summary.md'}")
    print(f"MAIN_DOC={docs.parent / 'mcnn_gonogo_gate3_20260625.md'}")
    print(f"DECISION={decision['exit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
