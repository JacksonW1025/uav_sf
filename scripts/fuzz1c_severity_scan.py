#!/usr/bin/env python3
"""FUZZ-1c severity scan for mc_nn violent activation.

This is a Method-A runner: SIH groundtruth topics trigger the handoff, and the
post-switch ULOG is graded on an ordinal severity ladder instead of a binary
hit/no-hit detector.
"""

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
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
from pyulog import ULog

import fuzz1_activation_mcnn as fuzz1
import fuzz1b_locked_activation as f1b
import m1_diff_runner as m1
import mcnn_gate3_position_error_probe as gate3
from m1_metrics import quaternion, quat_to_roll_pitch, vector3


RUN_ID = "fuzz1c_severity_20260625"

SEVERITY_LABELS = {
    0: "S0_clean_recovery",
    1: "S1_controlled_degraded_survival",
    2: "S2_controlled_safe_failure",
    3: "S3_uncontrolled_tumble_or_loc",
    4: "S4_numeric_or_software_fault",
}

SEVERITY_THRESHOLDS = {
    "s3_roll_pitch_deg": 90.0,
    "s3_angular_rate_rad_s": 8.0,
    "s2_ground_contact_agl_m": 0.25,
    "s0_last_window_s": 2.0,
    "s0_roll_pitch_deg": 40.0,
    "s0_angular_rate_rad_s": 1.0,
    "s0_final_error_m": 1.5,
    "s0_min_altitude_agl_m": 1.0,
    "method_a_roll_pitch_tolerance_deg": 8.0,
    "method_a_rate_tolerance_rad_s": 0.45,
}


@dataclass(frozen=True)
class SeverityCase:
    tag: str
    radius_m: float
    frequency_hz: float
    phase_rad: float
    roll_pitch_min_deg: float
    roll_pitch_max_deg: float
    rate_min_rad_s: float
    rate_max_rad_s: float
    wind_n: float = 0.0
    wind_e: float = 0.0
    setup_profile: str = "relaxed_limits"
    trigger_start_s: float = 18.0
    trigger_deadline_s: float = 54.0
    trajectory_start_s: float = 16.0
    mission_end_s: float = 68.0
    stage: str = "attitude_rate_grid"


SCAN_CASES = [
    SeverityCase(
        "rp48_62_rate2p45_2p90_w6_r6_f045",
        6.0,
        0.45,
        0.0,
        48.0,
        62.0,
        2.45,
        2.90,
        wind_n=6.0,
        stage="high_fuZZ1b_anchor",
    ),
    SeverityCase(
        "rp40_48_rate2p00_2p55_w0_r6_f045",
        6.0,
        0.45,
        0.0,
        40.0,
        48.0,
        2.00,
        2.55,
        stage="classical_43deg_benchmark",
    ),
    SeverityCase(
        "rp36_44_rate1p55_2p15_w3_r4_f038",
        4.0,
        0.38,
        0.0,
        36.0,
        44.0,
        1.55,
        2.15,
        wind_n=3.0,
        stage="through_43deg",
    ),
    SeverityCase(
        "rp32_40_rate1p30_1p95_w0_r4_f038",
        4.0,
        0.38,
        0.0,
        32.0,
        40.0,
        1.30,
        1.95,
        stage="below_43deg",
    ),
    SeverityCase(
        "rp25_34_rate0p80_1p45_w3_r2p5_f032",
        2.5,
        0.32,
        0.0,
        25.0,
        34.0,
        0.80,
        1.45,
        wind_n=3.0,
        stage="low_attitude",
    ),
    SeverityCase(
        "rp22_32_rate0p55_1p30_w0_r2p5_f032",
        2.5,
        0.32,
        0.0,
        22.0,
        32.0,
        0.55,
        1.30,
        stage="low_attitude",
    ),
    SeverityCase(
        "rp18_30_rate0p40_1p20_w3_r1p8_f025",
        1.8,
        0.25,
        0.0,
        18.0,
        30.0,
        0.40,
        1.20,
        wind_n=3.0,
        stage="low_attitude_fallback",
    ),
    SeverityCase(
        "rp12_28_rate0p25_1p00_w0_r1p8_f025",
        1.8,
        0.25,
        0.0,
        12.0,
        28.0,
        0.25,
        1.00,
        stage="low_attitude_fallback",
    ),
]


def write_json(path: Path, payload: Any) -> None:
    fuzz1.write_json(path, payload)


def append_jsonl(path: Path, payload: Any) -> None:
    fuzz1.append_jsonl(path, payload)


def load_json(path: Path) -> dict[str, Any]:
    return fuzz1.load_json(path)


def finite_float(value: float | np.floating[Any] | None) -> float | None:
    if value is None:
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def expected_tilt_deg(case: SeverityCase) -> float:
    lateral_accel = case.radius_m * (2.0 * math.pi * case.frequency_hz) ** 2
    return math.degrees(math.atan2(lateral_accel, 9.80665))


