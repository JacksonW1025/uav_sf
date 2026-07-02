#!/usr/bin/env python3
"""Compute property-oracle robustness values from one ULOG.

The reader intentionally reuses the ULOG conventions from m1_metrics.py:
pyulog datasets, Method-A groundtruth topics when present, task-event based
origin reconstruction when a task JSON is available, and trajectory_setpoint as
the logged reference state.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from pyulog import ULog

from m1_metrics import (
    NAV_STATE_BY_CONTROLLER,
    data_field,
    estimate_origin_from_setpoint,
    first_dataset,
    interp_columns,
    load_json,
    mask_window,
    quaternion,
    task_event_elapsed_us,
    vector3,
)
from validity_automation import decontaminated_control_window, mcnn_identity_gate


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_MOTORS = 4

# Tier-0 calibrated defaults. P1/P2 keep the oracle-map catastrophic starting
# values; behavior-class values are set from the 20260625 nominal multi-seed
# baseline in docs/oracle_calibration.md.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "theta_max_deg": 90.0,
    "tau_rec_s": 1.5,
    "omega_max_rad_s": 8.0,
    "u_sat": 0.99,
    "epsilon_sat": 0.01,
    "W_sat_s": 0.5,
    "delta_u_max": 0.70,
    "epsilon_set_m": 1.05,
    "T_set_s": 5.0,
    "W_hold_s": 2.0,
    "s_min_m": 0.5,
    "A_max_deg": 18.0,
    "W_osc_s": 2.0,
    "epsilon_ss_m": 1.80,
    "W_ss_s": 2.0,
    "margin_c": 0.02,
    "margin_c_P1": 0.4548139946,
    "margin_c_P2": 2.3421337853,
    "margin_c_P3": 0.1500000000,
    "margin_c_P4": 0.2023303610,
    "margin_c_P5": 0.1083387278,
    "margin_c_P6": 0.0759150636,
    "margin_c_P7": 0.1126242187,
    "state_moving_average_s": 0.10,
    "control_moving_average_s": 0.02,
}

PROPERTY_ORDER = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]

def finite_float(value: float | np.floating[Any] | None) -> float | None:
    if value is None:
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def load_thresholds(path: Path | None) -> dict[str, float]:
    thresholds = dict(DEFAULT_THRESHOLDS)
    if path is None:
        return thresholds
    data = load_json(path)
    source = data.get("thresholds", data)
    if not isinstance(source, dict):
        raise ValueError(f"thresholds JSON must be an object: {path}")
    for key, value in source.items():
        if isinstance(value, (int, float)):
            thresholds[key] = float(value)
    missing = sorted(set(DEFAULT_THRESHOLDS) - set(thresholds))
    if missing:
        raise ValueError(f"thresholds missing required keys: {missing}")
    return thresholds


def first_existing_dataset(ulog: ULog, names: list[str]):
    for name in names:
        dataset = first_dataset(ulog, name)
        if dataset is not None:
            return dataset
    return None


def field_matrix(dataset: Any, prefix: str, count: int, mask: np.ndarray | None = None) -> np.ndarray:
    cols = []
    for idx in range(count):
        cols.append(data_field(dataset.data, f"{prefix}[{idx}]", f"{prefix}_{idx}", f"{prefix}.{idx}"))
    out = np.column_stack(cols).astype(float)
    if mask is not None:
        out = out[mask]
    return out


def finite_real(value: float | np.floating[Any]) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"non-finite robustness value: {value}")
    return value


def moving_average(values: np.ndarray, timestamps_us: np.ndarray, window_s: float) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.size == 0 or window_s <= 0:
        return values.copy()
    one_dim = values.ndim == 1
    work = values.reshape((-1, 1)) if one_dim else values
    if len(work) < 3:
        return values.copy()
    dt = np.diff(timestamps_us.astype(float)) / 1e6
    dt = dt[np.isfinite(dt) & (dt > 0)]
    if len(dt) == 0:
        return values.copy()
    samples = max(1, int(round(float(window_s) / float(np.median(dt)))))
    if samples <= 1:
        return values.copy()
    if samples % 2 == 0:
        samples += 1
    kernel = np.ones(samples, dtype=float)
    out = np.zeros_like(work, dtype=float)
    for col in range(work.shape[1]):
        valid = np.isfinite(work[:, col]).astype(float)
        filled = np.where(np.isfinite(work[:, col]), work[:, col], 0.0)
        denom = np.convolve(valid, kernel, mode="same")
        numer = np.convolve(filled, kernel, mode="same")
        out[:, col] = np.divide(numer, denom, out=np.full_like(numer, np.nan), where=denom > 0)
    return out[:, 0] if one_dim else out


def quat_tilt_rad(q: np.ndarray) -> np.ndarray:
    # PX4 vehicle_attitude q[0..3] is Hamilton q_nb (body FRD to world NED).
    # DCM R(2,2)=1-2*(q1^2+q2^2), so acos(R33) is yaw-invariant tilt:
    # level flight is 0 rad, inverted is pi rad. This matches the oracle
    # physical definition and does not depend on mc_nn's internal obs frame.
    q = np.asarray(q, dtype=float)
    q1 = q[:, 1]
    q2 = q[:, 2]
    r33 = 1.0 - 2.0 * (q1 * q1 + q2 * q2)
    return np.arccos(np.clip(r33, -1.0, 1.0))


def longest_true_run_s(timestamps_us: np.ndarray, active: np.ndarray) -> float:
    ts = timestamps_us.astype(np.int64)
    active = active.astype(bool)
    if len(ts) == 0 or not np.any(active):
        return 0.0
    dt = np.diff(ts.astype(float)) / 1e6
    sample_dt = float(np.median(dt[np.isfinite(dt) & (dt > 0)])) if np.any(dt > 0) else 0.0
    best = 0.0
    start: int | None = None
    last = 0
    for idx, flag in enumerate(active):
        if flag and start is None:
            start = idx
        if not flag and start is not None:
            last = idx - 1
            best = max(best, (float(ts[last] - ts[start]) / 1e6) + sample_dt)
            start = None
    if start is not None:
        best = max(best, (float(ts[-1] - ts[start]) / 1e6) + sample_dt)
    return float(best)


def future_window_extreme(
    timestamps_us: np.ndarray,
    values: np.ndarray,
    window_s: float,
    want_max: bool,
) -> np.ndarray:
    ts = timestamps_us.astype(np.int64)
    values = np.asarray(values, dtype=float)
    out = np.full(len(values), np.nan, dtype=float)
    q: deque[int] = deque()
    j = 0
    window_us = int(round(window_s * 1e6))
    for i in range(len(values)):
        while j < len(values) and ts[j] <= ts[i] + window_us:
            if math.isfinite(float(values[j])):
                if want_max:
                    while q and values[q[-1]] <= values[j]:
                        q.pop()
                else:
                    while q and values[q[-1]] >= values[j]:
                        q.pop()
                q.append(j)
            j += 1
        while q and q[0] < i:
            q.popleft()
        if q:
            out[i] = values[q[0]]
    return out


def window_peak_to_peak(timestamps_us: np.ndarray, values: np.ndarray, window_s: float) -> np.ndarray:
    max_v = future_window_extreme(timestamps_us, values, window_s, want_max=True)
    min_v = future_window_extreme(timestamps_us, values, window_s, want_max=False)
    return max_v - min_v


def detect_setpoint_steps(
    timestamps_us: np.ndarray,
    setpoints: np.ndarray,
    s_min_m: float,
    start_us: int,
    end_us: int,
) -> list[int]:
    if len(timestamps_us) < 2:
        return []
    delta = np.linalg.norm(np.diff(setpoints, axis=0), axis=1)
    finite = np.isfinite(delta)
    idx = np.where(finite & (delta >= s_min_m))[0] + 1
    return [int(i) for i in idx if start_us <= int(timestamps_us[i]) <= end_us]


def significant_setpoint_change_times(
    timestamps_us: np.ndarray,
    setpoints: np.ndarray,
    min_change_m: float,
    start_us: int,
    end_us: int,
) -> list[int]:
    if len(timestamps_us) < 2:
        return []
    delta = np.linalg.norm(np.diff(setpoints, axis=0), axis=1)
    idx = np.where(np.isfinite(delta) & (delta >= min_change_m))[0] + 1
    return [int(timestamps_us[i]) for i in idx if start_us <= int(timestamps_us[i]) <= end_us]


def task_window_from_json(
    ulog: ULog,
    task: dict[str, Any],
    theta: dict[str, Any],
    controller: str,
    setpoint: Any,
) -> dict[str, int | None]:
    target_nav = NAV_STATE_BY_CONTROLLER[controller]
    status = first_dataset(ulog, "vehicle_status")
    active_us = None
    active_us_from_nav = None
    if status is not None and "nav_state" in status.data:
        nav = status.data["nav_state"].astype(int)
        idx = np.where(nav == target_nav)[0]
        if len(idx):
            active_us_from_nav = int(status.data["timestamp"][idx[0]])
            active_us = active_us_from_nav

    active_elapsed_us = task_event_elapsed_us(task, "controller_active")
    if active_elapsed_us is None:
        active_elapsed_us = task_event_elapsed_us(task, "post_switch_setpoint")
    if active_elapsed_us is None:
        active_elapsed_us = task_event_elapsed_us(task, "state_trigger")
    trajectory_elapsed_us = task_event_elapsed_us(task, "trajectory_start")
    mission_elapsed_us = task_event_elapsed_us(task, "mission_end")
    if task.get("state_trigger_enabled") and active_elapsed_us is not None:
        # Method-A task event timestamps are ROS/wall-clock values, while ULog
        # timestamps are PX4 boot-relative.  The elapsed_s fields are the stable
        # bridge; using setpoint-derived origins can pick pre-switch samples.
        origin_us = int(ulog.start_timestamp)
        active_us = int(origin_us + active_elapsed_us)
        trajectory_start_us = (
            int(origin_us + trajectory_elapsed_us) if trajectory_elapsed_us is not None else active_us
        )
        mission_end_us = int(origin_us + mission_elapsed_us) if mission_elapsed_us is not None else int(ulog.last_timestamp)
        return {
            "origin_us": origin_us,
            "active_us": active_us,
            "active_us_from_nav": active_us_from_nav,
            "trajectory_start_us": trajectory_start_us,
            "mission_end_us": mission_end_us,
        }

    estimated_origin_us = estimate_origin_from_setpoint(setpoint, theta, task) if task.get("state_trigger_enabled") else None
    if task.get("state_trigger_enabled") and estimated_origin_us is not None:
        if active_elapsed_us is not None:
            active_us = int(estimated_origin_us + active_elapsed_us)

    task_active_us = task.get("controller_active_us")
    if active_us is None and isinstance(task_active_us, int):
        active_us = int(task_active_us if task_active_us < 10**12 else task_active_us - int(ulog.start_timestamp))

    if active_us is not None and active_elapsed_us is not None:
        origin_us = int(active_us - active_elapsed_us)
    elif estimated_origin_us is not None:
        origin_us = int(estimated_origin_us)
    else:
        origin_us = int(ulog.start_timestamp)

    if trajectory_elapsed_us is not None:
        trajectory_start_us = int(origin_us + trajectory_elapsed_us)
    elif isinstance(task.get("trajectory_start_us"), int):
        value = int(task["trajectory_start_us"])
        trajectory_start_us = value if value < 10**12 else int(value - int(ulog.start_timestamp))
    else:
        trajectory_start_us = active_us

    if mission_elapsed_us is not None:
        mission_end_us = int(origin_us + mission_elapsed_us)
    elif isinstance(task.get("mission_end_us"), int):
        value = int(task["mission_end_us"])
        mission_end_us = value if value < 10**12 else int(value - int(ulog.start_timestamp))
    else:
        mission_end_us = int(ulog.last_timestamp)

    return {
        "origin_us": origin_us,
        "active_us": active_us,
        "active_us_from_nav": active_us_from_nav,
        "trajectory_start_us": trajectory_start_us,
        "mission_end_us": mission_end_us,
    }


def infer_window_from_ulog(ulog: ULog, controller: str) -> dict[str, int | None]:
    target_nav = NAV_STATE_BY_CONTROLLER[controller]
    status = first_dataset(ulog, "vehicle_status")
    active_us = None
    if status is not None and "nav_state" in status.data:
        nav = status.data["nav_state"].astype(int)
        idx = np.where(nav == target_nav)[0]
        if len(idx):
            active_us = int(status.data["timestamp"][idx[0]])
    if active_us is None:
        active_us = int(ulog.start_timestamp)
    return {
        "origin_us": int(ulog.start_timestamp),
        "active_us": active_us,
        "active_us_from_nav": active_us,
        "trajectory_start_us": active_us,
        "mission_end_us": int(ulog.last_timestamp),
    }


def choose_window(
    ulog: ULog,
    theta: dict[str, Any],
    task: dict[str, Any],
    controller: str,
    setpoint: Any,
    analysis_start_us: int | None,
    analysis_end_us: int | None,
) -> dict[str, Any]:
    if task:
        window = task_window_from_json(ulog, task, theta, controller, setpoint)
    else:
        window = infer_window_from_ulog(ulog, controller)

    start_us = int(analysis_start_us if analysis_start_us is not None else window["active_us"] or ulog.start_timestamp)
    mission_end_us = int(analysis_end_us if analysis_end_us is not None else window["mission_end_us"] or ulog.last_timestamp)
    decontamination = decontaminated_control_window(
        ulog,
        start_us,
        mission_end_us,
        controller=controller,
    )
    terminal = decontamination["terminal"]
    control_end_us = min(int(decontamination["control_end_us"]), mission_end_us)
    if control_end_us <= start_us:
        raise ValueError(f"empty analysis window: start_us={start_us}, control_end_us={control_end_us}")
    window.update(
        {
            "analysis_start_us": start_us,
            "analysis_end_us": mission_end_us,
            "control_end_us": control_end_us,
            "control_duration_s": (control_end_us - start_us) / 1e6,
            "terminal": terminal,
            "decontamination": decontamination,
        }
    )
    return window


def extract_position_reference(
    lpos: Any,
    setpoint: Any,
    start_us: int,
    end_us: int,
    thresholds: dict[str, float],
) -> dict[str, np.ndarray]:
    if lpos is None or setpoint is None:
        raise ValueError("missing vehicle_local_position[_groundtruth] or trajectory_setpoint")
    lts = lpos.data["timestamp"].astype(np.int64)
    lmask = mask_window(lts, start_us, end_us)
    sts = setpoint.data["timestamp"].astype(np.int64)
    smask = mask_window(sts, start_us, end_us)
    if not np.any(lmask) or not np.any(smask):
        raise ValueError("missing position or setpoint samples in analysis window")
    pos_ts = lts[lmask]
    pos = np.column_stack([lpos.data["x"], lpos.data["y"], lpos.data["z"]]).astype(float)[lmask]
    sp_ts = sts[smask]
    sp_pos = vector3(setpoint.data, "position")[smask]
    sp_interp = interp_columns(sp_ts, sp_pos, pos_ts)
    state_window = thresholds["state_moving_average_s"]
    pos_s = moving_average(pos, pos_ts, state_window)
    sp_s = moving_average(sp_interp, pos_ts, state_window)
    err_vec = pos_s - sp_s
    err_norm = np.linalg.norm(err_vec, axis=1)
    return {
        "timestamp_us": pos_ts,
        "position_ned_m": pos_s,
        "setpoint_ned_m": sp_s,
        "setpoint_raw_ned_m": sp_interp,
        "setpoint_logged_timestamp_us": sp_ts,
        "setpoint_logged_ned_m": sp_pos,
        "error_ned_m": err_vec,
        "error_norm_m": err_norm,
    }


def extract_tilt(att: Any, start_us: int, end_us: int, thresholds: dict[str, float]) -> dict[str, np.ndarray]:
    if att is None:
        raise ValueError("missing vehicle_attitude[_groundtruth]")
    ts = att.data["timestamp"].astype(np.int64)
    mask = mask_window(ts, start_us, end_us)
    if not np.any(mask):
        raise ValueError("missing attitude samples in analysis window")
    q = quaternion(att.data)[mask]
    tilt = quat_tilt_rad(q)
    tilt_s = moving_average(tilt, ts[mask], thresholds["state_moving_average_s"])
    return {"timestamp_us": ts[mask], "tilt_rad": tilt_s, "tilt_raw_rad": tilt}


def extract_omega(rates: Any, start_us: int, end_us: int, thresholds: dict[str, float]) -> dict[str, np.ndarray]:
    if rates is None:
        raise ValueError("missing vehicle_angular_velocity[_groundtruth]")
    ts = rates.data["timestamp"].astype(np.int64)
    mask = mask_window(ts, start_us, end_us)
    if not np.any(mask):
        raise ValueError("missing angular velocity samples in analysis window")
    # vehicle_angular_velocity.xyz is body-frame angular rate in rad/s; the norm
    # is frame-invariant for P2 and avoids any mc_nn observation convention.
    omega = vector3(rates.data, "xyz")[mask]
    omega_s = moving_average(omega, ts[mask], thresholds["state_moving_average_s"])
    return {
        "timestamp_us": ts[mask],
        "omega_rad_s": omega_s,
        "omega_norm_rad_s": np.linalg.norm(omega_s, axis=1),
        "omega_raw_norm_rad_s": np.linalg.norm(omega, axis=1),
    }


def extract_motors(motors: Any, start_us: int, end_us: int, thresholds: dict[str, float]) -> dict[str, np.ndarray]:
    if motors is None:
        raise ValueError("missing actuator_motors")
    ts = motors.data["timestamp"].astype(np.int64)
    mask = mask_window(ts, start_us, end_us)
    if not np.any(mask):
        raise ValueError("missing actuator_motors samples in analysis window")
    # mc_nn_control::PublishOutput writes the active X500 motor commands to
    # actuator_motors.control[0..3] and fills unused slots with NaN. Classical
    # control allocation uses the same active normalized command fields.
    controls = field_matrix(motors, "control", ACTIVE_MOTORS, mask)
    controls_s = moving_average(controls, ts[mask], thresholds["control_moving_average_s"])
    return {"timestamp_us": ts[mask], "controls": controls_s, "controls_raw": controls}


def robustness_p1(tilt: dict[str, np.ndarray], thresholds: dict[str, float]) -> tuple[float, dict[str, Any]]:
    theta_max = math.radians(thresholds["theta_max_deg"])
    margin = theta_max - tilt["tilt_rad"]
    rec = future_window_extreme(tilt["timestamp_us"], margin, thresholds["tau_rec_s"], want_max=True)
    rho = finite_real(np.nanmin(rec))
    return rho, {
        "theta_max_deg": thresholds["theta_max_deg"],
        "tau_rec_s": thresholds["tau_rec_s"],
        "tilt_max_deg": finite_float(np.rad2deg(np.nanmax(tilt["tilt_rad"]))),
        "tilt_raw_max_deg": finite_float(np.rad2deg(np.nanmax(tilt["tilt_raw_rad"]))),
    }


def robustness_p2(omega: dict[str, np.ndarray], thresholds: dict[str, float]) -> tuple[float, dict[str, Any]]:
    omega_norm = omega["omega_norm_rad_s"]
    rho = finite_real(np.nanmin(thresholds["omega_max_rad_s"] - omega_norm))
    return rho, {
        "omega_max_rad_s": thresholds["omega_max_rad_s"],
        "omega_norm_max_rad_s": finite_float(np.nanmax(omega_norm)),
        "omega_raw_norm_max_rad_s": finite_float(np.nanmax(omega["omega_raw_norm_rad_s"])),
    }


def robustness_p3(motors: dict[str, np.ndarray], thresholds: dict[str, float]) -> tuple[float, dict[str, Any]]:
    controls = motors["controls"]
    sat_level = thresholds["u_sat"] - thresholds["epsilon_sat"]
    finite = np.all(np.isfinite(controls), axis=1)
    all_high = finite & (np.nanmin(controls, axis=1) >= sat_level)
    longest = longest_true_run_s(motors["timestamp_us"], all_high)
    rho = finite_real(thresholds["W_sat_s"] - longest)
    return rho, {
        "sat_level": sat_level,
        "longest_all_motor_high_saturation_s": longest,
        "max_min_active_motor": finite_float(np.nanmax(np.nanmin(controls, axis=1))),
    }


def robustness_p4(motors: dict[str, np.ndarray], thresholds: dict[str, float]) -> tuple[float, dict[str, Any]]:
    controls = motors["controls"]
    if len(controls) < 2:
        raise ValueError("not enough actuator_motors samples for P4")
    du = np.nanmax(np.abs(np.diff(controls, axis=0)), axis=1)
    max_du = finite_real(np.nanmax(du))
    rho = finite_real(thresholds["delta_u_max"] - max_du)
    return rho, {"delta_u_max": thresholds["delta_u_max"], "max_delta_u": max_du}


def robustness_p5(position: dict[str, np.ndarray], thresholds: dict[str, float]) -> tuple[float, dict[str, Any]]:
    ts = position["timestamp_us"]
    err = position["error_norm_m"]
    setpoint_type = position.get("setpoint_type")
    event_step_times = [int(value) for value in position.get("task_step_times_us", [])]
    if setpoint_type in {None, "", "step"}:
        step_times = significant_setpoint_change_times(
            position.get("setpoint_logged_timestamp_us", ts),
            position.get("setpoint_logged_ned_m", position.get("setpoint_raw_ned_m", position["setpoint_ned_m"])),
            thresholds["s_min_m"],
            int(ts[0]),
            int(ts[-1]),
        )
        if not step_times and event_step_times:
            step_times = [value for value in event_step_times if int(ts[0]) <= value <= int(ts[-1])]
    else:
        step_times = []
    if not step_times:
        return finite_real(thresholds["epsilon_set_m"]), {
            "vacuous": True,
            "steps": 0,
            "s_min_m": thresholds["s_min_m"],
        }
    margin = thresholds["epsilon_set_m"] - err
    hold_min = future_window_extreme(ts, margin, thresholds["W_hold_s"], want_max=False)
    rhos: list[float] = []
    for step_us in step_times:
        end_us = int(step_us + int(round(thresholds["T_set_s"] * 1e6)))
        candidates = (ts >= step_us) & (ts <= end_us)
        if np.any(candidates):
            rhos.append(float(np.nanmax(hold_min[candidates])))
    if not rhos:
        return finite_real(thresholds["epsilon_set_m"]), {
            "vacuous": True,
            "steps": len(step_times),
            "s_min_m": thresholds["s_min_m"],
            "reason": "detected_step_without_settling_candidates",
            "step_times_us": step_times,
        }
    rho = finite_real(min(rhos))
    return rho, {
        "vacuous": False,
        "steps": len(step_times),
        "epsilon_set_m": thresholds["epsilon_set_m"],
        "T_set_s": thresholds["T_set_s"],
        "W_hold_s": thresholds["W_hold_s"],
        "step_times_us": step_times,
        "worst_step_rho_m": rho,
    }


def steady_start_us(position: dict[str, Any], thresholds: dict[str, float]) -> int:
    ts = position["timestamp_us"]
    base_us = int(position.get("steady_base_us", int(ts[0])))
    changes = significant_setpoint_change_times(
        ts,
        position["setpoint_ned_m"],
        max(0.05, thresholds["s_min_m"] * 0.25),
        base_us,
        int(ts[-1]),
    )
    base = changes[-1] if changes else int(ts[0])
    base = max(base, base_us)
    return int(base + int(round(thresholds["T_set_s"] * 1e6)))


def robustness_p6(tilt: dict[str, np.ndarray], position: dict[str, np.ndarray], thresholds: dict[str, float]) -> tuple[float, dict[str, Any]]:
    start_us = steady_start_us(position, thresholds)
    ts = tilt["timestamp_us"]
    pp = window_peak_to_peak(ts, tilt["tilt_rad"], thresholds["W_osc_s"])
    valid = (ts >= start_us) & (ts + int(round(thresholds["W_osc_s"] * 1e6)) <= ts[-1]) & np.isfinite(pp)
    if not np.any(valid):
        # Short windows are vacuously safe for sustained oscillation.
        return finite_real(math.radians(thresholds["A_max_deg"])), {
            "vacuous": True,
            "steady_start_us": start_us,
        }
    pp_max = finite_real(np.nanmax(pp[valid]))
    rho = finite_real(math.radians(thresholds["A_max_deg"]) - pp_max)
    return rho, {
        "vacuous": False,
        "steady_start_us": start_us,
        "A_max_deg": thresholds["A_max_deg"],
        "W_osc_s": thresholds["W_osc_s"],
        "tilt_peak_to_peak_max_deg": finite_float(np.rad2deg(pp_max)),
    }


def robustness_p7(position: dict[str, np.ndarray], thresholds: dict[str, float]) -> tuple[float, dict[str, Any]]:
    start_us = steady_start_us(position, thresholds)
    ts = position["timestamp_us"]
    window_us = int(round(thresholds["W_ss_s"] * 1e6))
    candidates = np.where((ts >= start_us) & (ts <= ts[-1] - window_us))[0]
    if len(candidates) == 0:
        return finite_real(thresholds["epsilon_ss_m"]), {
            "vacuous": True,
            "steady_start_us": start_us,
        }
    worst_axis_mean = 0.0
    for idx in candidates:
        mask = (ts >= ts[idx]) & (ts <= ts[idx] + window_us)
        if not np.any(mask):
            continue
        mean_axis = np.nanmean(position["error_ned_m"][mask], axis=0)
        worst_axis_mean = max(worst_axis_mean, float(np.nanmax(np.abs(mean_axis))))
    rho = finite_real(thresholds["epsilon_ss_m"] - worst_axis_mean)
    return rho, {
        "vacuous": False,
        "steady_start_us": start_us,
        "W_ss_s": thresholds["W_ss_s"],
        "epsilon_ss_m": thresholds["epsilon_ss_m"],
        "worst_abs_axis_mean_error_m": finite_float(worst_axis_mean),
    }


def numeric_faults(ulog: ULog, start_us: int, end_us: int, controller: str) -> dict[str, Any]:
    faults: list[str] = []
    details: dict[str, Any] = {}
    motors = first_dataset(ulog, "actuator_motors")
    if motors is not None:
        ts = motors.data["timestamp"].astype(np.int64)
        mask = mask_window(ts, start_us, end_us)
        if np.any(mask):
            active = field_matrix(motors, "control", ACTIVE_MOTORS, mask)
            count = int(np.count_nonzero(~np.isfinite(active)))
            details["active_motor_nonfinite_count"] = count
            if count:
                faults.append("actuator_motors_active_nonfinite")
    neural = first_dataset(ulog, "neural_control")
    if controller == "mcnn" and neural is not None:
        ts = neural.data["timestamp"].astype(np.int64)
        mask = mask_window(ts, start_us, end_us)
        if np.any(mask):
            network = field_matrix(neural, "network_output", 4, mask)
            observation = field_matrix(neural, "observation", 15, mask)
            n_count = int(np.count_nonzero(~np.isfinite(network)))
            o_count = int(np.count_nonzero(~np.isfinite(observation)))
            details["network_output_nonfinite_count"] = n_count
            details["observation_nonfinite_count"] = o_count
            if n_count:
                faults.append("neural_control_network_output_nonfinite")
            if o_count:
                faults.append("neural_control_observation_nonfinite")
    return {"fault": bool(faults), "reasons": sorted(set(faults)), "details": details}


def controller_identity(ulog: ULog, start_us: int, end_us: int, controller: str) -> dict[str, Any]:
    out: dict[str, Any] = {"controller": controller}
    neural = first_dataset(ulog, "neural_control")
    raptor_input = first_dataset(ulog, "raptor_input")
    out["raptor_input_present"] = raptor_input is not None
    if controller != "mcnn":
        return out
    if neural is None:
        out.update({"mcnn_confirmed": False, "reason": "missing_neural_control_topic"})
        return out
    nts = neural.data["timestamp"].astype(np.int64)
    nmask = mask_window(nts, start_us, end_us)
    samples = int(np.count_nonzero(nmask))
    out["neural_control_samples"] = samples
    if samples >= 2:
        nt = nts[nmask]
        duration_s = max((int(nt[-1]) - int(nt[0])) / 1e6, 1e-9)
        out["neural_control_rate_hz"] = samples / duration_s
    motors = first_dataset(ulog, "actuator_motors")
    exact_matches = 0
    max_abs_diff = None
    exact_match_fraction = None
    exact_equal_count = 0
    p99_abs_diff = None
    if motors is not None and samples > 0:
        mts = motors.data["timestamp"].astype(np.int64)
        common, nidx, midx = np.intersect1d(nts[nmask], mts, return_indices=True)
        if len(common) > 0:
            network = field_matrix(neural, "network_output", 4, nmask)[nidx]
            active = field_matrix(motors, "control", 4, None)[midx]
            diff = np.abs(network - active)
            exact_matches = int(len(common))
            max_abs_diff = finite_float(np.nanmax(diff))
            per_sample = np.nanmax(diff, axis=1)
            exact_equal_count = int(np.count_nonzero(per_sample <= 1e-6))
            exact_match_fraction = finite_float(float(np.mean(per_sample <= 1e-6)))
            p99_abs_diff = finite_float(float(np.nanpercentile(per_sample, 99.0)))
    out["network_output_actuator_exact_timestamp_matches"] = exact_matches
    out["network_output_actuator_exact_equal_count"] = exact_equal_count
    out["network_output_actuator_max_abs_diff"] = max_abs_diff
    out["network_output_actuator_exact_match_fraction"] = exact_match_fraction
    out["network_output_actuator_p99_abs_diff"] = p99_abs_diff
    identity_gate = mcnn_identity_gate(out)
    out["identity_gate"] = identity_gate
    out["mcnn_confirmed"] = bool(identity_gate["passed"])
    return out


def severity_from_properties(rhos: dict[str, float], numeric: dict[str, Any]) -> dict[str, Any]:
    if numeric.get("fault"):
        return {"severity": 4, "label": "S4_numeric_or_software_fault", "reasons": numeric.get("reasons", [])}
    if rhos["P1"] <= 0.0 or rhos["P2"] <= 0.0:
        reasons = []
        if rhos["P1"] <= 0.0:
            reasons.append("P1_attitude_envelope")
        if rhos["P2"] <= 0.0:
            reasons.append("P2_angular_rate_envelope")
        return {"severity": 3, "label": "S3_uncontrolled_tumble_or_spin", "reasons": reasons}
    if rhos["P3"] <= 0.0 or rhos["P5"] <= 0.0:
        reasons = []
        if rhos["P3"] <= 0.0:
            reasons.append("P3_sustained_saturation")
        if rhos["P5"] <= 0.0:
            reasons.append("P5_settling")
        return {"severity": 2, "label": "S2_controlled_safe_failure", "reasons": reasons}
    if rhos["P4"] <= 0.0 or rhos["P6"] <= 0.0 or rhos["P7"] <= 0.0:
        reasons = []
        for name, reason in [("P4", "P4_control_smoothness"), ("P6", "P6_sustained_oscillation"), ("P7", "P7_steady_state_bias")]:
            if rhos[name] <= 0.0:
                reasons.append(reason)
        return {"severity": 1, "label": "S1_controlled_degraded_survival", "reasons": reasons}
    return {"severity": 0, "label": "S0_clean_recovery", "reasons": []}


def evaluate_ulog(
    ulog_path: Path,
    *,
    controller: str = "mcnn",
    theta: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
    thresholds: dict[str, float] | None = None,
    analysis_start_us: int | None = None,
    analysis_end_us: int | None = None,
) -> dict[str, Any]:
    thresholds = dict(thresholds or DEFAULT_THRESHOLDS)
    theta = theta or {}
    task = task or {}
    ulog = ULog(str(ulog_path))
    topic_names = sorted({dataset.name for dataset in ulog.data_list})
    setpoint = first_dataset(ulog, "trajectory_setpoint")
    window = choose_window(ulog, theta, task, controller, setpoint, analysis_start_us, analysis_end_us)
    start_us = int(window["analysis_start_us"])
    end_us = int(window["control_end_us"])

    att = first_existing_dataset(ulog, ["vehicle_attitude_groundtruth", "vehicle_attitude"])
    rates = first_existing_dataset(ulog, ["vehicle_angular_velocity_groundtruth", "vehicle_angular_velocity"])
    lpos = first_existing_dataset(ulog, ["vehicle_local_position_groundtruth", "vehicle_local_position"])
    motors = first_dataset(ulog, "actuator_motors")

    position = extract_position_reference(lpos, setpoint, start_us, end_us, thresholds)
    position["setpoint_type"] = str(theta.get("setpoint", {}).get("type", "")) if isinstance(theta, dict) else ""
    origin_us = window.get("origin_us")
    if isinstance(origin_us, int):
        position["task_step_times_us"] = [
            int(origin_us + int(round(float(event.get("elapsed_s", 0.0)) * 1e6)))
            for event in task.get("events", [])
            if event.get("name") == "setpoint_step"
        ]
    trajectory_start_us = window.get("trajectory_start_us")
    if isinstance(trajectory_start_us, int):
        position["steady_base_us"] = max(start_us, int(trajectory_start_us))
    else:
        position["steady_base_us"] = start_us
    tilt = extract_tilt(att, start_us, end_us, thresholds)
    omega = extract_omega(rates, start_us, end_us, thresholds)
    motor_data = extract_motors(motors, start_us, end_us, thresholds)

    rhos: dict[str, float] = {}
    details: dict[str, Any] = {}
    for prop, fn, args in [
        ("P1", robustness_p1, (tilt, thresholds)),
        ("P2", robustness_p2, (omega, thresholds)),
        ("P3", robustness_p3, (motor_data, thresholds)),
        ("P4", robustness_p4, (motor_data, thresholds)),
        ("P5", robustness_p5, (position, thresholds)),
        ("P6", robustness_p6, (tilt, position, thresholds)),
        ("P7", robustness_p7, (position, thresholds)),
    ]:
        rho, detail = fn(*args)
        rhos[prop] = finite_real(rho)
        details[prop] = detail

    numeric = numeric_faults(ulog, start_us, end_us, controller)
    severity = severity_from_properties(rhos, numeric)

    return {
        "tag": theta.get("tag"),
        "controller": controller,
        "ulog": str(ulog_path),
        "topics_present": topic_names,
        "topic_sources": {
            "attitude": att.name if att is not None else None,
            "angular_velocity": rates.name if rates is not None else None,
            "local_position": lpos.name if lpos is not None else None,
            "setpoint": setpoint.name if setpoint is not None else None,
            "motors": motors.name if motors is not None else None,
        },
        "frame_units_note": (
            "PX4 local_position/trajectory_setpoint are world NED in meters; "
            "vehicle_angular_velocity.xyz is body-frame rad/s; vehicle_attitude "
            "q[0..3] is Hamilton body-to-NED, with tilt=acos(R33); "
            "actuator_motors.control[0..3] are active normalized motor commands. "
            "mc_nn's internal observation frame and 6D attitude ordering were "
            "checked in mc_nn_control.cpp but are not used by this oracle."
        ),
        "thresholds": thresholds,
        "window": window,
        "rho": rhos,
        "details": details,
        "numeric_faults": numeric,
        "severity": severity,
        "controller_identity": controller_identity(ulog, start_us, end_us, controller),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ulog", type=Path, required=True)
    parser.add_argument("--controller", choices=["classical", "raptor", "mcnn"], default="mcnn")
    parser.add_argument("--theta", type=Path)
    parser.add_argument("--task-json", type=Path)
    parser.add_argument("--thresholds-json", type=Path)
    parser.add_argument("--analysis-start-us", type=int)
    parser.add_argument("--analysis-end-us", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    theta = load_json(args.theta) if args.theta else {}
    task = load_json(args.task_json) if args.task_json else {}
    thresholds = load_thresholds(args.thresholds_json)
    result = evaluate_ulog(
        args.ulog,
        controller=args.controller,
        theta=theta,
        task=task,
        thresholds=thresholds,
        analysis_start_us=args.analysis_start_us,
        analysis_end_us=args.analysis_end_us,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    print(
        json.dumps(
            {
                "ulog": str(args.ulog),
                "controller": args.controller,
                "rho": result["rho"],
                "severity": result["severity"],
                "output": str(args.output) if args.output else None,
            },
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
