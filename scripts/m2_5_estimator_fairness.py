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


def theta_estimator_params(theta: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for source_name in ["boot_px4_params", "px4_params"]:
        source = theta.get(source_name, {})
        if isinstance(source, dict):
            for name in ESTIMATOR_PARAM_NAMES:
                if name in source:
                    params[name] = source[name]
    return params


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
    pos_err = np.linalg.norm(pos - truth_pos_i, axis=1)
    vel_err = np.linalg.norm(vel - truth_vel_i, axis=1)
    return {
        "present": True,
        "window_samples": int(len(ts)),
        "position_error_rms_m": finite_rms(pos_err),
        "position_error_max_m": finite_max(pos_err),
        "velocity_error_rms_m_s": finite_rms(vel_err),
        "velocity_error_max_m_s": finite_max(vel_err),
        "position_error_final_m": finite(pos_err[-1]) if len(pos_err) else None,
        "velocity_error_final_m_s": finite(vel_err[-1]) if len(vel_err) else None,
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
    return {
        "present": True,
        "active_samples": int(np.count_nonzero(mask)),
        "position_norm_rms_m": finite_rms(np.linalg.norm(position, axis=1)),
        "position_norm_max_m": finite_max(np.linalg.norm(position, axis=1)),
        "linear_velocity_norm_rms_m_s": finite_rms(np.linalg.norm(linear_velocity, axis=1)),
        "linear_velocity_norm_max_m_s": finite_max(np.linalg.norm(linear_velocity, axis=1)),
        "angular_velocity_norm_rms_rad_s": finite_rms(np.linalg.norm(angular_velocity, axis=1)),
        "angular_velocity_norm_max_rad_s": finite_max(np.linalg.norm(angular_velocity, axis=1)),
        "orientation_all_finite": bool(np.all(np.isfinite(orientation))),
    }


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
        "local_position_vs_groundtruth": local_vs_groundtruth(ulog, window),
        "estimator_status": estimator_status_summary(ulog, window),
        "raptor_input": raptor_input_summary(ulog, window),
    }


def fairness(theta: dict[str, Any], classical: dict[str, Any], raptor: dict[str, Any]) -> dict[str, Any]:
    expected = theta_estimator_params(theta)
    classical_params = classical["effective_estimator_params"]
    raptor_params = raptor["effective_estimator_params"]
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
    shared_topics = all(
        summary["local_position_vs_groundtruth"].get("present")
        and summary["estimator_status"].get("present")
        for summary in [classical, raptor]
    )
    raptor_consumed = bool(raptor["raptor_input"].get("present")) and int(raptor["raptor_input"].get("active_samples") or 0) > 0
    return {
        "same_effective_estimator_params": same_params,
        "theta_estimator_params_applied": expected_applied,
        "shared_estimator_topics_present": shared_topics,
        "raptor_input_active": raptor_consumed,
        "fair_shared_estimator_pollution": same_params and expected_applied and shared_topics and raptor_consumed,
        "param_checks": param_checks,
        "note": "Estimator-error magnitudes need not match exactly because controller trajectories differ; fairness is parameter-identical shared EKF estimate pollution, not RAPTOR-only observation modification.",
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
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