def theta_for_case(run_id: str, case: SeverityCase, seed: int) -> dict[str, Any]:
    tag = f"{run_id}_{case.tag}_s{seed}"
    boot_params = dict(fuzz1.COMMON_BOOT_PARAMS)
    if case.wind_n or case.wind_e:
        boot_params["SIH_WIND_N"] = case.wind_n
        boot_params["SIH_WIND_E"] = case.wind_e
    return {
        "tag": tag,
        "description": (
            "FUZZ-1c mc_nn_control severity scan: classical Offboard circle approach, "
            "SIH groundtruth state-triggered switch, post-switch hover recovery."
        ),
        "seed": int(seed),
        "airframe": {"sim": "sih", "model": "sihsim_x500_v2", "sys_autostart": 10046},
        "timing": {
            "approach_start_s": 12.0,
            "controller_switch_s": case.trigger_deadline_s,
            "trajectory_start_s": case.trajectory_start_s,
            "mission_end_s": case.mission_end_s,
            "mode_command_repeat_s": 0.5,
            "mode_command_timeout_s": 8.0,
            "px4_shutdown_margin_s": 8.0,
            "px4_shutdown_wall_slack_s": 22.0,
            "external_mode_id": 23,
        },
        "setpoint": {
            "rate_hz": 80.0,
            "max_wall_timer_hz": 800.0,
            "hover_ned": [0.0, 0.0, -2.5],
            "yaw_rad": 0.0,
            "type": "circle",
            "feedforward": True,
            "circle": {
                "radius_m": case.radius_m,
                "frequency_hz": case.frequency_hz,
                "phase_rad": case.phase_rad,
                "z_amplitude_m": 0.0,
            },
            "activation_trigger": {
                "enabled": True,
                "method": "SIH groundtruth threshold crossing",
                "start_s": case.trigger_start_s,
                "deadline_s": case.trigger_deadline_s,
                "roll_pitch_abs_min_deg": case.roll_pitch_min_deg,
                "roll_pitch_abs_max_deg": case.roll_pitch_max_deg,
                "angular_rate_norm_min_rad_s": case.rate_min_rad_s,
                "angular_rate_norm_max_rad_s": case.rate_max_rad_s,
                "max_topic_age_s": 0.25,
            },
            "post_switch": {
                "type": "hover",
                "hover_ned": [0.0, 0.0, -2.5],
            },
        },
        "boot_px4_params": boot_params,
        "px4_params": {**fuzz1.COMMON_PX4_PARAMS, **fuzz1.setup_params(case.setup_profile)},
        "environment": {
            "fuzz_family": "violent_activation_severity",
            "state_control_method": "A_state_triggered_switch",
            "case": asdict(case),
            "expected_lateral_accel_m_s2": case.radius_m * (2.0 * math.pi * case.frequency_hz) ** 2,
            "expected_tilt_deg": expected_tilt_deg(case),
            "severity_thresholds": SEVERITY_THRESHOLDS,
            "reachability": (
                "Classical Offboard circle approach creates the switch state. Relaxed limits, when used, "
                "are IC setup only; the post-switch judgment is controlled versus uncontrolled outcome."
            ),
            "uses_state_shim": False,
        },
        "faults": [],
        "sensor_perturbations": [],
        "safe_thresholds": {
            "tracking_error_max_m": 8.0,
            "tracking_error_rms_m": 4.0,
            "final_error_m": 4.0,
            "roll_pitch_max_deg": 75.0,
            "angular_rate_max_rad_s": 8.0,
            "motor_saturation_ratio_max": 0.99,
            "min_altitude_agl_m": 0.25,
        },
        "divergence_thresholds": {"position_divergence_m": 2.0},
    }


def first_existing_dataset(ulog: ULog, names: list[str]):
    for name in names:
        dataset = f1b.first_dataset(ulog, name)
        if dataset is not None:
            return dataset
    return None


def mask_window(ts: np.ndarray, start_us: int | None, end_us: int | None) -> np.ndarray:
    return fuzz1.mask_window(ts, start_us, end_us)


def nav_active_us(ulog: ULog, nav_state: int, after_us: int) -> int | None:
    return f1b.nav_active_us(ulog, nav_state, after_us)


def task_event_us(task: dict[str, Any], name: str) -> int | None:
    return f1b.task_event_us(task, name)


def task_event(task: dict[str, Any], name: str) -> dict[str, Any] | None:
    return f1b.task_event(task, name)


def latest_window_mask(ts: np.ndarray, start_us: int | None, mission_end_us: int | None, window_s: float) -> np.ndarray:
    if len(ts) == 0:
        return np.zeros(0, dtype=bool)
    end = int(mission_end_us) if mission_end_us is not None else int(ts[-1])
    start = max(int(start_us or ts[0]), int(end - window_s * 1e6))
    return mask_window(ts, start, end)


def nonfinite_matrix_summary(matrix: np.ndarray | None, timestamps: np.ndarray | None = None) -> dict[str, Any]:
    return fuzz1.nonfinite_summary(matrix, timestamps)


def field_matrix(dataset: Any, prefix: str, count: int, mask: np.ndarray | None = None) -> np.ndarray | None:
    return fuzz1.field_matrix(dataset, prefix, count, mask)


