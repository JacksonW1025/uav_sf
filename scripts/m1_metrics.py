#!/usr/bin/env python3
"""Extract M1 oracle metrics from one ULOG."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from pyulog import ULog


NAV_STATE_BY_CONTROLLER = {"classical": 14, "raptor": 23}
ACTIVE_MOTORS = 4
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAFETY_CONFIG = REPO_ROOT / "config/m2_safety_envelope.json"
CONTROL_LEVEL_REASONS = {
    "missing_required_topics",
    "controller_mode_not_confirmed",
    "unexpected_disarm",
    "failsafe",
    "tracking_error_max",
    "tracking_error_rms",
    "task_not_complete",
    "ground_contact",
    "attitude_quaternion_nonfinite",
    "attitude_diverged",
    "angular_rate_diverged",
    "active_motor_nan",
    "motor_saturation",
    "missing_position_or_setpoint_window",
}
INFRASTRUCTURE_REASONS = {
    "offboard_control_signal_lost",
    "classical_nav_state_exit",
}


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_safety_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        path = DEFAULT_SAFETY_CONFIG
    if not path.exists():
        return {}
    return load_json(path)


def safety_thresholds(theta: dict[str, Any], safety_config: dict[str, Any]) -> dict[str, Any]:
    thresholds = dict(safety_config.get("safe_thresholds", {}))
    legacy = theta.get("safe_thresholds", {})
    if legacy and not thresholds:
        thresholds.update(legacy)
    return thresholds


def threshold(thresholds: dict[str, Any], name: str) -> float:
    value = thresholds.get(name)
    if value is None:
        raise KeyError(f"missing safety threshold {name}; define it in config/m2_safety_envelope.json")
    return float(value)


def first_dataset(ulog: ULog, name: str):
    matches = [dataset for dataset in ulog.data_list if dataset.name == name]
    return matches[0] if matches else None


def data_field(data: dict[str, np.ndarray], *names: str) -> np.ndarray:
    for name in names:
        if name in data:
            return data[name]
    raise KeyError(f"missing field, tried {names}")


def vector3(data: dict[str, np.ndarray], stem: str) -> np.ndarray:
    return np.column_stack(
        [
            data_field(data, f"{stem}[0]", f"{stem}_0", stem + ".0"),
            data_field(data, f"{stem}[1]", f"{stem}_1", stem + ".1"),
            data_field(data, f"{stem}[2]", f"{stem}_2", stem + ".2"),
        ]
    ).astype(float)


def quaternion(data: dict[str, np.ndarray]) -> np.ndarray:
    return np.column_stack(
        [
            data_field(data, "q[0]", "q_0"),
            data_field(data, "q[1]", "q_1"),
            data_field(data, "q[2]", "q_2"),
            data_field(data, "q[3]", "q_3"),
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


def quat_to_roll_pitch(q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    q0 = q[:, 0]
    q1 = q[:, 1]
    q2 = q[:, 2]
    q3 = q[:, 3]
    roll = np.arctan2(2.0 * (q0 * q1 + q2 * q3), 1.0 - 2.0 * (q1 * q1 + q2 * q2))
    sin_pitch = 2.0 * (q0 * q2 - q3 * q1)
    sin_pitch = np.clip(sin_pitch, -1.0, 1.0)
    pitch = np.arcsin(sin_pitch)
    return roll, pitch


def finite_float(value: float | np.floating | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value):
        return None
    return value


def finite_nanmean(values: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return None
    return finite_float(float(np.mean(values)))


def finite_nanmax(values: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return None
    return finite_float(float(np.max(values)))


def downsample_trace(ts: np.ndarray, values: np.ndarray, origin_us: int, max_points: int = 800) -> list[list[float]]:
    if len(ts) == 0:
        return []
    step = max(1, int(math.ceil(len(ts) / max_points)))
    result: list[list[float]] = []
    for idx in range(0, len(ts), step):
        row = [float((int(ts[idx]) - origin_us) / 1e6)]
        row.extend(float(v) if math.isfinite(float(v)) else math.nan for v in values[idx])
        result.append(row)
    return result


def task_event_elapsed_us(task: dict[str, Any], name: str) -> int | None:
    for event in task.get("events", []):
        if event.get("name") == name:
            return int(round(float(event.get("elapsed_s", 0.0)) * 1e6))
    return None


def extract_metrics(
    ulog_path: Path,
    theta: dict[str, Any],
    task: dict[str, Any],
    controller: str,
    safety_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safety_config = safety_config or {}
    ulog = ULog(str(ulog_path))
    topic_names = sorted({dataset.name for dataset in ulog.data_list})

    status = first_dataset(ulog, "vehicle_status")
    failsafe_flags = first_dataset(ulog, "failsafe_flags")
    lpos = first_dataset(ulog, "vehicle_local_position")
    att = first_dataset(ulog, "vehicle_attitude")
    rates = first_dataset(ulog, "vehicle_angular_velocity")
    setpoint = first_dataset(ulog, "trajectory_setpoint")
    motors = first_dataset(ulog, "actuator_motors")
    raptor_status = first_dataset(ulog, "raptor_status")

    target_nav = NAV_STATE_BY_CONTROLLER[controller]
    mode_confirmed = bool(task.get("mode_confirmed", False))
    active_us = None
    active_us_from_nav = None
    if status is not None and "nav_state" in status.data:
        nav = status.data["nav_state"].astype(int)
        idx = np.where(nav == target_nav)[0]
        if len(idx):
            active_us_from_nav = int(status.data["timestamp"][idx[0]])
            active_us = active_us_from_nav
            mode_confirmed = True

    task_active_us = task.get("controller_active_us")
    if active_us is None and isinstance(task_active_us, int) and task_active_us < 10**12:
        active_us = task_active_us

    active_elapsed_us = task_event_elapsed_us(task, "controller_active")
    trajectory_elapsed_us = task_event_elapsed_us(task, "trajectory_start")
    mission_elapsed_us = task_event_elapsed_us(task, "mission_end")
    if active_us is not None and active_elapsed_us is not None:
        origin_us = int(active_us - active_elapsed_us)
    else:
        origin_us = int(ulog.start_timestamp)

    if trajectory_elapsed_us is not None:
        trajectory_start_us = int(origin_us + trajectory_elapsed_us)
    elif isinstance(task.get("trajectory_start_us"), int) and task["trajectory_start_us"] < 10**12:
        trajectory_start_us = int(task["trajectory_start_us"])
    else:
        trajectory_start_us = active_us

    if mission_elapsed_us is not None:
        mission_end_us = int(origin_us + mission_elapsed_us)
    elif isinstance(task.get("mission_end_us"), int) and task["mission_end_us"] < 10**12:
        mission_end_us = int(task["mission_end_us"])
    else:
        mission_end_us = None
    thresholds = safety_thresholds(theta, safety_config)

    metrics: dict[str, Any] = {
        "tag": theta.get("tag"),
        "controller": controller,
        "ulog": str(ulog_path),
        "ulog_start_timestamp_us": int(ulog.start_timestamp),
        "topics_present": topic_names,
        "required_topics_missing": [
            name
            for name in [
                "trajectory_setpoint",
                "vehicle_local_position",
                "vehicle_angular_velocity",
                "vehicle_attitude",
                "vehicle_status",
                "actuator_motors",
            ]
            if name not in topic_names
        ],
        "mode_confirmed": mode_confirmed,
        "target_nav_state": target_nav,
        "controller_active_us_from_nav_state": active_us_from_nav,
        "controller_active_us": active_us,
        "trajectory_start_us": trajectory_start_us,
        "mission_end_us": mission_end_us,
        "task_to_ulog_origin_us": origin_us,
        "safe_thresholds": thresholds,
        "safety_config": str(safety_config.get("_path", DEFAULT_SAFETY_CONFIG)),
        "noise_floor": safety_config.get("noise_floor", {}),
    }

    safe_reasons: list[str] = []
    infrastructure_reasons: list[str] = []
    if metrics["required_topics_missing"]:
        safe_reasons.append("missing_required_topics")
    if not mode_confirmed:
        safe_reasons.append("controller_mode_not_confirmed")

    # vehicle_status: disarm/failsafe and nav-state evidence.
    if status is not None:
        sts = status.data["timestamp"].astype(np.int64)
        smask = mask_window(sts, active_us, mission_end_us)
        nav_values = status.data["nav_state"].astype(int)
        metrics["nav_states"] = sorted({int(v) for v in nav_values.tolist()})
        if np.any(smask):
            arming_state = status.data["arming_state"].astype(int)[smask]
            failsafe = status.data["failsafe"].astype(bool)[smask]
            nav_window = nav_values[smask]
            metrics["disarmed_in_window"] = bool(np.any(arming_state != 2))
            metrics["failsafe_in_window"] = bool(np.any(failsafe))
            metrics["nav_states_in_window"] = sorted({int(v) for v in nav_window.tolist()})
            metrics["target_nav_state_fraction"] = finite_float(float(np.mean(nav_window == target_nav)))
            if metrics["disarmed_in_window"]:
                safe_reasons.append("unexpected_disarm")
            if metrics["failsafe_in_window"]:
                safe_reasons.append("failsafe")
            target_fraction = metrics["target_nav_state_fraction"]
            if controller == "classical" and target_fraction is not None and target_fraction < 0.98:
                infrastructure_reasons.append("classical_nav_state_exit")
        else:
            metrics["disarmed_in_window"] = None
            metrics["failsafe_in_window"] = None
            metrics["nav_states_in_window"] = []
            metrics["target_nav_state_fraction"] = None

    if failsafe_flags is not None:
        fts = failsafe_flags.data["timestamp"].astype(np.int64)
        fmask = mask_window(fts, active_us, mission_end_us)
        for field in ["offboard_control_signal_lost", "mode_req_offboard_signal"]:
            if field in failsafe_flags.data and np.any(fmask):
                active = bool(np.any(failsafe_flags.data[field].astype(bool)[fmask]))
                metrics[f"{field}_in_window"] = active
                if controller == "classical" and field == "offboard_control_signal_lost" and active:
                    infrastructure_reasons.append(field)
            else:
                metrics[f"{field}_in_window"] = None

    # Position tracking against the logged commanded trajectory_setpoint.
    if lpos is not None and setpoint is not None:
        lts = lpos.data["timestamp"].astype(np.int64)
        lmask = mask_window(lts, trajectory_start_us, mission_end_us)
        sts = setpoint.data["timestamp"].astype(np.int64)
        smask = mask_window(sts, trajectory_start_us, mission_end_us)
        if np.any(lmask) and np.any(smask):
            pos = np.column_stack([lpos.data["x"], lpos.data["y"], lpos.data["z"]]).astype(float)[lmask]
            pos_ts = lts[lmask]
            sp_pos = vector3(setpoint.data, "position")[smask]
            sp_ts = sts[smask]
            sp_interp = interp_columns(sp_ts, sp_pos, pos_ts)
            err = np.linalg.norm(pos - sp_interp, axis=1)
            finite_err = err[np.isfinite(err)]
            metrics["tracking_error_max_m"] = finite_float(np.nanmax(finite_err)) if len(finite_err) else None
            metrics["tracking_error_rms_m"] = finite_float(math.sqrt(float(np.nanmean(finite_err * finite_err)))) if len(finite_err) else None
            metrics["final_error_m"] = finite_float(err[-1]) if len(err) else None
            metrics["local_position_z_min"] = finite_float(np.nanmin(pos[:, 2]))
            metrics["local_position_z_max"] = finite_float(np.nanmax(pos[:, 2]))
            metrics["min_altitude_agl_m"] = finite_float(np.nanmin(-pos[:, 2]))
            metrics["position_trace"] = downsample_trace(pos_ts, pos, int(origin_us))
            metrics["setpoint_trace"] = downsample_trace(pos_ts, sp_interp, int(origin_us))
            metrics["commanded_setpoint_span_m"] = finite_float(
                np.nanmax(np.linalg.norm(sp_interp - sp_interp[0], axis=1))
            )
            if metrics["tracking_error_max_m"] is not None and metrics["tracking_error_max_m"] > threshold(
                thresholds, "tracking_error_max_m"
            ):
                safe_reasons.append("tracking_error_max")
            if metrics["tracking_error_rms_m"] is not None and metrics["tracking_error_rms_m"] > threshold(
                thresholds, "tracking_error_rms_m"
            ):
                safe_reasons.append("tracking_error_rms")
            if metrics["final_error_m"] is not None and metrics["final_error_m"] > threshold(
                thresholds, "final_error_m"
            ):
                safe_reasons.append("task_not_complete")
            if metrics["min_altitude_agl_m"] is not None and metrics["min_altitude_agl_m"] < threshold(
                thresholds, "min_altitude_agl_m"
            ):
                safe_reasons.append("ground_contact")
        else:
            safe_reasons.append("missing_position_or_setpoint_window")

    # Attitude envelope.
    if att is not None:
        ats = att.data["timestamp"].astype(np.int64)
        amask = mask_window(ats, active_us, mission_end_us)
        if np.any(amask):
            q = quaternion(att.data)[amask]
            finite_q = np.all(np.isfinite(q), axis=1)
            metrics["attitude_quaternion_finite"] = bool(np.all(finite_q))
            roll, pitch = quat_to_roll_pitch(q)
            roll_pitch_abs = np.maximum(np.abs(roll), np.abs(pitch))
            metrics["roll_pitch_max_deg"] = finite_float(np.rad2deg(np.nanmax(roll_pitch_abs)))
            metrics["roll_pitch_std_deg"] = finite_float(np.rad2deg(np.nanstd(roll_pitch_abs)))
            if not metrics["attitude_quaternion_finite"]:
                safe_reasons.append("attitude_quaternion_nonfinite")
            if metrics["roll_pitch_max_deg"] is not None and metrics["roll_pitch_max_deg"] > threshold(
                thresholds, "roll_pitch_max_deg"
            ):
                safe_reasons.append("attitude_diverged")

    # Angular velocity envelope.
    if rates is not None:
        rts = rates.data["timestamp"].astype(np.int64)
        rmask = mask_window(rts, active_us, mission_end_us)
        if np.any(rmask):
            omega = vector3(rates.data, "xyz")[rmask]
            omega_norm = np.linalg.norm(omega, axis=1)
            metrics["angular_rate_max_rad_s"] = finite_float(np.nanmax(omega_norm))
            metrics["angular_rate_std_rad_s"] = finite_float(np.nanstd(omega_norm))
            if metrics["angular_rate_max_rad_s"] is not None and metrics["angular_rate_max_rad_s"] > threshold(
                thresholds, "angular_rate_max_rad_s"
            ):
                safe_reasons.append("angular_rate_diverged")

    # Active motor NaNs and saturation proxy.
    if motors is not None:
        mts = motors.data["timestamp"].astype(np.int64)
        mmask = mask_window(mts, active_us, mission_end_us)
        active_nan_count = 0
        unused_nan_count = 0
        active_values: list[np.ndarray] = []
        for idx in range(12):
            field = f"control[{idx}]"
            if field not in motors.data:
                continue
            values = motors.data[field][mmask].astype(float) if np.any(mmask) else motors.data[field].astype(float)
            nan_count = int(np.isnan(values).sum())
            if idx < ACTIVE_MOTORS:
                active_nan_count += nan_count
                active_values.append(values)
            else:
                unused_nan_count += nan_count
        metrics["active_motor_nan_count"] = active_nan_count
        metrics["unused_motor_nan_count"] = unused_nan_count
        if active_nan_count:
            safe_reasons.append("active_motor_nan")
        if active_values:
            controls = np.column_stack(active_values)
            finite = np.isfinite(controls)
            finite_count = int(finite.sum())
            if finite_count > 0:
                sat = finite & ((controls <= 0.02) | (controls >= 0.98) | (np.abs(controls) >= 0.98))
                metrics["motor_saturation_ratio"] = finite_float(float(np.count_nonzero(sat)) / float(finite_count))
                metrics["motor_saturation_count"] = int(np.count_nonzero(sat))
                if metrics["motor_saturation_ratio"] is not None and metrics["motor_saturation_ratio"] > threshold(
                    thresholds, "motor_saturation_ratio_max"
                ):
                    safe_reasons.append("motor_saturation")

    if raptor_status is not None:
        rsts = raptor_status.data["timestamp"].astype(np.int64)
        rmask = mask_window(rsts, active_us, mission_end_us)
        if np.any(rmask):
            metrics["raptor_status_active_count"] = int(np.count_nonzero(raptor_status.data["active"][rmask]))
            if "substep" in raptor_status.data:
                metrics["raptor_substeps"] = sorted({int(v) for v in raptor_status.data["substep"][rmask].tolist()})
            if "control_interval" in raptor_status.data:
                ci = raptor_status.data["control_interval"][rmask].astype(float)
                metrics["raptor_control_interval_mean_s"] = finite_nanmean(ci)
                metrics["raptor_control_interval_max_s"] = finite_nanmax(ci)
            if "trajectory_setpoint_dt_max_since_activation" in raptor_status.data:
                metrics["raptor_trajectory_setpoint_dt_max_since_activation_us"] = finite_nanmax(
                    raptor_status.data["trajectory_setpoint_dt_max_since_activation"][rmask].astype(float)
                )
            try:
                ref = vector3(raptor_status.data, "internal_reference_position")[rmask]
                if len(ref) > 0:
                    metrics["raptor_internal_reference_span_m"] = finite_nanmax(np.linalg.norm(ref - ref[0], axis=1))
            except KeyError:
                pass

    metrics["safe_reasons"] = sorted(set(safe_reasons))
    metrics["control_level_unsafe_reasons"] = sorted(set(safe_reasons) & CONTROL_LEVEL_REASONS)
    metrics["infrastructure_reasons"] = sorted(set(infrastructure_reasons) & INFRASTRUCTURE_REASONS)
    metrics["infrastructure_limited"] = bool(metrics["infrastructure_reasons"])
    metrics["safe"] = len(metrics["safe_reasons"]) == 0
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ulog", type=Path, required=True)
    parser.add_argument("--theta", type=Path, required=True)
    parser.add_argument("--task-json", type=Path)
    parser.add_argument("--controller", choices=["classical", "raptor"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--safety-config", type=Path, default=DEFAULT_SAFETY_CONFIG)
    args = parser.parse_args()

    theta = load_json(args.theta)
    task = load_json(args.task_json)
    safety_config = load_safety_config(args.safety_config)
    safety_config["_path"] = str(args.safety_config)
    metrics = extract_metrics(args.ulog, theta, task, args.controller, safety_config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"output": str(args.output), "safe": metrics["safe"], "safe_reasons": metrics["safe_reasons"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
