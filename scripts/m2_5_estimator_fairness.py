#!/usr/bin/env python3
"""Summarize M2.5 shared-estimator-pollution fairness evidence from ULOGs."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from pyulog import ULog


NAV_STATE_BY_CONTROLLER = {"classical": 14, "raptor": 23}
ESTIMATOR_PARAM_NAMES = [
    "SENS_GPS0_DELAY",
    "SENS_GPS1_DELAY",
    "EKF2_DELAY_MAX",
    "EKF2_GPS_P_NOISE",
    "EKF2_GPS_V_NOISE",
    "EKF2_GPS_P_GATE",
    "EKF2_GPS_V_GATE",
    "EKF2_TAU_VEL",
    "EKF2_TAU_POS",
    "EKF2_IMU_POS_X",
    "EKF2_IMU_POS_Y",
    "EKF2_IMU_POS_Z",
    "EKF2_MAG_DELAY",
    "EKF2_MAG_NOISE",
    "EKF2_MAG_GATE",
]
UNSHIELDED_PARAM_NAMES = [
    "IMU_GYRO_CUTOFF",
    "IMU_GYRO_NF0_FRQ",
    "IMU_GYRO_NF0_BW",
    "IMU_GYRO_NF1_FRQ",
    "IMU_GYRO_NF1_BW",
    "IMU_GYRO_RATEMAX",
]
STATE_SHIM_PARAM_NAMES = [
    "M2B_EN",
    "M2B_START",
    "M2B_END",
    "M2B_SEED",
    "M2B_V_PROF",
    "M2B_V_DLY",
    "M2B_V_X",
    "M2B_V_Y",
    "M2B_V_Z",
    "M2B_G_PROF",
    "M2B_G_DLY",
    "M2B_G_X",
    "M2B_G_Y",
    "M2B_G_Z",
    "M2B_A_PROF",
    "M2B_A_DLY",
    "M2B_A_R",
    "M2B_A_P",
    "M2B_A_Y",
]
SHARED_PARAM_NAMES = sorted(set(ESTIMATOR_PARAM_NAMES + UNSHIELDED_PARAM_NAMES + STATE_SHIM_PARAM_NAMES))


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def first_dataset(ulog: ULog, name: str):
    matches = [dataset for dataset in ulog.data_list if dataset.name == name]
    return matches[0] if matches else None


def field(data: dict[str, np.ndarray], *names: str) -> np.ndarray:
    for name in names:
        if name in data:
            return data[name]
    raise KeyError(f"missing field, tried {names}")


def vector3(data: dict[str, np.ndarray], stem: str) -> np.ndarray:
    return np.column_stack(
        [
            field(data, f"{stem}[0]", f"{stem}_0", stem + ".0"),
            field(data, f"{stem}[1]", f"{stem}_1", stem + ".1"),
            field(data, f"{stem}[2]", f"{stem}_2", stem + ".2"),
        ]
    ).astype(float)


def quaternion(data: dict[str, np.ndarray], stem: str = "q") -> np.ndarray:
    return np.column_stack(
        [
            field(data, f"{stem}[0]", f"{stem}_0", stem + ".0"),
            field(data, f"{stem}[1]", f"{stem}_1", stem + ".1"),
            field(data, f"{stem}[2]", f"{stem}_2", stem + ".2"),
            field(data, f"{stem}[3]", f"{stem}_3", stem + ".3"),
        ]
    ).astype(float)


def normalize_quat(q: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(q, axis=1)
    out = q.copy()
    valid = np.isfinite(norm) & (norm > 0.0)
    out[valid] = out[valid] / norm[valid, None]
    out[~valid] = np.nan
    return out


def mask_window(ts: np.ndarray, start_us: int | None, end_us: int | None) -> np.ndarray:
    mask = np.ones(ts.shape, dtype=bool)
    if start_us is not None:
        mask &= ts >= start_us
    if end_us is not None:
        mask &= ts <= end_us
    return mask


def interp_columns(src_t: np.ndarray, src_v: np.ndarray, dst_t: np.ndarray) -> np.ndarray:
    out = np.zeros((len(dst_t), src_v.shape[1]), dtype=float)
    for idx in range(src_v.shape[1]):
        valid = np.isfinite(src_v[:, idx])
        if np.count_nonzero(valid) == 0:
            out[:, idx] = np.nan
        elif np.count_nonzero(valid) == 1:
            out[:, idx] = src_v[valid, idx][0]
        else:
            out[:, idx] = np.interp(dst_t, src_t[valid], src_v[valid, idx])
    return out


def finite(value: float | np.floating | None) -> float | None:
    if value is None:
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def finite_mean(values: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return finite(np.mean(values)) if len(values) else None


def finite_rms(values: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return finite(math.sqrt(float(np.mean(values * values)))) if len(values) else None


def finite_max(values: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return finite(np.max(values)) if len(values) else None


def nonfinite_count(values: np.ndarray) -> int:
    return int(np.count_nonzero(~np.isfinite(np.asarray(values, dtype=float))))


def vector_norm(values: np.ndarray) -> np.ndarray:
    return np.linalg.norm(np.asarray(values, dtype=float), axis=1)


def quat_error_deg(q_est: np.ndarray, q_truth: np.ndarray) -> np.ndarray:
    q_est = normalize_quat(q_est)
    q_truth = normalize_quat(q_truth)
    dot = np.abs(np.sum(q_est * q_truth, axis=1))
    dot = np.clip(dot, -1.0, 1.0)
    return np.rad2deg(2.0 * np.arccos(dot))


def task_event_elapsed_us(task: dict[str, Any], name: str) -> int | None:
    for event in task.get("events", []):
        if event.get("name") == name:
            return int(round(float(event.get("elapsed_s", 0.0)) * 1e6))
    return None


def analysis_window(ulog: ULog, task: dict[str, Any], controller: str) -> dict[str, int | None]:
    status = first_dataset(ulog, "vehicle_status")
    target_nav = NAV_STATE_BY_CONTROLLER[controller]
    active_us = None
    if status is not None and "nav_state" in status.data:
        nav = status.data["nav_state"].astype(int)
        idx = np.where(nav == target_nav)[0]
        if len(idx):
            active_us = int(status.data["timestamp"][idx[0]])

    active_elapsed = task_event_elapsed_us(task, "controller_active")
    trajectory_elapsed = task_event_elapsed_us(task, "trajectory_start")
    mission_elapsed = task_event_elapsed_us(task, "mission_end")
    origin_us = int(active_us - active_elapsed) if active_us is not None and active_elapsed is not None else int(ulog.start_timestamp)
    return {
        "origin_us": origin_us,
        "active_us": active_us,
        "trajectory_start_us": int(origin_us + trajectory_elapsed) if trajectory_elapsed is not None else active_us,
        "mission_end_us": int(origin_us + mission_elapsed) if mission_elapsed is not None else None,
    }


def effective_params(ulog: ULog, names: list[str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in names:
        if name in ulog.initial_parameters:
            values[name] = ulog.initial_parameters[name]
    for _timestamp, name, value in ulog.changed_parameters:
        if name in names:
            values[name] = value
    return values


def theta_params(theta: dict[str, Any], names: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for source_name in ["boot_px4_params", "px4_params"]:
        source = theta.get(source_name, {})
        if isinstance(source, dict):
            for name in names:
                if name in source:
                    params[name] = source[name]
    return params


def theta_estimator_params(theta: dict[str, Any]) -> dict[str, Any]:
    return theta_params(theta, ESTIMATOR_PARAM_NAMES)


def theta_unshielded_params(theta: dict[str, Any]) -> dict[str, Any]:
    return theta_params(theta, UNSHIELDED_PARAM_NAMES)


def theta_state_shim_params(theta: dict[str, Any]) -> dict[str, Any]:
    return theta_params(theta, STATE_SHIM_PARAM_NAMES)


def close_enough(a: Any, b: Any) -> bool:
    try:
        return math.isclose(float(a), float(b), rel_tol=1e-5, abs_tol=1e-5)
    except (TypeError, ValueError):
        return a == b


def local_vs_groundtruth(ulog: ULog, window: dict[str, int | None]) -> dict[str, Any]:
    lpos = first_dataset(ulog, "vehicle_local_position")
    truth = first_dataset(ulog, "vehicle_local_position_groundtruth")
    if lpos is None or truth is None:
        return {"present": False}
    lts = lpos.data["timestamp"].astype(np.int64)
    tts = truth.data["timestamp"].astype(np.int64)
    lmask = mask_window(lts, window["trajectory_start_us"], window["mission_end_us"])
    tmask = mask_window(tts, window["trajectory_start_us"], window["mission_end_us"])
    if not np.any(lmask) or not np.any(tmask):
        return {"present": True, "window_samples": 0}
    ts = lts[lmask]
    pos = np.column_stack([lpos.data["x"], lpos.data["y"], lpos.data["z"]]).astype(float)[lmask]
    vel = np.column_stack([lpos.data["vx"], lpos.data["vy"], lpos.data["vz"]]).astype(float)[lmask]
    truth_pos = np.column_stack([truth.data["x"], truth.data["y"], truth.data["z"]]).astype(float)[tmask]
    truth_vel = np.column_stack([truth.data["vx"], truth.data["vy"], truth.data["vz"]]).astype(float)[tmask]
    truth_pos_i = interp_columns(tts[tmask], truth_pos, ts)
    truth_vel_i = interp_columns(tts[tmask], truth_vel, ts)
    pos_delta = pos - truth_pos_i
    vel_delta = vel - truth_vel_i
    pos_err = vector_norm(pos_delta)
    vel_err = vector_norm(vel_delta)
    return {
        "present": True,
        "window_samples": int(len(ts)),
        "position_error_rms_m": finite_rms(pos_err),
        "position_error_max_m": finite_max(pos_err),
        "velocity_error_rms_m_s": finite_rms(vel_err),
        "velocity_error_max_m_s": finite_max(vel_err),
        "velocity_error_axis_rms_m_s": [finite_rms(vel_delta[:, axis]) for axis in range(3)],
        "velocity_estimate_nonfinite_count": nonfinite_count(vel),
        "position_error_final_m": finite(pos_err[-1]) if len(pos_err) else None,
        "velocity_error_final_m_s": finite(vel_err[-1]) if len(vel_err) else None,
    }


def attitude_vs_groundtruth(ulog: ULog, window: dict[str, int | None]) -> dict[str, Any]:
    att = first_dataset(ulog, "vehicle_attitude")
    truth = first_dataset(ulog, "vehicle_attitude_groundtruth")
    if att is None or truth is None:
        return {"present": False}
    ats = att.data["timestamp"].astype(np.int64)
    tts = truth.data["timestamp"].astype(np.int64)
    amask = mask_window(ats, window["trajectory_start_us"], window["mission_end_us"])
    tmask = mask_window(tts, window["trajectory_start_us"], window["mission_end_us"])
    if not np.any(amask) or not np.any(tmask):
        return {"present": True, "window_samples": 0}
    q = quaternion(att.data)[amask]
    truth_q = quaternion(truth.data)[tmask]
    truth_q_i = interp_columns(tts[tmask], truth_q, ats[amask])
    err_deg = quat_error_deg(q, truth_q_i)
    return {
        "present": True,
        "window_samples": int(np.count_nonzero(amask)),
        "quaternion_error_rms_deg": finite_rms(err_deg),
        "quaternion_error_max_deg": finite_max(err_deg),
        "attitude_quaternion_nonfinite_count": nonfinite_count(q),
        "quaternion_error_final_deg": finite(err_deg[-1]) if len(err_deg) else None,
    }


def angular_velocity_vs_groundtruth(ulog: ULog, window: dict[str, int | None]) -> dict[str, Any]:
    rates = first_dataset(ulog, "vehicle_angular_velocity")
    truth = first_dataset(ulog, "vehicle_angular_velocity_groundtruth")
    if rates is None or truth is None:
        return {"present": False}
    rts = rates.data["timestamp"].astype(np.int64)
    tts = truth.data["timestamp"].astype(np.int64)
    rmask = mask_window(rts, window["trajectory_start_us"], window["mission_end_us"])
    tmask = mask_window(tts, window["trajectory_start_us"], window["mission_end_us"])
    if not np.any(rmask) or not np.any(tmask):
        return {"present": True, "window_samples": 0}
    omega = vector3(rates.data, "xyz")[rmask]
    truth_omega = vector3(truth.data, "xyz")[tmask]
    truth_omega_i = interp_columns(tts[tmask], truth_omega, rts[rmask])
    delta = omega - truth_omega_i
    err = vector_norm(delta)
    return {
        "present": True,
        "window_samples": int(np.count_nonzero(rmask)),
        "error_rms_rad_s": finite_rms(err),
        "error_max_rad_s": finite_max(err),
        "error_axis_rms_rad_s": [finite_rms(delta[:, axis]) for axis in range(3)],
        "estimate_nonfinite_count": nonfinite_count(omega),
        "error_final_rad_s": finite(err[-1]) if len(err) else None,
        "estimate_norm_rms_rad_s": finite_rms(vector_norm(omega)),
        "truth_norm_rms_rad_s": finite_rms(vector_norm(truth_omega_i)),
    }


def estimator_status_summary(ulog: ULog, window: dict[str, int | None]) -> dict[str, Any]:
    status = first_dataset(ulog, "estimator_status")
    if status is None:
        return {"present": False}
    ts = status.data["timestamp"].astype(np.int64)
    mask = mask_window(ts, window["trajectory_start_us"], window["mission_end_us"])
    if not np.any(mask):
        return {"present": True, "window_samples": 0}
    summary: dict[str, Any] = {"present": True, "window_samples": int(np.count_nonzero(mask))}
    for name in [
        "vel_test_ratio",
        "pos_test_ratio",
        "hgt_test_ratio",
        "hdg_test_ratio",
        "pos_horiz_accuracy",
        "pos_vert_accuracy",
        "time_slip",
    ]:
        if name in status.data:
            values = status.data[name].astype(float)[mask]
            summary[f"{name}_mean"] = finite_mean(values)
            summary[f"{name}_max"] = finite_max(values)
    for idx, label in enumerate(["angle_rad", "velocity_m_s", "position_m"]):
        name = f"output_tracking_error[{idx}]"
        if name in status.data:
            values = status.data[name].astype(float)[mask]
            summary[f"output_tracking_error_{label}_mean"] = finite_mean(values)
            summary[f"output_tracking_error_{label}_max"] = finite_max(values)
    for name in [
        "gps_check_fail_flags",
        "filter_fault_flags",
        "reset_count_vel_ne",
        "reset_count_vel_d",
        "reset_count_pos_ne",
        "reset_count_pod_d",
        "reset_count_quat",
    ]:
        if name in status.data:
            values = status.data[name][mask]
            summary[f"{name}_max"] = int(np.max(values))
            summary[f"{name}_final"] = int(values[-1])
    return summary


def rotate_target_frame(vectors: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    c = np.cos(0.5 * yaw)
    s = np.sin(0.5 * yaw)
    r00 = 1.0 - 2.0 * s * s
    r01 = -2.0 * c * s
    r10 = 2.0 * c * s
    r11 = 1.0 - 2.0 * s * s
    out = np.zeros_like(vectors, dtype=float)
    out[:, 0] = r00 * vectors[:, 0] + r01 * vectors[:, 1]
    out[:, 1] = r10 * vectors[:, 0] + r11 * vectors[:, 1]
    out[:, 2] = vectors[:, 2]
    return out


def quat_multiply(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    out = np.zeros_like(q1, dtype=float)
    out[:, 0] = q1[:, 0] * q2[:, 0] - q1[:, 1] * q2[:, 1] - q1[:, 2] * q2[:, 2] - q1[:, 3] * q2[:, 3]
    out[:, 1] = q1[:, 0] * q2[:, 1] + q1[:, 1] * q2[:, 0] + q1[:, 2] * q2[:, 3] - q1[:, 3] * q2[:, 2]
    out[:, 2] = q1[:, 0] * q2[:, 2] - q1[:, 1] * q2[:, 3] + q1[:, 2] * q2[:, 0] + q1[:, 3] * q2[:, 1]
    out[:, 3] = q1[:, 0] * q2[:, 3] + q1[:, 1] * q2[:, 2] - q1[:, 2] * q2[:, 1] + q1[:, 3] * q2[:, 0]
    return out


def route_linear_velocity_from_shared_topics(ulog: ULog, input_ts: np.ndarray, input_values: np.ndarray, window: dict[str, int | None]) -> dict[str, Any]:
    lpos = first_dataset(ulog, "vehicle_local_position")
    sp = first_dataset(ulog, "trajectory_setpoint")
    if lpos is None or sp is None:
        return {"linear_velocity_shared_route_present": False}
    lts = lpos.data["timestamp"].astype(np.int64)
    sts = sp.data["timestamp"].astype(np.int64)
    lmask = mask_window(lts, window["active_us"], window["mission_end_us"])
    smask = mask_window(sts, window["active_us"], window["mission_end_us"])
    if not np.any(lmask) or not np.any(smask):
        return {"linear_velocity_shared_route_present": True, "linear_velocity_shared_route_samples": 0}
    velocity = np.column_stack([lpos.data["vx"], lpos.data["vy"], lpos.data["vz"]]).astype(float)[lmask]
    sp_velocity = vector3(sp.data, "velocity")[smask]
    yaw = field(sp.data, "yaw").astype(float)[smask]
    velocity_i = interp_columns(lts[lmask], velocity, input_ts)
    sp_velocity_i = interp_columns(sts[smask], sp_velocity, input_ts)
    yaw_i = np.interp(input_ts, sts[smask], yaw)
    flu_error = np.column_stack(
        [
            velocity_i[:, 0] - sp_velocity_i[:, 0],
            -(velocity_i[:, 1] - sp_velocity_i[:, 1]),
            -(velocity_i[:, 2] - sp_velocity_i[:, 2]),
        ]
    )
    expected = np.clip(rotate_target_frame(flu_error, yaw_i), -1.0, 1.0)
    route_err = vector_norm(input_values - expected)
    route_rms = finite_rms(route_err)
    return {
        "linear_velocity_shared_route_present": True,
        "linear_velocity_shared_route_samples": int(len(input_ts)),
        "linear_velocity_shared_route_error_rms_m_s": route_rms,
        "linear_velocity_shared_route_error_max_m_s": finite_max(route_err),
        "linear_velocity_shared_route_verified": bool(route_rms is not None and route_rms < 0.08),
        "linear_velocity_route_note": "Recomputed from shared vehicle_local_position velocity and trajectory_setpoint using mc_raptor clipping/sign conventions.",
    }


def route_orientation_from_shared_topics(ulog: ULog, input_ts: np.ndarray, input_values: np.ndarray, window: dict[str, int | None]) -> dict[str, Any]:
    attitude = first_dataset(ulog, "vehicle_attitude")
    sp = first_dataset(ulog, "trajectory_setpoint")
    if attitude is None or sp is None:
        return {"orientation_shared_route_present": False}
    ats = attitude.data["timestamp"].astype(np.int64)
    sts = sp.data["timestamp"].astype(np.int64)
    amask = mask_window(ats, window["active_us"], window["mission_end_us"])
    smask = mask_window(sts, window["active_us"], window["mission_end_us"])
    if not np.any(amask) or not np.any(smask):
        return {"orientation_shared_route_present": True, "orientation_shared_route_samples": 0}
    q_vehicle = quaternion(attitude.data)[amask]
    yaw = field(sp.data, "yaw").astype(float)[smask]
    q_vehicle_i = interp_columns(ats[amask], q_vehicle, input_ts)
    yaw_i = np.interp(input_ts, sts[smask], yaw)
    qtc = np.column_stack([np.cos(0.5 * yaw_i), np.zeros_like(yaw_i), np.zeros_like(yaw_i), np.sin(0.5 * yaw_i)])
    qr = np.column_stack([q_vehicle_i[:, 0], q_vehicle_i[:, 1], -q_vehicle_i[:, 2], -q_vehicle_i[:, 3]])
    expected = quat_multiply(qtc, qr)
    route_err = vector_norm(input_values - expected)
    route_rms = finite_rms(route_err)
    return {
        "orientation_shared_route_present": True,
        "orientation_shared_route_samples": int(len(input_ts)),
        "orientation_shared_route_error_rms": route_rms,
        "orientation_shared_route_error_max": finite_max(route_err),
        "orientation_shared_route_verified": bool(route_rms is not None and route_rms < 0.08),
        "orientation_route_note": "Recomputed from shared vehicle_attitude and trajectory_setpoint yaw using mc_raptor quaternion conventions.",
    }


def raptor_input_summary(ulog: ULog, window: dict[str, int | None]) -> dict[str, Any]:
    raptor_input = first_dataset(ulog, "raptor_input")
    if raptor_input is None:
        return {"present": False}
    ts = raptor_input.data["timestamp"].astype(np.int64)
    mask = mask_window(ts, window["active_us"], window["mission_end_us"])
    if "active" in raptor_input.data:
        mask &= raptor_input.data["active"].astype(bool)
    if not np.any(mask):
        return {"present": True, "active_samples": 0}
    linear_velocity = vector3(raptor_input.data, "linear_velocity")[mask]
    angular_velocity = vector3(raptor_input.data, "angular_velocity")[mask]
    position = vector3(raptor_input.data, "position")[mask]
    orientation = np.column_stack(
        [
            field(raptor_input.data, "orientation[0]", "orientation_0"),
            field(raptor_input.data, "orientation[1]", "orientation_1"),
            field(raptor_input.data, "orientation[2]", "orientation_2"),
            field(raptor_input.data, "orientation[3]", "orientation_3"),
        ]
    ).astype(float)[mask]
    summary = {
        "present": True,
        "active_samples": int(np.count_nonzero(mask)),
        "position_norm_rms_m": finite_rms(vector_norm(position)),
        "position_norm_max_m": finite_max(vector_norm(position)),
        "position_nonfinite_count": nonfinite_count(position),
        "position_all_finite": bool(np.all(np.isfinite(position))),
        "linear_velocity_norm_rms_m_s": finite_rms(vector_norm(linear_velocity)),
        "linear_velocity_norm_max_m_s": finite_max(vector_norm(linear_velocity)),
        "linear_velocity_nonfinite_count": nonfinite_count(linear_velocity),
        "linear_velocity_all_finite": bool(np.all(np.isfinite(linear_velocity))),
        "angular_velocity_norm_rms_rad_s": finite_rms(vector_norm(angular_velocity)),
        "angular_velocity_norm_max_rad_s": finite_max(vector_norm(angular_velocity)),
        "angular_velocity_nonfinite_count": nonfinite_count(angular_velocity),
        "angular_velocity_all_finite": bool(np.all(np.isfinite(angular_velocity))),
        "orientation_nonfinite_count": nonfinite_count(orientation),
        "orientation_all_finite": bool(np.all(np.isfinite(orientation))),
    }
    summary.update(route_linear_velocity_from_shared_topics(ulog, ts[mask], linear_velocity, window))
    summary.update(route_orientation_from_shared_topics(ulog, ts[mask], orientation, window))
    rates = first_dataset(ulog, "vehicle_angular_velocity")
    if rates is not None:
        rts = rates.data["timestamp"].astype(np.int64)
        rmask = mask_window(rts, window["active_us"], window["mission_end_us"])
        if np.any(rmask):
            omega = vector3(rates.data, "xyz")[rmask]
            omega_i = interp_columns(rts[rmask], omega, ts[mask])
            expected_input = np.column_stack([omega_i[:, 0], -omega_i[:, 1], -omega_i[:, 2]])
            route_err = vector_norm(angular_velocity - expected_input)
            route_rms = finite_rms(route_err)
            summary.update(
                {
                    "angular_velocity_vehicle_route_error_rms_rad_s": route_rms,
                    "angular_velocity_vehicle_route_error_max_rad_s": finite_max(route_err),
                    "angular_velocity_vehicle_route_verified": bool(
                        route_rms is not None and route_rms < 0.05
                    ),
                    "angular_velocity_route_note": "RAPTOR stores [x, -y, -z] from shared vehicle_angular_velocity.",
                }
            )
    return summary


def summarize_one(ulog_path: Path, task_path: Path | None, controller: str) -> dict[str, Any]:
    ulog = ULog(str(ulog_path))
    task = load_json(task_path)
    window = analysis_window(ulog, task, controller)
    return {
        "ulog": str(ulog_path),
        "controller": controller,
        "topics_present": sorted({dataset.name for dataset in ulog.data_list}),
        "window": window,
        "effective_estimator_params": effective_params(ulog, ESTIMATOR_PARAM_NAMES),
        "effective_unshielded_params": effective_params(ulog, UNSHIELDED_PARAM_NAMES),
        "effective_state_shim_params": effective_params(ulog, STATE_SHIM_PARAM_NAMES),
        "effective_shared_params": effective_params(ulog, SHARED_PARAM_NAMES),
        "local_position_vs_groundtruth": local_vs_groundtruth(ulog, window),
        "attitude_vs_groundtruth": attitude_vs_groundtruth(ulog, window),
        "angular_velocity_vs_groundtruth": angular_velocity_vs_groundtruth(ulog, window),
        "estimator_status": estimator_status_summary(ulog, window),
        "raptor_input": raptor_input_summary(ulog, window),
    }


def fairness(theta: dict[str, Any], classical: dict[str, Any], raptor: dict[str, Any]) -> dict[str, Any]:
    expected = theta_params(theta, SHARED_PARAM_NAMES)
    classical_params = classical["effective_shared_params"]
    raptor_params = raptor["effective_shared_params"]
    names = sorted(set(expected) | set(classical_params) | set(raptor_params))
    param_checks = {
        name: {
            "theta": expected.get(name),
            "classical": classical_params.get(name),
            "raptor": raptor_params.get(name),
            "classical_matches_theta": name not in expected or close_enough(classical_params.get(name), expected[name]),
            "raptor_matches_theta": name not in expected or close_enough(raptor_params.get(name), expected[name]),
            "classical_matches_raptor": close_enough(classical_params.get(name), raptor_params.get(name)),
        }
        for name in names
    }
    same_params = all(item["classical_matches_raptor"] for item in param_checks.values())
    expected_applied = all(
        item["classical_matches_theta"] and item["raptor_matches_theta"]
        for item in param_checks.values()
        if item["theta"] is not None
    )
    shared_estimator_topics = all(
        summary["local_position_vs_groundtruth"].get("present")
        and summary["estimator_status"].get("present")
        for summary in [classical, raptor]
    )
    shared_unshielded_topics = all(
        summary["angular_velocity_vs_groundtruth"].get("present")
        and summary["attitude_vs_groundtruth"].get("present")
        for summary in [classical, raptor]
    )
    raptor_consumed = bool(raptor["raptor_input"].get("present")) and int(raptor["raptor_input"].get("active_samples") or 0) > 0
    raptor_rate_routed = bool(raptor["raptor_input"].get("angular_velocity_vehicle_route_verified"))
    raptor_velocity_routed = bool(raptor["raptor_input"].get("linear_velocity_shared_route_verified"))
    raptor_orientation_routed = bool(raptor["raptor_input"].get("orientation_shared_route_verified"))
    unshielded_expected = theta_unshielded_params(theta)
    nominal_cutoff = float(theta.get("m2_6", {}).get("nominal_gyro_cutoff_hz", 30.0))
    cutoff = unshielded_expected.get("IMU_GYRO_CUTOFF")
    cutoff_pollution = cutoff is not None and float(cutoff) < nominal_cutoff - 1e-6
    notch_pollution = any(
        float(unshielded_expected.get(name, 0.0) or 0.0) > 0.0
        for name in ["IMU_GYRO_NF0_FRQ", "IMU_GYRO_NF1_FRQ"]
    )
    unshielded_configured = bool(cutoff_pollution or notch_pollution)
    state_expected = theta_state_shim_params(theta)
    state_enabled = bool(int(float(state_expected.get("M2B_EN", 0) or 0)))
    profile_names = {
        0: "off",
        1: "delay",
        2: "bias",
        3: "noise",
        4: "nan",
        5: "inf",
    }
    state_channels: list[dict[str, Any]] = []
    for channel, key in [("velocity", "M2B_V_PROF"), ("angular_velocity", "M2B_G_PROF"), ("attitude", "M2B_A_PROF")]:
        profile = int(float(state_expected.get(key, 0) or 0))
        if profile > 0:
            state_channels.append({"channel": channel, "profile": profile_names.get(profile, str(profile)), "profile_id": profile})

    def channel_topic_observed(summary: dict[str, Any], channel: str) -> bool:
        if channel == "velocity":
            local = summary["local_position_vs_groundtruth"]
            return bool(
                local.get("present")
                and (
                    int(local.get("velocity_estimate_nonfinite_count") or 0) > 0
                    or float(local.get("velocity_error_rms_m_s") or 0.0) > 0.005
                )
            )
        if channel == "angular_velocity":
            rates = summary["angular_velocity_vs_groundtruth"]
            return bool(
                rates.get("present")
                and (
                    int(rates.get("estimate_nonfinite_count") or 0) > 0
                    or float(rates.get("error_rms_rad_s") or 0.0) > 0.002
                )
            )
        if channel == "attitude":
            attitude = summary["attitude_vs_groundtruth"]
            return bool(
                attitude.get("present")
                and (
                    int(attitude.get("attitude_quaternion_nonfinite_count") or 0) > 0
                    or float(attitude.get("quaternion_error_rms_deg") or 0.0) > 0.01
                )
            )
        return False

    def raptor_touch_observed(channel: str) -> bool:
        rin = raptor["raptor_input"]
        if channel == "velocity":
            return bool(raptor_velocity_routed or int(rin.get("linear_velocity_nonfinite_count") or 0) > 0)
        if channel == "angular_velocity":
            return bool(raptor_rate_routed or int(rin.get("angular_velocity_nonfinite_count") or 0) > 0)
        if channel == "attitude":
            return bool(raptor_orientation_routed or int(rin.get("orientation_nonfinite_count") or 0) > 0)
        return False

    state_topic_checks = [
        {
            "channel": item["channel"],
            "classical_topic_polluted": channel_topic_observed(classical, item["channel"]),
            "raptor_topic_polluted": channel_topic_observed(raptor, item["channel"]),
            "raptor_input_touch_verified": raptor_touch_observed(item["channel"]),
        }
        for item in state_channels
    ]
    state_topic_polluted_both = bool(state_topic_checks) and all(
        item["classical_topic_polluted"] and item["raptor_topic_polluted"] for item in state_topic_checks
    )
    state_raptor_touch = bool(state_topic_checks) and all(item["raptor_input_touch_verified"] for item in state_topic_checks)
    return {
        "same_effective_estimator_params": same_params,
        "theta_estimator_params_applied": expected_applied,
        "same_effective_shared_params": same_params,
        "theta_shared_params_applied": expected_applied,
        "theta_state_shim_params": state_expected,
        "state_shim_enabled": state_enabled,
        "state_shim_channels": state_channels,
        "state_shim_topic_checks": state_topic_checks,
        "state_shim_topic_polluted_both_runs": state_topic_polluted_both,
        "state_shim_raptor_input_touch_verified": state_raptor_touch,
        "shared_estimator_topics_present": shared_estimator_topics,
        "shared_unshielded_topics_present": shared_unshielded_topics,
        "raptor_input_active": raptor_consumed,
        "raptor_input_rate_routed_from_vehicle_angular_velocity": raptor_rate_routed,
        "raptor_input_linear_velocity_routed_from_vehicle_local_position": raptor_velocity_routed,
        "raptor_input_orientation_routed_from_vehicle_attitude": raptor_orientation_routed,
        "rate_filter_pollution_configured": unshielded_configured,
        "fair_shared_estimator_pollution": same_params and expected_applied and shared_estimator_topics and raptor_consumed,
        "fair_shared_unshielded_pollution": (
            same_params
            and expected_applied
            and shared_unshielded_topics
            and raptor_consumed
            and raptor_rate_routed
            and unshielded_configured
        ),
        "fair_shared_state_shim_pollution": (
            same_params
            and expected_applied
            and state_enabled
            and bool(state_channels)
            and shared_estimator_topics
            and shared_unshielded_topics
            and raptor_consumed
            and state_topic_polluted_both
            and state_raptor_touch
        ),
        "param_checks": param_checks,
        "note": "Error magnitudes need not match exactly because controller trajectories differ; fairness is parameter-identical shared-channel pollution, not RAPTOR-only observation modification.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theta", type=Path, required=True)
    parser.add_argument("--classical-ulog", type=Path, required=True)
    parser.add_argument("--raptor-ulog", type=Path, required=True)
    parser.add_argument("--classical-task-json", type=Path)
    parser.add_argument("--raptor-task-json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    theta = load_json(args.theta)
    classical = summarize_one(args.classical_ulog, args.classical_task_json, "classical")
    raptor = summarize_one(args.raptor_ulog, args.raptor_task_json, "raptor")
    result = {
        "theta": str(args.theta),
        "theta_tag": theta.get("tag"),
        "theta_estimator_params": theta_estimator_params(theta),
        "theta_unshielded_params": theta_unshielded_params(theta),
        "theta_state_shim_params": theta_state_shim_params(theta),
        "classical": classical,
        "raptor": raptor,
        "fairness": fairness(theta, classical, raptor),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "fair_shared_estimator_pollution": result["fairness"]["fair_shared_estimator_pollution"],
                "fair_shared_unshielded_pollution": result["fairness"]["fair_shared_unshielded_pollution"],
                "fair_shared_state_shim_pollution": result["fairness"]["fair_shared_state_shim_pollution"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