def severity_evidence(
    ulog: ULog,
    outputs: dict[str, Path],
    controller: str,
    theta: dict[str, Any],
    task: dict[str, Any],
    switch_us: int,
) -> dict[str, Any]:
    mission_end_us = int(ulog.last_timestamp)
    target_nav = 23 if controller == "mcnn" else 14
    active_us = nav_active_us(ulog, target_nav, switch_us)
    analysis_start_us = active_us if controller == "mcnn" and active_us is not None else switch_us
    hover = theta.get("setpoint", {}).get("post_switch", {}).get("hover_ned", [0.0, 0.0, -2.5])

    evidence: dict[str, Any] = {
        "controller": controller,
        "switch_us": switch_us,
        "analysis_start_us": analysis_start_us,
        "controller_active_us": active_us,
        "mission_end_us": mission_end_us,
        "console": fuzz1.console_faults(Path(outputs["console"])),
        "task_exit_code": task.get("exit_code"),
        "mode_confirmed": bool(task.get("mode_confirmed")),
        "mission_end_reached": task_event(task, "mission_end") is not None,
        "post_switch_hover_ned": hover,
    }

    if evidence["console"]["fault"]:
        evidence.setdefault("software_fault_reasons", []).append("px4_console_fault")

    neural = f1b.first_dataset(ulog, "neural_control")
    if controller == "mcnn" and neural is not None:
        nts = neural.data["timestamp"].astype(np.int64)
        nmask = mask_window(nts, analysis_start_us, mission_end_us)
        network = field_matrix(neural, "network_output", 4, nmask)
        observation = field_matrix(neural, "observation", 15, nmask)
        evidence["neural_control_samples"] = int(np.count_nonzero(nmask))
        evidence["network_output_nonfinite"] = nonfinite_matrix_summary(network, nts[nmask] if np.any(nmask) else None)
        evidence["observation_nonfinite"] = nonfinite_matrix_summary(observation, nts[nmask] if np.any(nmask) else None)
        if evidence["network_output_nonfinite"]["nonfinite_count"]:
            evidence.setdefault("software_fault_reasons", []).append("neural_control_network_output_nonfinite")
    elif controller == "mcnn" and bool(task.get("mode_confirmed")):
        evidence.setdefault("software_fault_reasons", []).append("missing_neural_control_topic")

    motors = f1b.first_dataset(ulog, "actuator_motors")
    if motors is not None:
        mts = motors.data["timestamp"].astype(np.int64)
        mmask = mask_window(mts, analysis_start_us, mission_end_us)
        active = field_matrix(motors, "control", fuzz1.ACTIVE_MOTORS, mmask)
        evidence["active_motor_nonfinite"] = nonfinite_matrix_summary(active, mts[mmask] if np.any(mmask) else None)
        if evidence["active_motor_nonfinite"]["nonfinite_count"]:
            evidence.setdefault("software_fault_reasons", []).append("actuator_motors_active_nonfinite")
        if active is not None and active.size:
            finite = np.isfinite(active)
            finite_count = int(np.count_nonzero(finite))
            if finite_count:
                sat = finite & ((active <= 0.02) | (active >= 0.98) | (np.abs(active) >= 0.98))
                evidence["active_motor_saturation_ratio"] = float(np.count_nonzero(sat)) / float(finite_count)
                evidence["active_motor_saturation_count"] = int(np.count_nonzero(sat))

    status = f1b.first_dataset(ulog, "vehicle_status")
    if status is not None:
        sts = status.data["timestamp"].astype(np.int64)
        smask = mask_window(sts, switch_us, mission_end_us)
        if np.any(smask):
            evidence["post_switch_disarmed"] = bool(np.any(status.data["arming_state"].astype(int)[smask] != 2))
            evidence["post_switch_failsafe"] = bool(np.any(status.data["failsafe"].astype(bool)[smask]))
            evidence["post_switch_nav_states"] = sorted(
                {int(value) for value in status.data["nav_state"].astype(int)[smask].tolist()}
            )

    att = first_existing_dataset(ulog, ["vehicle_attitude_groundtruth", "vehicle_attitude"])
    if att is not None:
        ats = att.data["timestamp"].astype(np.int64)
        amask = mask_window(ats, analysis_start_us, mission_end_us)
        if np.any(amask):
            q = quaternion(att.data)[amask]
            finite_q = np.all(np.isfinite(q), axis=1)
            roll, pitch = quat_to_roll_pitch(q)
            rp = np.maximum(np.abs(roll), np.abs(pitch))
            evidence["attitude_topic"] = att.name
            evidence["attitude_quaternion_finite"] = bool(np.all(finite_q))
            evidence["post_switch_roll_pitch_max_deg"] = finite_float(np.rad2deg(np.nanmax(rp)))
            lmask = latest_window_mask(ats, analysis_start_us, mission_end_us, SEVERITY_THRESHOLDS["s0_last_window_s"])
            if np.any(lmask):
                lq = quaternion(att.data)[lmask]
                lroll, lpitch = quat_to_roll_pitch(lq)
                lrp = np.maximum(np.abs(lroll), np.abs(lpitch))
                evidence["last_window_roll_pitch_max_deg"] = finite_float(np.rad2deg(np.nanmax(lrp)))
                evidence["last_roll_deg"] = finite_float(np.rad2deg(lroll[-1]))
                evidence["last_pitch_deg"] = finite_float(np.rad2deg(lpitch[-1]))
        else:
            evidence["attitude_topic"] = att.name

    rates = first_existing_dataset(ulog, ["vehicle_angular_velocity_groundtruth", "vehicle_angular_velocity"])
    if rates is not None:
        rts = rates.data["timestamp"].astype(np.int64)
        rmask = mask_window(rts, analysis_start_us, mission_end_us)
        if np.any(rmask):
            omega = vector3(rates.data, "xyz")[rmask]
            omega_norm = np.linalg.norm(omega, axis=1)
            evidence["angular_velocity_topic"] = rates.name
            evidence["post_switch_angular_rate_max_rad_s"] = finite_float(np.nanmax(omega_norm))
            lmask = latest_window_mask(rts, analysis_start_us, mission_end_us, SEVERITY_THRESHOLDS["s0_last_window_s"])
            if np.any(lmask):
                lomega = vector3(rates.data, "xyz")[lmask]
                lnorm = np.linalg.norm(lomega, axis=1)
                evidence["last_window_angular_rate_max_rad_s"] = finite_float(np.nanmax(lnorm))
                evidence["last_angular_rate_norm_rad_s"] = finite_float(lnorm[-1])
        else:
            evidence["angular_velocity_topic"] = rates.name

    lpos = first_existing_dataset(ulog, ["vehicle_local_position_groundtruth", "vehicle_local_position"])
    if lpos is not None:
        lts = lpos.data["timestamp"].astype(np.int64)
        lmask = mask_window(lts, analysis_start_us, mission_end_us)
        if np.any(lmask):
            pos = np.column_stack([lpos.data["x"], lpos.data["y"], lpos.data["z"]]).astype(float)[lmask]
            evidence["local_position_topic"] = lpos.name
            evidence["post_switch_min_altitude_agl_m"] = finite_float(np.nanmin(-pos[:, 2]))
            evidence["last_position_ned_m"] = [finite_float(value) for value in pos[-1].tolist()]
            if len(hover) == 3:
                target = np.asarray(hover, dtype=float)
                err = np.linalg.norm(pos - target, axis=1)
                evidence["final_error_to_hover_m"] = finite_float(err[-1])
                evidence["post_switch_error_to_hover_max_m"] = finite_float(np.nanmax(err))
        else:
            evidence["local_position_topic"] = lpos.name

    return evidence


