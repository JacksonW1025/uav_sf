#!/usr/bin/env python3
"""FUZZ-1 violent activation fuzzing for mc_nn_control.

The search is intentionally mc_nn-first: run the neural controller with a wide
detector, then run the classical controller only for detector hits to classify
attribution. Tracking lag alone is not a finding in this harness.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
from pyulog import ULog

import m1_diff_runner as m1
import mcnn_gate3_position_error_probe as gate3
from m1_metrics import quaternion, quat_to_roll_pitch, vector3


RUN_ID = "fuzz1_activation_20260625"
ACTIVE_MOTORS = 4
FLIGHT_UNSAFE_REASONS = {
    "unexpected_disarm",
    "failsafe",
    "ground_contact",
    "attitude_quaternion_nonfinite",
    "attitude_diverged",
    "angular_rate_diverged",
    "active_motor_nan",
    "motor_saturation",
}
TRACKING_ONLY_REASONS = {"tracking_error_max", "tracking_error_rms", "task_not_complete"}
CONSOLE_FAULT_RE = re.compile(
    r"(ASSERT|assert|PANIC|Segmentation fault|Aborted|Bus error|Hardfault|Fatal|Invoke\(\) failed|tensor is null)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ActivationCase:
    tag: str
    radius_m: float
    frequency_hz: float
    phase_rad: float
    wind_n: float = 0.0
    wind_e: float = 0.0
    switch_s: float = 29.0
    trajectory_start_s: float = 16.0
    mission_end_s: float = 43.0
    setup_profile: str = "relaxed_limits"
    feedforward: bool = True
    stage: str = "phase1_extreme_corner"


RELAXED_SETUP_PARAMS: dict[str, float] = {
    "MPC_TILTMAX_AIR": 89.0,
    "MPC_TILTMAX_LND": 45.0,
    "MC_ROLLRATE_MAX": 1200.0,
    "MC_PITCHRATE_MAX": 1200.0,
    "MC_YAWRATE_MAX": 720.0,
    "MPC_ACC_HOR": 15.0,
    "MPC_ACC_HOR_MAX": 15.0,
    "MPC_JERK_AUTO": 80.0,
    "MPC_JERK_MAX": 500.0,
    "MPC_XY_VEL_MAX": 20.0,
    "MPC_XY_CRUISE": 20.0,
    "MPC_XY_ERR_MAX": 10.0,
    "MPC_XY_TRAJ_P": 1.0,
}

HOT_SETUP_PARAMS: dict[str, float] = {
    **RELAXED_SETUP_PARAMS,
    "MPC_XY_P": 2.0,
    "MPC_XY_VEL_P_ACC": 5.0,
    "MPC_XY_VEL_I_ACC": 2.0,
    "MPC_XY_VEL_D_ACC": 0.4,
}

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

PHASE1_CASES = [
    ActivationCase("corner_r6_f045_w6_n_phase0", 6.0, 0.45, 0.0, wind_n=6.0),
    ActivationCase("corner_r7_f050_w8_e_phase90", 7.0, 0.50, math.pi / 2.0, wind_e=8.0),
    ActivationCase("corner_r8_f050_w8_cross_phase180", 8.0, 0.50, math.pi, wind_n=6.0, wind_e=6.0),
    ActivationCase("corner_r5_f060_w10_n_phase270", 5.0, 0.60, 3.0 * math.pi / 2.0, wind_n=10.0),
    ActivationCase("corner_r4_f070_w6_e_phase45", 4.0, 0.70, math.pi / 4.0, wind_e=6.0),
    ActivationCase("corner_r10_f040_w12_n_phase135", 10.0, 0.40, 3.0 * math.pi / 4.0, wind_n=12.0),
    ActivationCase("corner_r6_f055_w0_phase225", 6.0, 0.55, 5.0 * math.pi / 4.0),
    ActivationCase("corner_r8_f035_w8_neg_phase315", 8.0, 0.35, 7.0 * math.pi / 4.0, wind_n=-8.0),
    ActivationCase("hot_r6_f050_w8_n_phase0", 6.0, 0.50, 0.0, wind_n=8.0, setup_profile="hot_limits"),
    ActivationCase("hot_r5_f065_w10_cross_phase90", 5.0, 0.65, math.pi / 2.0, wind_n=7.0, wind_e=-7.0, setup_profile="hot_limits"),
    ActivationCase("realistic_r4p5_f038_w6_n", 4.5, 0.38, 0.0, wind_n=6.0, setup_profile="nominal_limits"),
    ActivationCase("realistic_r6_f032_w8_e", 6.0, 0.32, math.pi / 2.0, wind_e=8.0, setup_profile="nominal_limits"),
]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sanitize(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.floating):
        fvalue = float(value)
        return fvalue if math.isfinite(fvalue) else None
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(sanitize(payload), handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def first_dataset(ulog: ULog, name: str):
    matches = [dataset for dataset in ulog.data_list if dataset.name == name]
    return matches[0] if matches else None


def field_matrix(dataset: Any, prefix: str, count: int, mask: np.ndarray | None = None) -> np.ndarray | None:
    columns = []
    for idx in range(count):
        field = f"{prefix}[{idx}]"
        if field not in dataset.data:
            return None
        values = dataset.data[field].astype(float)
        if mask is not None:
            values = values[mask]
        columns.append(values)
    if not columns:
        return None
    return np.column_stack(columns)


def mask_window(ts: np.ndarray, start_us: int | None, end_us: int | None) -> np.ndarray:
    mask = np.ones(len(ts), dtype=bool)
    if start_us is not None:
        mask &= ts >= int(start_us)
    if end_us is not None:
        mask &= ts <= int(end_us)
    return mask


def finite_max(values: list[float | None]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return max(finite) if finite else None


def finite_median(values: list[float | None]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return float(median(finite)) if finite else None


def setup_params(profile: str) -> dict[str, float]:
    if profile == "nominal_limits":
        return {}
    if profile == "relaxed_limits":
        return dict(RELAXED_SETUP_PARAMS)
    if profile == "hot_limits":
        return dict(HOT_SETUP_PARAMS)
    raise ValueError(f"unknown setup profile {profile}")


def expected_tilt_deg(case: ActivationCase) -> float:
    lateral_accel = case.radius_m * (2.0 * math.pi * case.frequency_hz) ** 2
    return math.degrees(math.atan2(lateral_accel, 9.80665))


def theta_for_case(run_id: str, case: ActivationCase, seed: int) -> dict[str, Any]:
    tag = f"{run_id}_{case.tag}_s{seed}"
    boot_params = dict(COMMON_BOOT_PARAMS)
    if case.wind_n or case.wind_e:
        boot_params["SIH_WIND_N"] = case.wind_n
        boot_params["SIH_WIND_E"] = case.wind_e
    px4_params = {**COMMON_PX4_PARAMS, **setup_params(case.setup_profile)}
    return {
        "tag": tag,
        "description": (
            "FUZZ-1 mc_nn_control violent activation: classical Offboard circle approach, "
            "wind disturbance, switch to controller mode 23, then restore hover."
        ),
        "seed": int(seed),
        "airframe": {"sim": "sih", "model": "sihsim_x500_v2", "sys_autostart": 10046},
        "timing": {
            "approach_start_s": 12.0,
            "controller_switch_s": case.switch_s,
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
            "feedforward": case.feedforward,
            "circle": {
                "radius_m": case.radius_m,
                "frequency_hz": case.frequency_hz,
                "phase_rad": case.phase_rad,
                "z_amplitude_m": 0.0,
            },
            "post_switch": {
                "type": "hover",
                "hover_ned": [0.0, 0.0, -2.5],
            },
        },
        "boot_px4_params": boot_params,
        "px4_params": px4_params,
        "environment": {
            "fuzz_family": "violent_activation",
            "case": asdict(case),
            "expected_lateral_accel_m_s2": case.radius_m * (2.0 * math.pi * case.frequency_hz) ** 2,
            "expected_tilt_deg": expected_tilt_deg(case),
            "reachability": (
                "Classical Offboard setup with SIH wind. setup_profile records whether PX4 approach limits "
                "were relaxed only to create the initial condition; the post-switch judgment is on mc_nn_control."
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


def console_faults(console_path: Path) -> dict[str, Any]:
    if not console_path.exists():
        return {"fault": False, "matches": [], "px4_timeout_rc": False}
    text = console_path.read_text(encoding="utf-8", errors="replace")
    matches = []
    for line in text.splitlines():
        if CONSOLE_FAULT_RE.search(line):
            matches.append(line.strip())
    return {
        "fault": bool(matches),
        "matches": matches[:20],
        "px4_timeout_rc": "# px4_rc=124" in text,
    }


def nonfinite_summary(matrix: np.ndarray | None, timestamps: np.ndarray | None = None) -> dict[str, Any]:
    if matrix is None or matrix.size == 0:
        return {"samples": 0, "nonfinite_count": 0, "first_nonfinite": None}
    finite = np.isfinite(matrix)
    bad = ~finite
    result: dict[str, Any] = {
        "samples": int(matrix.shape[0]),
        "nonfinite_count": int(np.count_nonzero(bad)),
        "nan_count": int(np.count_nonzero(np.isnan(matrix))),
        "posinf_count": int(np.count_nonzero(matrix == np.inf)),
        "neginf_count": int(np.count_nonzero(matrix == -np.inf)),
        "first_nonfinite": None,
    }
    if np.any(bad):
        row, col = np.argwhere(bad)[0]
        result["first_nonfinite"] = {
            "row": int(row),
            "column": int(col),
            "timestamp_us": int(timestamps[row]) if timestamps is not None and len(timestamps) > row else None,
            "row_values": [float(v) if math.isfinite(float(v)) else str(float(v)) for v in matrix[row].tolist()],
        }
    return result


def task_event_us(task: dict[str, Any], name: str) -> int | None:
    for event in task.get("events") or []:
        if event.get("name") == name and isinstance(event.get("timestamp_us"), int):
            return int(event["timestamp_us"])
    return None


def task_event_elapsed_s(task: dict[str, Any], name: str) -> float | None:
    for event in task.get("events") or []:
        if event.get("name") == name and event.get("elapsed_s") is not None:
            return float(event["elapsed_s"])
    return None


def switch_time_us(task: dict[str, Any], theta: dict[str, Any], metrics: dict[str, Any]) -> int | None:
    origin_us = metrics.get("task_to_ulog_origin_us")
    if isinstance(origin_us, int):
        elapsed_s = task_event_elapsed_s(task, "post_switch_setpoint")
        if elapsed_s is None:
            elapsed_s = float(theta["timing"]["controller_switch_s"])
        return int(origin_us + elapsed_s * 1e6)
    return None


def switch_context(
    ulog: ULog,
    switch_us: int | None,
    mission_end_us: int | None,
    controller_active_us: int | None,
    pre_s: float = 0.5,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "switch_us": switch_us,
        "controller_active_us": controller_active_us,
        "mission_end_us": mission_end_us,
        "pre_window_s": pre_s,
    }
    if switch_us is None:
        return result

    pre_start_us = int(switch_us - pre_s * 1e6)
    att = first_dataset(ulog, "vehicle_attitude")
    rates = first_dataset(ulog, "vehicle_angular_velocity")
    lpos = first_dataset(ulog, "vehicle_local_position")

    if att is not None:
        ts = att.data["timestamp"].astype(np.int64)
        pre = mask_window(ts, pre_start_us, switch_us)
        post = mask_window(ts, switch_us, mission_end_us)
        if np.any(pre):
            q = quaternion(att.data)[pre]
            roll, pitch = quat_to_roll_pitch(q)
            rp = np.maximum(np.abs(roll), np.abs(pitch))
            result["pre_switch_roll_pitch_max_deg"] = float(np.rad2deg(np.nanmax(rp)))
            result["pre_switch_roll_pitch_mean_deg"] = float(np.rad2deg(np.nanmean(rp)))
            result["pre_switch_attitude_samples"] = int(np.count_nonzero(pre))
        if np.any(post):
            q = quaternion(att.data)[post]
            roll, pitch = quat_to_roll_pitch(q)
            rp = np.maximum(np.abs(roll), np.abs(pitch))
            result["post_switch_roll_pitch_max_deg"] = float(np.rad2deg(np.nanmax(rp)))

    if rates is not None:
        ts = rates.data["timestamp"].astype(np.int64)
        pre = mask_window(ts, pre_start_us, switch_us)
        post = mask_window(ts, switch_us, mission_end_us)
        if np.any(pre):
            omega = vector3(rates.data, "xyz")[pre]
            norm = np.linalg.norm(omega, axis=1)
            result["pre_switch_angular_rate_max_rad_s"] = float(np.nanmax(norm))
            result["pre_switch_angular_rate_mean_rad_s"] = float(np.nanmean(norm))
            for axis, field in enumerate(["x", "y", "z"]):
                result[f"pre_switch_angular_rate_{field}_max_abs_rad_s"] = float(np.nanmax(np.abs(omega[:, axis])))
            result["pre_switch_angular_rate_samples"] = int(np.count_nonzero(pre))
        if np.any(post):
            omega = vector3(rates.data, "xyz")[post]
            result["post_switch_angular_rate_max_rad_s"] = float(np.nanmax(np.linalg.norm(omega, axis=1)))

    if lpos is not None:
        ts = lpos.data["timestamp"].astype(np.int64)
        post = mask_window(ts, switch_us, mission_end_us)
        if np.any(post):
            result["post_switch_min_altitude_agl_m"] = float(np.nanmin(-lpos.data["z"][post].astype(float)))
            result["post_switch_position_samples"] = int(np.count_nonzero(post))

    return result


def analyze_run(
    outputs: dict[str, Path],
    controller: str,
    theta: dict[str, Any],
    safety_config: Path,
) -> dict[str, Any]:
    metrics = load_json(Path(outputs["metrics"]))
    task = load_json(Path(outputs["task"]))
    ulog = ULog(str(outputs["ulog"]))
    active_us = metrics.get("controller_active_us")
    mission_end_us = metrics.get("mission_end_us")
    if not isinstance(active_us, int):
        active_us = task.get("controller_active_us")
    if not isinstance(mission_end_us, int):
        mission_end_us = task.get("mission_end_us")
    switch_us = switch_time_us(task, theta, metrics)
    analysis_start_us = active_us if controller == "mcnn" and isinstance(active_us, int) else switch_us

    detector: dict[str, Any] = {
        "controller": controller,
        "hit": False,
        "severity": 0,
        "severity_label": "none",
        "hit_reasons": [],
        "tracking_only_reasons_ignored": sorted(set(metrics.get("safe_reasons") or []) & TRACKING_ONLY_REASONS),
        "console": console_faults(Path(outputs["console"])),
        "source_map": {
            "observation": "mc_nn_control.cpp PopulateInputTensor() fills _input_data; neural_control.cpp publish loop copies it.",
            "network_output": "mc_nn_control.cpp RescaleActions() mutates output tensor before neural_control.network_output publish.",
            "actuator_motors": "mc_nn_control.cpp PublishOutput() writes active actuator_motors.control[0..3].",
        },
    }
    if detector["console"]["fault"]:
        detector["hit_reasons"].append("px4_console_fault")
        detector["severity"] = max(detector["severity"], 4)

    neural = first_dataset(ulog, "neural_control")
    if neural is not None and analysis_start_us is not None:
        nts = neural.data["timestamp"].astype(np.int64)
        nmask = mask_window(nts, analysis_start_us, mission_end_us)
        detector["neural_control_samples"] = int(np.count_nonzero(nmask))
        network = field_matrix(neural, "network_output", 4, nmask)
        observation = field_matrix(neural, "observation", 15, nmask)
        detector["network_output_nonfinite"] = nonfinite_summary(network, nts[nmask] if np.any(nmask) else None)
        detector["observation_nonfinite"] = nonfinite_summary(observation, nts[nmask] if np.any(nmask) else None)
        if detector["network_output_nonfinite"]["nonfinite_count"]:
            detector["hit_reasons"].append("neural_control_network_output_nonfinite")
            detector["severity"] = max(detector["severity"], 4)
    elif controller == "mcnn":
        detector["hit_reasons"].append("missing_neural_control_topic")
        detector["severity"] = max(detector["severity"], 2)

    motors = first_dataset(ulog, "actuator_motors")
    if motors is not None and analysis_start_us is not None:
        mts = motors.data["timestamp"].astype(np.int64)
        mmask = mask_window(mts, analysis_start_us, mission_end_us)
        active = field_matrix(motors, "control", ACTIVE_MOTORS, mmask)
        detector["active_motor_nonfinite"] = nonfinite_summary(active, mts[mmask] if np.any(mmask) else None)
        if detector["active_motor_nonfinite"]["nonfinite_count"]:
            detector["hit_reasons"].append("actuator_motors_active_nonfinite")
            detector["severity"] = max(detector["severity"], 4)
        if active is not None and active.size:
            finite = np.isfinite(active)
            finite_count = int(np.count_nonzero(finite))
            if finite_count:
                sat = finite & ((active <= 0.02) | (active >= 0.98) | (np.abs(active) >= 0.98))
                detector["active_motor_saturation_ratio"] = float(np.count_nonzero(sat)) / float(finite_count)
                detector["active_motor_saturation_count"] = int(np.count_nonzero(sat))
                if detector["active_motor_saturation_ratio"] > theta.get("safe_thresholds", {}).get(
                    "motor_saturation_ratio_max", 0.99
                ):
                    detector["hit_reasons"].append("motor_saturation")
                    detector["severity"] = max(detector["severity"], 2)

    context = switch_context(ulog, switch_us, mission_end_us, active_us)

    status = first_dataset(ulog, "vehicle_status")
    if status is not None and switch_us is not None:
        sts = status.data["timestamp"].astype(np.int64)
        smask = mask_window(sts, switch_us, mission_end_us)
        if np.any(smask):
            disarmed = bool(np.any(status.data["arming_state"].astype(int)[smask] != 2))
            failsafe = bool(np.any(status.data["failsafe"].astype(bool)[smask]))
            detector["post_switch_disarmed"] = disarmed
            detector["post_switch_failsafe"] = failsafe
            if disarmed:
                detector["hit_reasons"].append("unexpected_disarm")
                detector["severity"] = max(detector["severity"], 2)
            if failsafe:
                detector["hit_reasons"].append("failsafe")
                detector["severity"] = max(detector["severity"], 2)

    if (
        context.get("post_switch_roll_pitch_max_deg") is not None
        and context["post_switch_roll_pitch_max_deg"] > theta.get("safe_thresholds", {}).get("roll_pitch_max_deg", 75.0)
    ):
        detector["hit_reasons"].append("attitude_loss_of_control")
        detector["severity"] = max(detector["severity"], 3)
    if (
        context.get("post_switch_angular_rate_max_rad_s") is not None
        and context["post_switch_angular_rate_max_rad_s"]
        > theta.get("safe_thresholds", {}).get("angular_rate_max_rad_s", 8.0)
    ):
        detector["hit_reasons"].append("angular_rate_loss_of_control")
        detector["severity"] = max(detector["severity"], 3)
    if (
        context.get("post_switch_min_altitude_agl_m") is not None
        and context["post_switch_min_altitude_agl_m"] < theta.get("safe_thresholds", {}).get("min_altitude_agl_m", 0.25)
    ):
        detector["hit_reasons"].append("ground_contact_post_switch")
        detector["severity"] = max(detector["severity"], 2)

    detector["hit_reasons"] = sorted(set(detector["hit_reasons"]))
    detector["hit"] = detector["severity"] > 0
    detector["severity_label"] = {0: "none", 2: "medium", 3: "high", 4: "highest"}.get(
        detector["severity"], "unknown"
    )

    return {
        "controller": controller,
        "outputs": {key: str(value) for key, value in outputs.items()},
        "metrics": compact_metrics(metrics),
        "detector": detector,
        "switch_context": context,
        "safety_config": str(safety_config),
    }


def compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = [
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
        "disarmed_in_window",
        "failsafe_in_window",
    ]
    return {key: metrics.get(key) for key in keys if key in metrics}


def run_controller_eval(
    repo: Path,
    docs: Path,
    run_id: str,
    case: ActivationCase,
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
        outputs = gate3.run_one(repo, theta_path, theta, controller, eval_dir, env, run_timeout, safety_config)
        record = analyze_run(outputs, controller, theta, safety_config)
        record["run_error"] = None
    except Exception as exc:  # Keep harness failures explicit; do not silently promote them to PX4 crashes.
        prefix = f"mcnn_gate3_{theta['tag']}_{controller}"
        console = eval_dir / f"{prefix}_px4_console.log"
        record = {
            "controller": controller,
            "outputs": {"console": str(console)},
            "metrics": {},
            "detector": {
                "controller": controller,
                "hit": False,
                "severity": 0,
                "severity_label": "harness_error",
                "hit_reasons": [],
                "console": console_faults(console),
                "harness_exception": repr(exc),
            },
            "switch_context": {},
            "run_error": repr(exc),
        }
        if record["detector"]["console"]["fault"]:
            record["detector"]["hit"] = True
            record["detector"]["severity"] = 4
            record["detector"]["severity_label"] = "highest"
            record["detector"]["hit_reasons"] = ["px4_console_fault_after_harness_exception"]
    record["theta"] = theta
    record["case"] = asdict(case)
    record["seed"] = int(seed)
    record["tag"] = theta["tag"]
    write_json(eval_dir / f"{controller}_record.json", record)
    return record


def classify_pair(mcnn_record: dict[str, Any], classical_record: dict[str, Any]) -> dict[str, Any]:
    mcnn_detector = mcnn_record["detector"]
    classical_detector = classical_record["detector"]
    mcnn_reasons = set(mcnn_detector.get("hit_reasons") or [])
    nn_only = bool(
        mcnn_reasons
        & {
            "neural_control_network_output_nonfinite",
            "px4_console_fault",
            "px4_console_fault_after_harness_exception",
            "missing_neural_control_topic",
        }
    )
    classical_hit = bool(classical_detector.get("hit"))
    differential = bool(mcnn_detector.get("hit")) and not classical_hit
    if differential:
        label = "differential_primary_bug"
    elif nn_only:
        label = "nn_only_numerical_or_software_primary_bug"
    elif bool(mcnn_detector.get("hit")) and classical_hit:
        label = "too_hard_not_primary"
    else:
        label = "no_mcnn_hit"
    return {
        "label": label,
        "primary_bug": label in {"differential_primary_bug", "nn_only_numerical_or_software_primary_bug"},
        "mcnn_hit": bool(mcnn_detector.get("hit")),
        "classical_hit": classical_hit,
        "nn_only_mode": nn_only,
        "mcnn_severity": mcnn_detector.get("severity"),
        "classical_severity": classical_detector.get("severity"),
        "mcnn_reasons": sorted(mcnn_reasons),
        "classical_reasons": sorted(classical_detector.get("hit_reasons") or []),
    }


def fitness(record: dict[str, Any]) -> float:
    detector = record.get("detector", {})
    ctx = record.get("switch_context", {})
    metrics = record.get("metrics", {})
    score = float(detector.get("severity") or 0) * 10000.0
    score += float(ctx.get("pre_switch_roll_pitch_max_deg") or 0.0) * 10.0
    score += float(ctx.get("pre_switch_angular_rate_max_rad_s") or 0.0) * 100.0
    score += float(metrics.get("motor_saturation_ratio") or 0.0) * 50.0
    return score


def descriptor_bin(record: dict[str, Any]) -> tuple[int, int]:
    ctx = record.get("switch_context", {})
    attitude = float(ctx.get("pre_switch_roll_pitch_max_deg") or 0.0)
    rate = float(ctx.get("pre_switch_angular_rate_max_rad_s") or 0.0)
    return int(min(9, attitude // 10.0)), int(min(9, rate // 1.0))


def mutate_case(parent: ActivationCase, rng: random.Random, index: int) -> ActivationCase:
    radius = min(10.0, max(3.5, parent.radius_m + rng.uniform(-1.5, 1.5)))
    frequency = min(0.75, max(0.30, parent.frequency_hz + rng.uniform(-0.10, 0.10)))
    wind_n = min(12.0, max(-12.0, parent.wind_n + rng.uniform(-4.0, 4.0)))
    wind_e = min(12.0, max(-12.0, parent.wind_e + rng.uniform(-4.0, 4.0)))
    phase = (parent.phase_rad + rng.choice([-math.pi / 2.0, -math.pi / 4.0, 0.0, math.pi / 4.0, math.pi / 2.0])) % (
        2.0 * math.pi
    )
    profile = parent.setup_profile if rng.random() < 0.8 else rng.choice(["relaxed_limits", "hot_limits"])
    return replace(
        parent,
        tag=f"map_e{index:04d}_r{radius:.2f}_f{frequency:.2f}",
        radius_m=radius,
        frequency_hz=frequency,
        phase_rad=phase,
        wind_n=wind_n,
        wind_e=wind_e,
        setup_profile=profile,
        stage="phase2_map_elites",
    )


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    mcnn_records = [record for record in records if record["controller"] == "mcnn"]
    return {
        "eval_count_mcnn": len(mcnn_records),
        "hit_count_mcnn": sum(1 for record in mcnn_records if record["detector"].get("hit")),
        "max_pre_switch_roll_pitch_deg": finite_max(
            [record.get("switch_context", {}).get("pre_switch_roll_pitch_max_deg") for record in mcnn_records]
        ),
        "max_pre_switch_angular_rate_rad_s": finite_max(
            [record.get("switch_context", {}).get("pre_switch_angular_rate_max_rad_s") for record in mcnn_records]
        ),
        "median_pre_switch_roll_pitch_deg": finite_median(
            [record.get("switch_context", {}).get("pre_switch_roll_pitch_max_deg") for record in mcnn_records]
        ),
        "median_pre_switch_angular_rate_rad_s": finite_median(
            [record.get("switch_context", {}).get("pre_switch_angular_rate_max_rad_s") for record in mcnn_records]
        ),
    }


def write_summary(docs: Path, payload: dict[str, Any]) -> None:
    decision = payload["decision"]
    summary = payload.get("coverage_summary", {})
    lines = [
        f"decision: {decision['status']}"
        + (f" ({decision.get('detail')})" if decision.get("detail") else ""),
        "",
        "# FUZZ-1 mc_nn_control Violent Activation",
        "",
        f"run_id: `{payload['run_id']}`",
        "scope: offboard aggressive circle approach + SIH wind + mode 23 mc_nn activation + post-switch hover",
        f"mcnn_evals: {summary.get('eval_count_mcnn')}",
        f"mcnn_hits: {summary.get('hit_count_mcnn')}",
        f"max_pre_switch_roll_pitch_deg: {summary.get('max_pre_switch_roll_pitch_deg')}",
        f"max_pre_switch_angular_rate_rad_s: {summary.get('max_pre_switch_angular_rate_rad_s')}",
        "",
        "## Detection Discipline",
        "",
        "The detector is mc_nn-first. Classical is run only after mc_nn detector hits and is used as a post-hoc classifier, not as a pre-filter. Pure tracking lag is ignored as a finding.",
        "",
        "## Evals",
        "",
        "| idx | controller | case | seed | stage | hit | severity | pre roll deg | pre rate rad/s | reasons | attribution |",
        "|---:|---|---|---:|---|---|---:|---:|---:|---|---|",
    ]
    pairs_by_tag = {item["mcnn"]["tag"]: item for item in payload.get("pairs", [])}
    for idx, record in enumerate(payload.get("records", []), start=1):
        ctx = record.get("switch_context", {})
        detector = record.get("detector", {})
        pair = pairs_by_tag.get(record.get("tag"), {})
        attribution = pair.get("classification", {}).get("label", "-") if record["controller"] == "mcnn" else "-"
        lines.append(
            "| {idx} | {controller} | {case} | {seed} | {stage} | {hit} | {severity} | {roll} | {rate} | {reasons} | {attr} |".format(
                idx=idx,
                controller=record.get("controller"),
                case=record.get("case", {}).get("tag"),
                seed=record.get("seed"),
                stage=record.get("case", {}).get("stage"),
                hit=str(detector.get("hit")).lower(),
                severity=detector.get("severity"),
                roll=ctx.get("pre_switch_roll_pitch_max_deg"),
                rate=ctx.get("pre_switch_angular_rate_max_rad_s"),
                reasons=",".join(detector.get("hit_reasons") or []) or "-",
                attr=attribution,
            )
        )
    if decision["status"] == "BUG-FOUND" and payload.get("confirmed_bug"):
        bug = payload["confirmed_bug"]
        lines.extend(
            [
                "",
                "## Confirmed Bug",
                "",
                f"case: `{bug['case']['tag']}`",
                f"classification: {bug['classification_summary']}",
                f"seeds: {bug['seeds']}",
                f"mcnn_hit_count: {bug['mcnn_hit_count']}",
                f"primary_count: {bug['primary_count']}",
                f"reachability: {bug['reachability']}",
                "",
                "### Source Trace",
                "",
                bug["source_trace"],
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Null Exit",
                "",
                decision.get("rationale", ""),
                "",
                "Next decision point: switch to velocity/angular-rate state injection after repairing shim delivery, or convert these results into robustness characterization.",
            ]
        )
    text = "\n".join(lines) + "\n"
    (docs / "summary.md").write_text(text, encoding="utf-8")
    (docs.parent / f"{payload['run_id']}.md").write_text(text, encoding="utf-8")


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sanitize(payload), sort_keys=True, allow_nan=False) + "\n")


def build_if_needed(repo: Path, docs: Path, env: dict[str, str], skip_build: bool) -> None:
    if not skip_build:
        build_env = env.copy()
        build_env["PX4_MCNN_SIH_BUILD_LOG"] = str(docs / "px4_mcnn_sih_build.log")
        m1.run_checked([str(repo / "scripts/build_px4_mcnn_sih.sh")], cwd=repo, log=docs / "build.log", env=build_env)
        return
    m1.run_checked([str(repo / "scripts/install_mcnn_sih_board.sh")], cwd=repo, log=docs / "build.log", env=env)
    m1.run_checked([str(repo / "scripts/install_m1_sih_x500.sh")], cwd=repo, log=docs / "build.log", env=env)


def source_trace_for(records: list[dict[str, Any]]) -> str:
    reasons = sorted({reason for record in records for reason in record["detector"].get("hit_reasons", [])})
    if "neural_control_network_output_nonfinite" in reasons:
        return (
            "`neural_control.network_output` is published from `_output_tensor->data.f[0..3]` after "
            "`RescaleActions()` in `external/PX4-Autopilot/src/modules/mc_nn_control/mc_nn_control.cpp`; "
            "therefore the non-finite value is produced inside mc_nn inference/rescale glue before debug publish."
        )
    if "actuator_motors_active_nonfinite" in reasons:
        return (
            "Active motor non-finite values are written by `PublishOutput()` from `command_actions[0..3]` in "
            "`external/PX4-Autopilot/src/modules/mc_nn_control/mc_nn_control.cpp`, not by unused actuator slots."
        )
    if any("px4_console_fault" in reason for reason in reasons):
        return "PX4 console matched a module fault/assert pattern; see per-eval console logs for the exact line."
    return "The hit is flight-dynamic; source attribution is through mode-23 mc_nn activation versus matched classical rerun."


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--docs-root", type=Path, default=m1.repo_root() / "docs")
    parser.add_argument("--run-timeout", type=int, default=170)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--max-evals", type=int, default=20)
    parser.add_argument("--phase1-count", type=int, default=12)
    parser.add_argument("--confirm-seeds", type=int, default=3)
    parser.add_argument("--seed-base", type=int, default=20261500)
    parser.add_argument("--safety-config", type=Path, default=m1.repo_root() / "config/m2_safety_envelope.json")
    args = parser.parse_args()

    repo = m1.repo_root()
    docs = (args.docs_root / args.run_id).resolve()
    docs.mkdir(parents=True, exist_ok=True)
    env = m1.agent_env(repo)
    build_if_needed(repo, docs, env, args.skip_build)

    records: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    archive: dict[tuple[int, int], dict[str, Any]] = {}
    rng = random.Random(args.seed_base)
    decision = {
        "status": "NULL",
        "detail": "no confirmed mc_nn-attributable hit yet",
        "rationale": "No mc_nn detector hit has passed post-hoc classical classification and multi-seed confirmation.",
    }
    payload: dict[str, Any] = {
        "run_id": args.run_id,
        "records": records,
        "pairs": pairs,
        "decision": decision,
        "coverage_summary": {},
        "confirmed_bug": None,
    }

    phase1 = PHASE1_CASES[: max(0, args.phase1_count)]
    eval_cases: list[ActivationCase] = list(phase1)
    eval_index = 0

    while eval_index < args.max_evals:
        if eval_index < len(eval_cases):
            case = eval_cases[eval_index]
        else:
            parents = sorted(archive.values() or records, key=fitness, reverse=True)
            parent_case = ActivationCase(**parents[0]["case"]) if parents else rng.choice(PHASE1_CASES)
            case = mutate_case(parent_case, rng, eval_index)
            eval_cases.append(case)

        seed = args.seed_base + eval_index
        mcnn_record = run_controller_eval(
            repo, docs, args.run_id, case, seed, "mcnn", env, args.run_timeout, args.safety_config
        )
        records.append(mcnn_record)
        append_jsonl(docs / "results.jsonl", {"type": "mcnn_eval", "record": mcnn_record})
        archive_key = descriptor_bin(mcnn_record)
        if archive_key not in archive or fitness(mcnn_record) > fitness(archive[archive_key]):
            archive[archive_key] = mcnn_record

        payload["coverage_summary"] = summarize_records(records)
        write_json(docs / "results.json", payload)
        write_summary(docs, payload)

        if not mcnn_record["detector"].get("hit"):
            eval_index += 1
            continue

        classical_record = run_controller_eval(
            repo, docs, args.run_id, case, seed, "classical", env, args.run_timeout, args.safety_config
        )
        records.append(classical_record)
        classification = classify_pair(mcnn_record, classical_record)
        pair = {"mcnn": mcnn_record, "classical": classical_record, "classification": classification}
        pairs.append(pair)
        append_jsonl(docs / "results.jsonl", {"type": "classified_pair", "pair": pair})

        confirmed_pairs = [pair]
        for offset in range(1, max(1, args.confirm_seeds)):
            confirm_seed = seed + 100 + offset
            confirm_case = replace(case, tag=f"{case.tag}_confirm{offset}")
            confirm_mcnn = run_controller_eval(
                repo, docs, args.run_id, confirm_case, confirm_seed, "mcnn", env, args.run_timeout, args.safety_config
            )
            confirm_classical = run_controller_eval(
                repo,
                docs,
                args.run_id,
                confirm_case,
                confirm_seed,
                "classical",
                env,
                args.run_timeout,
                args.safety_config,
            )
            records.extend([confirm_mcnn, confirm_classical])
            confirm_pair = {
                "mcnn": confirm_mcnn,
                "classical": confirm_classical,
                "classification": classify_pair(confirm_mcnn, confirm_classical),
            }
            pairs.append(confirm_pair)
            confirmed_pairs.append(confirm_pair)
            append_jsonl(docs / "results.jsonl", {"type": "confirm_pair", "pair": confirm_pair})

        mcnn_hit_count = sum(1 for item in confirmed_pairs if item["classification"]["mcnn_hit"])
        primary_count = sum(1 for item in confirmed_pairs if item["classification"]["primary_bug"])
        if mcnn_hit_count >= 2 and primary_count >= 2:
            labels = sorted({item["classification"]["label"] for item in confirmed_pairs})
            decision = {
                "status": "BUG-FOUND",
                "detail": f"{case.tag}: {','.join(labels)}",
                "rationale": "A mc_nn detector hit reproduced across seeds and remained NN-attributable after classical reruns.",
            }
            bug_records = [item["mcnn"] for item in confirmed_pairs]
            payload["confirmed_bug"] = {
                "case": asdict(case),
                "seeds": [item["mcnn"]["seed"] for item in confirmed_pairs],
                "mcnn_hit_count": mcnn_hit_count,
                "primary_count": primary_count,
                "classification_summary": ",".join(labels),
                "reachability": (
                    f"Classical Offboard circle approach, wind_n={case.wind_n}, wind_e={case.wind_e}, "
                    f"setup_profile={case.setup_profile}; relaxed limits are IC setup only."
                ),
                "source_trace": source_trace_for(bug_records),
            }
            payload["decision"] = decision
            payload["coverage_summary"] = summarize_records(records)
            write_json(docs / "results.json", payload)
            write_summary(docs, payload)
            print(f"DECISION={decision['status']}")
            print(f"SUMMARY={docs / 'summary.md'}")
            return 0

        payload["coverage_summary"] = summarize_records(records)
        write_json(docs / "results.json", payload)
        write_summary(docs, payload)
        eval_index += 1

    coverage = summarize_records(records)
    decision = {
        "status": "NULL",
        "detail": (
            f"max roll {coverage.get('max_pre_switch_roll_pitch_deg')} deg, "
            f"max rate {coverage.get('max_pre_switch_angular_rate_rad_s')} rad/s"
        ),
        "rationale": (
            "Ran mc_nn-first violent activation search to budget without a confirmed NN-attributable primary bug. "
            "Classical was only used after mc_nn detector hits; tracking-only lag was ignored."
        ),
    }
    payload["decision"] = decision
    payload["coverage_summary"] = coverage
    write_json(docs / "results.json", payload)
    write_summary(docs, payload)
    print(f"DECISION={decision['status']}")
    print(f"SUMMARY={docs / 'summary.md'}")
    print(f"MAIN_DOC={docs.parent / f'{args.run_id}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