def classify_severity(evidence: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    severity = 0

    software_faults = sorted(set(evidence.get("software_fault_reasons") or []))
    if software_faults or evidence.get("attitude_quaternion_finite") is False:
        reasons.extend(software_faults)
        if evidence.get("attitude_quaternion_finite") is False:
            reasons.append("attitude_quaternion_nonfinite")
        severity = 4
    else:
        rp_max = evidence.get("post_switch_roll_pitch_max_deg")
        rate_max = evidence.get("post_switch_angular_rate_max_rad_s")
        if rp_max is not None and rp_max >= SEVERITY_THRESHOLDS["s3_roll_pitch_deg"]:
            reasons.append("attitude_tumble_over_90deg")
            severity = max(severity, 3)
        if rate_max is not None and rate_max >= SEVERITY_THRESHOLDS["s3_angular_rate_rad_s"]:
            reasons.append("angular_rate_loss_of_control")
            severity = max(severity, 3)

        if severity < 3:
            if evidence.get("post_switch_failsafe"):
                reasons.append("failsafe")
            if evidence.get("post_switch_disarmed"):
                reasons.append("unexpected_disarm")
            min_agl = evidence.get("post_switch_min_altitude_agl_m")
            if min_agl is not None and min_agl < SEVERITY_THRESHOLDS["s2_ground_contact_agl_m"]:
                reasons.append("ground_contact_post_switch")
            if reasons:
                severity = max(severity, 2)

    if severity == 0:
        clean = True
        checks = [
            (
                "last_window_roll_pitch_max_deg",
                SEVERITY_THRESHOLDS["s0_roll_pitch_deg"],
                "last_window_attitude_above_s0",
            ),
            (
                "last_window_angular_rate_max_rad_s",
                SEVERITY_THRESHOLDS["s0_angular_rate_rad_s"],
                "last_window_rate_above_s0",
            ),
            ("final_error_to_hover_m", SEVERITY_THRESHOLDS["s0_final_error_m"], "final_hover_error_above_s0"),
        ]
        for key, threshold, reason in checks:
            value = evidence.get(key)
            if value is None or float(value) > threshold:
                clean = False
                reasons.append(reason)
        min_agl = evidence.get("post_switch_min_altitude_agl_m")
        if min_agl is None or float(min_agl) < SEVERITY_THRESHOLDS["s0_min_altitude_agl_m"]:
            clean = False
            reasons.append("minimum_altitude_below_s0")
        severity = 0 if clean else 1

    controlled = severity <= 2
    return {
        "severity": severity,
        "severity_label": SEVERITY_LABELS[severity],
        "controlled": controlled,
        "uncontrolled": severity >= 3,
        "reasons": sorted(set(reasons)),
        "thresholds": SEVERITY_THRESHOLDS,
    }


def run_one_fuzz1c(
    repo: Path,
    theta_path: Path,
    theta: dict[str, Any],
    controller: str,
    run_dir: Path,
    env: dict[str, str],
    run_timeout_s: int,
    safety_config: Path,
) -> tuple[dict[str, Path], dict[str, Any]]:
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
    metrics_log = run_dir / f"{prefix}_metrics.log"

    for path in [console_log, agent_log, topics_log, task_log, metrics_log]:
        path.write_text("", encoding="utf-8")

    if not (build_dir / "bin/px4").exists():
        raise FileNotFoundError(f"PX4 binary missing: {build_dir / 'bin/px4'}")

    gate3.write_logger_topics(run_root)
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

    outputs = {
        "ulog": copied_ulog,
        "metrics": metrics_json,
        "task": task_json,
        "console": console_log,
        "agent": agent_log,
        "topics": topics_log,
    }
    meta: dict[str, Any] = {"task_rc": None, "px4_rc": None, "nonzero_task_exit": False, "ulog_copied": False}

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
        cmd_tmp.write(gate3.px4_command_script(theta, controller, sim_speed_factor))
        cmd_tmp.close()

        with console_log.open("w", encoding="utf-8") as console_handle, open(
            cmd_tmp.name, "r", encoding="utf-8"
        ) as stdin:
            console_handle.write(f"# FUZZ-1c PX4 console controller={controller} tag={tag}\n")
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

            meta["task_rc"] = int(task_rc)
            console_handle.write(f"\n# task_rc={task_rc}\n")
            console_handle.flush()

            if task_rc == 0:
                try:
                    px4_rc = px4.wait(timeout=45)
                except subprocess.TimeoutExpired as exc:
                    m1.terminate_process(px4)
                    raise RuntimeError(f"PX4 did not shut down after task for {controller}") from exc
                meta["px4_rc"] = int(px4_rc)
                console_handle.write(f"\n# px4_rc={px4_rc}\n")
            else:
                meta["nonzero_task_exit"] = True
                console_handle.write("\n# nonzero task exit; terminating PX4 early for fail-loud trigger result\n")
                console_handle.flush()
                m1.terminate_process(px4)

        ulog = m1.latest_ulog(log_root)
        if ulog is not None:
            shutil.copy2(ulog, copied_ulog)
            meta["ulog_copied"] = True
            if task_json.exists():
                try:
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
                        log=metrics_log,
                        env=env,
                    )
                    meta["metrics_rc"] = 0
                except subprocess.CalledProcessError as exc:
                    meta["metrics_rc"] = int(exc.returncode)
                    meta["metrics_error"] = repr(exc)
        elif task_rc == 0:
            raise RuntimeError(f"No ULOG found under {log_root}")

        return outputs, meta
    finally:
        m1.terminate_process(task)
        m1.terminate_process(px4)
        m1.terminate_process(agent)
        if cmd_tmp is not None:
            try:
                Path(cmd_tmp.name).unlink()
            except FileNotFoundError:
                pass


def augment_record(record: dict[str, Any], outputs: dict[str, Path]) -> None:
    if not Path(outputs["task"]).exists():
        record["state_trigger"] = {"enabled": True, "fired": False, "missing_task_json": True}
        return
    task = load_json(Path(outputs["task"]))
    record["state_trigger"] = {
        "enabled": bool(task.get("state_trigger_enabled")),
        "fired": bool(task.get("state_trigger_fired")),
        "state": task.get("state_trigger_state"),
        "max_observed": task.get("state_trigger_max_observed"),
        "event": task_event(task, "state_trigger"),
        "timeout_event": task_event(task, "state_trigger_timeout"),
        "task_exit_code": task.get("exit_code"),
    }
    if not Path(outputs["ulog"]).exists():
        record["trigger_ulog_match"] = {"matched": False, "reason": "missing_ulog"}
        record["exact_switch_state"] = {"switch_us": None}
        return
    try:
        ulog = ULog(str(outputs["ulog"]))
        switch_us, match = f1b.matched_switch_us_from_trigger(ulog, task.get("state_trigger_state"))
        if switch_us is None:
            switch_us = task_event_us(task, "post_switch_setpoint") or task_event_us(task, "state_trigger")
        record["trigger_ulog_match"] = match
        record["exact_switch_state"] = f1b.exact_switch_state(ulog, switch_us)
    except Exception as exc:
        record["trigger_ulog_match"] = {"matched": False, "error": repr(exc)}
        record["exact_switch_state"] = {"switch_us": None, "error": repr(exc)}


def run_controller_eval(
    repo: Path,
    docs: Path,
    run_id: str,
    case: SeverityCase,
    seed: int,
    controller: str,
    env: dict[str, str],
    run_timeout: int,
    safety_config: Path,
) -> dict[str, Any]:
    theta = theta_for_case(run_id, case, seed)
    eval_dir = docs / "evals" / theta["tag"]
    eval_dir.mkdir(parents=True, exist_ok=True)
    theta_path = eval_dir / f"{theta['tag']}.json"
    write_json(theta_path, theta)
    print(f"RUN_CONTROLLER={controller} CASE={case.tag} SEED={seed}", flush=True)
    try:
        outputs, meta = run_one_fuzz1c(repo, theta_path, theta, controller, eval_dir, env, run_timeout, safety_config)
        record: dict[str, Any] = {
            "controller": controller,
            "outputs": {key: str(value) for key, value in outputs.items()},
            "runner_meta": meta,
            "metrics": load_json(outputs["metrics"]) if outputs["metrics"].exists() else {},
            "run_error": None,
        }
        augment_record(record, outputs)
        switch_us = record.get("exact_switch_state", {}).get("switch_us")
        trigger_fired = bool(record.get("state_trigger", {}).get("fired"))
        if isinstance(switch_us, int) and trigger_fired and outputs["ulog"].exists():
            task = load_json(outputs["task"])
            ulog = ULog(str(outputs["ulog"]))
            evidence = severity_evidence(ulog, outputs, controller, theta, task, switch_us)
            record["severity_evidence"] = evidence
            record["severity"] = classify_severity(evidence)
        elif not trigger_fired:
            record["severity"] = {
                "severity": None,
                "severity_label": "UNTESTED_TRIGGER_NOT_FIRED",
                "controlled": None,
                "uncontrolled": None,
                "reasons": ["state_trigger_not_fired"],
                "thresholds": SEVERITY_THRESHOLDS,
            }
            record["severity_evidence"] = {}
    except Exception as exc:
        prefix = f"mcnn_gate3_{theta['tag']}_{controller}"
        console = eval_dir / f"{prefix}_px4_console.log"
        record = {
            "controller": controller,
            "outputs": {"console": str(console)},
            "runner_meta": {},
            "metrics": {},
            "severity": {
                "severity": None,
                "severity_label": "UNTESTED_HARNESS_ERROR",
                "controlled": None,
                "uncontrolled": None,
                "reasons": ["harness_exception"],
                "harness_exception": repr(exc),
                "console": fuzz1.console_faults(console),
                "thresholds": SEVERITY_THRESHOLDS,
            },
            "severity_evidence": {},
            "state_trigger": {"enabled": True, "fired": False, "error": repr(exc)},
            "exact_switch_state": {},
            "trigger_ulog_match": {"matched": False, "error": repr(exc)},
            "run_error": repr(exc),
        }
    record["theta"] = theta
    record["case"] = asdict(case)
    record["seed"] = int(seed)
    record["tag"] = theta["tag"]
    write_json(eval_dir / f"{controller}_record.json", record)
    return record


def compact_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "controller": record.get("controller"),
        "tag": record.get("tag"),
        "seed": record.get("seed"),
        "case": record.get("case", {}).get("tag"),
        "stage": record.get("case", {}).get("stage"),
        "run_error": record.get("run_error"),
        "runner_meta": record.get("runner_meta"),
        "severity": record.get("severity"),
        "severity_evidence": record.get("severity_evidence"),
        "state_trigger": record.get("state_trigger"),
        "trigger_ulog_match": record.get("trigger_ulog_match"),
        "exact_switch_state": record.get("exact_switch_state"),
        "outputs": record.get("outputs"),
    }


def state_residual(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    residual = f1b.state_residual(a, b)
    residual["within_method_a_tolerance"] = (
        residual.get("roll_pitch_abs_deg") is not None
        and residual["roll_pitch_abs_deg"] <= SEVERITY_THRESHOLDS["method_a_roll_pitch_tolerance_deg"]
        and residual.get("angular_rate_norm_rad_s") is not None
        and residual["angular_rate_norm_rad_s"] <= SEVERITY_THRESHOLDS["method_a_rate_tolerance_rad_s"]
    )
    return residual


def classify_pair(mcnn_record: dict[str, Any], classical_record: dict[str, Any]) -> dict[str, Any]:
    residual = state_residual(
        mcnn_record.get("exact_switch_state", {}),
        classical_record.get("exact_switch_state", {}),
    )
    both_triggered = bool(mcnn_record.get("state_trigger", {}).get("fired")) and bool(
        classical_record.get("state_trigger", {}).get("fired")
    )
    msev = mcnn_record.get("severity", {}).get("severity")
    csev = classical_record.get("severity", {}).get("severity")
    valid = (
        both_triggered
        and mcnn_record.get("run_error") is None
        and classical_record.get("run_error") is None
        and isinstance(msev, int)
        and isinstance(csev, int)
        and bool(residual.get("within_method_a_tolerance"))
    )
    wide = bool(valid and msev >= 3 and csev <= 2)
    strict = bool(valid and msev >= 3 and csev <= 1)
    s2_vs_s3 = bool(valid and msev >= 3 and csev == 2)
    return {
        "valid_matched_pair": valid,
        "both_triggered": both_triggered,
        "state_residual": residual,
        "mcnn_severity": msev,
        "mcnn_severity_label": mcnn_record.get("severity", {}).get("severity_label"),
        "classical_severity": csev,
        "classical_severity_label": classical_record.get("severity", {}).get("severity_label"),
        "mcnn_reasons": mcnn_record.get("severity", {}).get("reasons"),
        "classical_reasons": classical_record.get("severity", {}).get("reasons"),
        "clean_differential_wide_s0s2_vs_s3s4": wide,
        "clean_differential_strict_s0s1_vs_s3s4": strict,
        "controlled_failure_vs_uncontrolled": s2_vs_s3,
        "too_hard_uncontrolled": bool(valid and msev >= 3 and csev >= 3),
        "both_controlled": bool(valid and msev <= 2 and csev <= 2),
    }


def run_pair(
    repo: Path,
    docs: Path,
    run_id: str,
    case: SeverityCase,
    seed: int,
    env: dict[str, str],
    run_timeout: int,
    safety_config: Path,
) -> dict[str, Any]:
    mcnn_record = run_controller_eval(repo, docs, run_id, case, seed, "mcnn", env, run_timeout, safety_config)
    classical_record = run_controller_eval(repo, docs, run_id, case, seed, "classical", env, run_timeout, safety_config)
    pair = {
        "mcnn": compact_record(mcnn_record),
        "classical": compact_record(classical_record),
        "classification": classify_pair(mcnn_record, classical_record),
    }
    append_jsonl(docs / "results.jsonl", {"type": "pair", "pair": pair})
    return pair


def summarize_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [pair for pair in pairs if pair["classification"].get("valid_matched_pair")]
    rp_values = [
        pair["mcnn"].get("exact_switch_state", {}).get("roll_pitch_abs_deg")
        for pair in valid
        if pair["mcnn"].get("exact_switch_state", {}).get("roll_pitch_abs_deg") is not None
    ]
    return {
        "pair_count": len(pairs),
        "valid_pair_count": len(valid),
        "wide_clean_differential_count": sum(
            1 for pair in valid if pair["classification"].get("clean_differential_wide_s0s2_vs_s3s4")
        ),
        "strict_clean_differential_count": sum(
            1 for pair in valid if pair["classification"].get("clean_differential_strict_s0s1_vs_s3s4")
        ),
        "s2_vs_s3_count": sum(1 for pair in valid if pair["classification"].get("controlled_failure_vs_uncontrolled")),
        "untested_count": sum(1 for pair in pairs if not pair["classification"].get("both_triggered")),
        "min_valid_mcnn_roll_pitch_abs_deg": min(rp_values) if rp_values else None,
        "max_valid_mcnn_roll_pitch_abs_deg": max(rp_values) if rp_values else None,
        "rate_residual_mean_rad_s": mean(
            [
                pair["classification"]["state_residual"]["angular_rate_norm_rad_s"]
                for pair in valid
                if pair["classification"]["state_residual"].get("angular_rate_norm_rad_s") is not None
            ]
        )
        if any(pair["classification"]["state_residual"].get("angular_rate_norm_rad_s") is not None for pair in valid)
        else None,
    }


def decide(payload: dict[str, Any]) -> dict[str, Any]:
    pairs = payload.get("pairs", [])
    wide = [pair for pair in pairs if pair["classification"].get("clean_differential_wide_s0s2_vs_s3s4")]
    strict = [pair for pair in pairs if pair["classification"].get("clean_differential_strict_s0s1_vs_s3s4")]
    if wide:
        best = strict[0] if strict else wide[0]
        cls = best["classification"]
        return {
            "status": "CLEAN_DIFFERENTIAL",
            "rationale": (
                "Found matched-state severity differential: classical severity "
                f"{cls.get('classical_severity_label')} and mc_nn severity {cls.get('mcnn_severity_label')}."
            ),
            "strict_primary_available": bool(strict),
            "s2_vs_s3_only": not bool(strict),
            "case": best["mcnn"].get("case"),
        }

    summary = summarize_pairs(pairs)
    coverage = bool(summary.get("valid_pair_count")) and (
        summary.get("min_valid_mcnn_roll_pitch_abs_deg") is not None
        and float(summary["min_valid_mcnn_roll_pitch_abs_deg"]) <= 32.0
    )
    return {
        "status": "DOWNGRADE",
        "rationale": (
            "No matched pair showed classical controlled (S0-S2) with mc_nn uncontrolled (S3-S4)."
            if coverage
            else "No clean differential was found, but coverage is incomplete because some low-attitude trigger buckets remain untested."
        ),
        "coverage_complete_for_downgrade": coverage,
    }


def fmt_float(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    try:
        fvalue = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(fvalue):
        return "-"
    return f"{fvalue:.{digits}f}"


def write_summary(docs: Path, payload: dict[str, Any]) -> None:
    decision = payload["decision"]
    pairs = payload.get("pairs", [])
    valid_pairs = [pair for pair in pairs if pair["classification"].get("valid_matched_pair")]
    wide_pairs = [pair for pair in valid_pairs if pair["classification"].get("clean_differential_wide_s0s2_vs_s3s4")]
    strict_pairs = [
        pair for pair in valid_pairs if pair["classification"].get("clean_differential_strict_s0s1_vs_s3s4")
    ]
    mcnn_s3_states = [
        pair["mcnn"].get("exact_switch_state", {})
        for pair in wide_pairs
        if pair["mcnn"].get("exact_switch_state", {}).get("roll_pitch_abs_deg") is not None
    ]
    mcnn_s0_states = [
        pair["mcnn"].get("exact_switch_state", {})
        for pair in valid_pairs
        if pair["classification"].get("mcnn_severity") == 0
        and pair["mcnn"].get("exact_switch_state", {}).get("roll_pitch_abs_deg") is not None
    ]
    lines = [
        f"decision: {decision['status']}",
        "",
        "# FUZZ-1c Severity Scan",
        "",
        f"run_id: `{payload['run_id']}`",
        "method: Method A, SIH groundtruth state-triggered switch",
        "state_shim: not used",
        "",
        "## Decision",
        "",
        decision.get("rationale", ""),
        "",
        "## Interpretation",
        "",
        (
            "This is a wide-clean differential: classical is controlled S2 while mc_nn is uncontrolled S3. "
            "No strict classical S0/S1 vs mc_nn S3 point was found in this scan."
            if wide_pairs and not strict_pairs
            else "A strict classical S0/S1 vs mc_nn S3 point was found."
            if strict_pairs
            else "No severity differential was found."
        ),
        "",
        (
            "Observed S2-vs-S3 band: mc_nn S3 switch states span "
            f"{fmt_float(min(state['roll_pitch_abs_deg'] for state in mcnn_s3_states), 2)}-"
            f"{fmt_float(max(state['roll_pitch_abs_deg'] for state in mcnn_s3_states), 2)} deg and "
            f"{fmt_float(min(state['angular_rate_norm_rad_s'] for state in mcnn_s3_states), 2)}-"
            f"{fmt_float(max(state['angular_rate_norm_rad_s'] for state in mcnn_s3_states), 2)} rad/s."
            if mcnn_s3_states
            else "Observed S2-vs-S3 band: none."
        ),
        (
            "Low-severity coverage reached mc_nn S0 at "
            f"{fmt_float(min(state['roll_pitch_abs_deg'] for state in mcnn_s0_states), 2)} deg / "
            f"{fmt_float(min(state['angular_rate_norm_rad_s'] for state in mcnn_s0_states), 2)} rad/s "
            "and included valid matched points below 25-30 deg."
            if mcnn_s0_states
            else "Low-severity coverage did not produce a valid S0 point."
        ),
        "One no-wind low bucket is explicitly UNTESTED because the approach never entered its 22-32 deg trigger window; it is not used as no-hit evidence.",
        "",
        "## Severity Ladder",
        "",
        "- S0: clean recovery; final hover error, attitude, rate, and altitude back inside the S0 thresholds.",
        "- S1: controlled degraded survival; no failsafe/ground/tumble, but not clean S0.",
        "- S2: controlled safe failure; bounded attitude/rate but failsafe, disarm, or ground contact.",
        "- S3: uncontrolled loss of control; roll/pitch >= 90 deg or angular-rate norm >= 8 rad/s.",
        "- S4: numerical/software fault; console fault or active nonfinite controller/motor output.",
        "",
        f"thresholds_json: `{docs.name}/severity_thresholds.json`",
        "",
        "## Pairs",
        "",
        "| idx | case | valid | mc_nn switch rp/rate | classical switch rp/rate | residual rp/rate | mc_nn severity | classical severity | differential | reasons |",
        "|---:|---|---|---:|---:|---:|---|---|---|---|",
    ]
    for idx, pair in enumerate(payload.get("pairs", []), start=1):
        cls = pair["classification"]
        m_state = pair["mcnn"].get("exact_switch_state", {})
        c_state = pair["classical"].get("exact_switch_state", {})
        resid = cls.get("state_residual", {})
        diff = "strict" if cls.get("clean_differential_strict_s0s1_vs_s3s4") else (
            "S2-vs-S3" if cls.get("controlled_failure_vs_uncontrolled") else "-"
        )
        reasons = "mc_nn=" + ",".join(cls.get("mcnn_reasons") or [])
        reasons += "; classical=" + ",".join(cls.get("classical_reasons") or [])
        lines.append(
            "| {idx} | {case} | {valid} | {mrp}/{mrate} | {crp}/{crate} | {rrp}/{rrate} | {msev} | {csev} | {diff} | {reasons} |".format(
                idx=idx,
                case=pair["mcnn"].get("case"),
                valid=str(cls.get("valid_matched_pair")).lower(),
                mrp=fmt_float(m_state.get("roll_pitch_abs_deg"), 2),
                mrate=fmt_float(m_state.get("angular_rate_norm_rad_s"), 2),
                crp=fmt_float(c_state.get("roll_pitch_abs_deg"), 2),
                crate=fmt_float(c_state.get("angular_rate_norm_rad_s"), 2),
                rrp=fmt_float(resid.get("roll_pitch_abs_deg"), 2),
                rrate=fmt_float(resid.get("angular_rate_norm_rad_s"), 2),
                msev=cls.get("mcnn_severity_label"),
                csev=cls.get("classical_severity_label"),
                diff=diff,
                reasons=reasons,
            )
        )
    lines.extend(
        [
            "",
            "## Coverage",
            "",
            json.dumps(payload.get("pair_summary", {}), indent=2, sort_keys=True),
            "",
            "## Validity",
            "",
            "Trigger timeouts are marked UNTESTED and are not used as safe/no-hit evidence. ULOG switch states are matched back to groundtruth by value, and the Method-A residual is reported per pair.",
            "",
            "## Artifacts",
            "",
            f"results_json: `{docs.name}/results.json`",
            f"results_jsonl: `{docs.name}/results.jsonl`",
            f"eval_dir: `{docs.name}/evals`",
        ]
    )
    text = "\n".join(lines) + "\n"
    (docs / "summary.md").write_text(text, encoding="utf-8")
    (docs.parent / f"{payload['run_id']}.md").write_text(text, encoding="utf-8")


def build_if_needed(repo: Path, docs: Path, env: dict[str, str], rebuild: bool) -> None:
    fuzz1.build_if_needed(repo, docs, env, skip_build=not rebuild)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--docs-root", type=Path, default=m1.repo_root() / "docs")
    parser.add_argument("--run-timeout", type=int, default=210)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--seed-base", type=int, default=20261800)
    parser.add_argument("--max-scan-cases", type=int, default=len(SCAN_CASES))
    parser.add_argument("--confirm-runs", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--continue-after-wide", action="store_true")
    parser.add_argument("--safety-config", type=Path, default=m1.repo_root() / "config/m2_safety_envelope.json")
    args = parser.parse_args()

    repo = m1.repo_root()
    docs = (args.docs_root / args.run_id).resolve()
    docs.mkdir(parents=True, exist_ok=True)
    env = m1.agent_env(repo)
    build_if_needed(repo, docs, env, args.rebuild)
    write_json(docs / "severity_thresholds.json", SEVERITY_THRESHOLDS)

    results_path = docs / "results.json"
    if args.resume and results_path.exists():
        payload = load_json(results_path)
        payload["severity_ladder"] = SEVERITY_LABELS
        payload["severity_thresholds"] = SEVERITY_THRESHOLDS
        payload["scan_cases"] = [asdict(case) for case in SCAN_CASES[: max(1, args.max_scan_cases)]]
    else:
        payload = {
            "run_id": args.run_id,
            "severity_ladder": SEVERITY_LABELS,
            "severity_thresholds": SEVERITY_THRESHOLDS,
            "scan_cases": [asdict(case) for case in SCAN_CASES[: max(1, args.max_scan_cases)]],
            "pairs": [],
            "pair_summary": {},
            "decision": {
                "status": "DOWNGRADE",
                "rationale": "No FUZZ-1c pairs have run yet.",
                "coverage_complete_for_downgrade": False,
            },
        }

    differential_case: SeverityCase | None = None
    completed_cases = {pair.get("mcnn", {}).get("case") for pair in payload.get("pairs", [])}
    for idx, case in enumerate(SCAN_CASES[: max(1, args.max_scan_cases)]):
        if case.tag in completed_cases:
            continue
        pair = run_pair(repo, docs, args.run_id, case, args.seed_base + idx, env, args.run_timeout, args.safety_config)
        payload["pairs"].append(pair)
        payload["pair_summary"] = summarize_pairs(payload["pairs"])
        payload["decision"] = decide(payload)
        write_json(docs / "results.json", payload)
        write_summary(docs, payload)
        if (
            pair["classification"].get("clean_differential_wide_s0s2_vs_s3s4")
            and not args.continue_after_wide
        ):
            differential_case = case
            break

    if differential_case is not None and args.confirm_runs > 1:
        for offset in range(1, max(1, args.confirm_runs)):
            confirm_case = replace(differential_case, tag=f"{differential_case.tag}_confirm{offset}")
            if confirm_case.tag in completed_cases:
                continue
            confirm_pair = run_pair(
                repo,
                docs,
                args.run_id,
                confirm_case,
                args.seed_base + 100 + offset,
                env,
                args.run_timeout,
                args.safety_config,
            )
            payload["pairs"].append(confirm_pair)
            payload["pair_summary"] = summarize_pairs(payload["pairs"])
            payload["decision"] = decide(payload)
            write_json(docs / "results.json", payload)
            write_summary(docs, payload)

    payload["pair_summary"] = summarize_pairs(payload["pairs"])
    payload["decision"] = decide(payload)
    write_json(docs / "results.json", payload)
    write_summary(docs, payload)
    print(f"DECISION={payload['decision']['status']}")
    print(f"SUMMARY={docs / 'summary.md'}")
    print(f"MAIN_DOC={docs.parent / f'{args.run_id}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
