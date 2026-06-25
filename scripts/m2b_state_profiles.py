#!/usr/bin/env python3
"""Shared M2b-1 state-shim theta helpers."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import m2_map_elites


REPO_ROOT = Path(__file__).resolve().parents[1]
SAFETY_CONFIG = REPO_ROOT / "config/m2b_safety_envelope_4x_high_twr.json"
PROFILE_IDS = {"off": 0, "delay": 1, "bias": 2, "noise": 3, "nan": 4, "inf": 5}
CHANNEL_PREFIX = {"velocity": "V", "angular_velocity": "G", "attitude": "A"}


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(data, handle, sort_keys=True, allow_nan=False)
        handle.write("\n")


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def physical_params_for_twr(twr: float) -> dict[str, float]:
    mass = m2_map_elites.NOMINAL["mass"]
    t_max = float(twr) * mass * 9.80665 / 4.0
    thrust_scale = t_max / m2_map_elites.NOMINAL["t_max"]
    return {
        "SIH_MASS": mass,
        "SIH_T_MAX": t_max,
        "SIH_Q_MAX": m2_map_elites.NOMINAL["q_max"] * thrust_scale,
        "MPC_THR_HOVER": clamp(1.0 / float(twr), 0.25, 0.9),
    }


def shim_defaults() -> dict[str, int | float]:
    return {
        "M2B_EN": 0,
        "M2B_START": 0.0,
        "M2B_END": 0.0,
        "M2B_SEED": 20260624,
        "M2B_V_PROF": 0,
        "M2B_V_DLY": 0,
        "M2B_V_X": 0.0,
        "M2B_V_Y": 0.0,
        "M2B_V_Z": 0.0,
        "M2B_G_PROF": 0,
        "M2B_G_DLY": 0,
        "M2B_G_X": 0.0,
        "M2B_G_Y": 0.0,
        "M2B_G_Z": 0.0,
        "M2B_A_PROF": 0,
        "M2B_A_DLY": 0,
        "M2B_A_R": 0.0,
        "M2B_A_P": 0.0,
        "M2B_A_Y": 0.0,
    }


def shim_params(
    *,
    channel: str,
    profile: str,
    start_s: float,
    end_s: float,
    seed: int,
    delay_ms: int = 0,
    values: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> dict[str, int | float]:
    if channel not in CHANNEL_PREFIX:
        raise ValueError(f"unsupported M2b channel: {channel}")
    if profile not in PROFILE_IDS:
        raise ValueError(f"unsupported M2b profile: {profile}")
    params = shim_defaults()
    prefix = CHANNEL_PREFIX[channel]
    params["M2B_EN"] = 1 if profile != "off" else 0
    params["M2B_START"] = round(float(start_s), 4)
    params["M2B_END"] = round(float(end_s), 4)
    params["M2B_SEED"] = int(seed)
    params[f"M2B_{prefix}_PROF"] = PROFILE_IDS[profile]
    params[f"M2B_{prefix}_DLY"] = int(round(delay_ms))
    suffixes = ("X", "Y", "Z") if prefix != "A" else ("R", "P", "Y")
    for suffix, value in zip(suffixes, values):
        params[f"M2B_{prefix}_{suffix}"] = round(float(value), 8)
    return params


def base_state_theta(
    *,
    tag: str,
    seed: int,
    channel: str,
    profile: str,
    delay_ms: int = 0,
    values: tuple[float, float, float] = (0.0, 0.0, 0.0),
    twr: float = 2.3,
    sine_axis: str = "z",
    sine_amplitude_m: float = 0.22,
    sine_frequency_hz: float = 2.5,
    start_s: float = 22.0,
    end_s: float = 38.0,
    controller_switch_s: float = 18.0,
    trajectory_start_s: float = 22.0,
    mission_end_s: float = 38.0,
    mitigation: str = "absent_in_px4_mc_raptor_3042f906",
) -> dict[str, Any]:
    physical = physical_params_for_twr(twr)
    shim = shim_params(
        channel=channel,
        profile=profile,
        start_s=start_s,
        end_s=end_s,
        seed=seed,
        delay_ms=delay_ms,
        values=values,
    )
    params = dict(m2_map_elites.BASE_PX4_PARAMS)
    params.update({key: round(value, 8) for key, value in physical.items()})
    params.update(shim)
    boot_params = {key: round(value, 8) for key, value in physical.items()}
    boot_params.update(shim)
    theta: dict[str, Any] = {
        "tag": tag,
        "description": "M2b-1 adversarial shared-state shim theta.",
        "seed": int(seed),
        "airframe": {"sim": "sih", "model": "sihsim_x500_v2", "sys_autostart": 10046},
        "timing": {
            "controller_switch_s": round(float(controller_switch_s), 3),
            "trajectory_start_s": round(float(trajectory_start_s), 3),
            "mission_end_s": round(float(mission_end_s), 3),
            "mode_command_repeat_s": 0.5,
            "mode_command_timeout_s": 6.0,
            "px4_shutdown_margin_s": 6.0,
            "px4_shutdown_wall_slack_s": 22.0,
        },
        "setpoint": {
            "rate_hz": 100.0,
            "max_wall_timer_hz": 100.0,
            "hover_ned": [0.0, 0.0, -2.5],
            "yaw_rad": 0.0,
            "type": "sine",
            "step": {"delta_ned": [0.2, 0.0, 0.0]},
            "sine": {
                "axis": sine_axis,
                "amplitude_m": round(float(sine_amplitude_m), 4),
                "frequency_hz": round(float(sine_frequency_hz), 4),
            },
        },
        "boot_px4_params": boot_params,
        "px4_params": params,
        "environment": {
            "mass_kg": round(physical["SIH_MASS"], 4),
            "t_max_n": round(physical["SIH_T_MAX"], 4),
            "thrust_to_weight_ratio": round(float(twr), 4),
            "mpc_thr_hover": round(physical["MPC_THR_HOVER"], 4),
            "sih_wind_n": 0.0,
            "sih_wind_e": 0.0,
        },
        "faults": [],
        "sensor_perturbations": [
            {
                "type": "adversarial_shared_state_shim",
                "simulator": "sih",
                "mechanism": "PX4 publish-point patch before shared uORB topic publication",
                "shared_quantity": channel,
                "profile": profile,
                "delay_ms": int(round(delay_ms)),
                "values": [round(float(v), 8) for v in values],
                "start_s": round(float(start_s), 4),
                "end_s": round(float(end_s), 4),
                "timebase": "PX4 boot-time seconds, not m1_offboard_task elapsed seconds",
                "physical_credibility": "Topic-level transport delay/bias/noise is applied to both controllers; NaN/Inf profiles are marked as input-robustness probes.",
            }
        ],
        "divergence_thresholds": {"position_divergence_m": 1.0},
        "m2b_1": {
            "generator": "scripts/m2b_state_profiles.py",
            "shim_patch": "patches/px4/m2b_state_shim.patch",
            "channel": channel,
            "profile": profile,
            "delay_ms": int(round(delay_ms)),
            "values": [round(float(v), 8) for v in values],
            "start_s": round(float(start_s), 4),
            "end_s": round(float(end_s), 4),
            "timebase": "PX4 boot-time seconds",
            "thrust_to_weight_ratio": round(float(twr), 4),
            "mitigation": mitigation,
            "safety_config": str(SAFETY_CONFIG.relative_to(REPO_ROOT)),
        },
    }
    return theta


def run_fairness(theta_path: Path, docs_dir: Path, *, prefix: str = "m2b_1") -> tuple[Path | None, int | None]:
    theta = load_json(theta_path)
    tag = theta["tag"]
    classical_ulog = docs_dir / f"m1_{tag}_classical.ulg"
    raptor_ulog = docs_dir / f"m1_{tag}_raptor.ulg"
    if not classical_ulog.exists() or not raptor_ulog.exists():
        return None, None
    output = docs_dir / f"{prefix}_fairness_{tag}.json"
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/m2_5_estimator_fairness.py"),
        "--theta",
        str(theta_path),
        "--classical-ulog",
        str(classical_ulog),
        "--raptor-ulog",
        str(raptor_ulog),
        "--classical-task-json",
        str(docs_dir / f"m1_{tag}_classical_task.json"),
        "--raptor-task-json",
        str(docs_dir / f"m1_{tag}_raptor_task.json"),
        "--output",
        str(output),
        "--require-state-shim-delivery",
    ]
    with (docs_dir / f"{prefix}_fairness_{tag}.log").open("w", encoding="utf-8") as handle:
        handle.write("$ " + " ".join(cmd) + "\n")
        handle.flush()
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), stdout=handle, stderr=subprocess.STDOUT, check=False)
    return output, int(proc.returncode)


def summarize_compare(compare_path: str | None) -> dict[str, Any]:
    if not compare_path:
        return {}
    path = Path(compare_path)
    if not path.exists():
        return {}
    compare = load_json(path)
    return {
        "quadrant": compare.get("quadrant"),
        "primary_bug": bool(compare.get("primary_bug")),
        "classical_usable": bool(compare.get("classical_usable_for_primary")),
        "classical_safe": bool(compare.get("classical", {}).get("safe")),
        "raptor_safe": bool(compare.get("raptor", {}).get("safe")),
        "quality": float(compare.get("divergence", {}).get("quality") or 0.0),
        "effective_deltas": compare.get("divergence", {}).get("effective_deltas_above_noise_floor", {}),
        "classical_tracking_rms_m": compare.get("classical", {}).get("tracking_error_rms_m"),
        "raptor_tracking_rms_m": compare.get("raptor", {}).get("tracking_error_rms_m"),
        "classical_tracking_max_m": compare.get("classical", {}).get("tracking_error_max_m"),
        "raptor_tracking_max_m": compare.get("raptor", {}).get("tracking_error_max_m"),
        "classical_rate_max_rad_s": compare.get("classical", {}).get("angular_rate_max_rad_s"),
        "raptor_rate_max_rad_s": compare.get("raptor", {}).get("angular_rate_max_rad_s"),
        "classical_active_motor_nan_count": compare.get("classical", {}).get("active_motor_nan_count"),
        "raptor_active_motor_nan_count": compare.get("raptor", {}).get("active_motor_nan_count"),
    }


def evaluate_theta_record(
    theta: dict[str, Any],
    theta_path: Path,
    docs_dir: Path,
    index: int,
    *,
    run_timeout: int,
    eval_timeout: int,
    sim_speed_factor: float,
    safety_config: Path | None = None,
) -> dict[str, Any]:
    m2_map_elites.SAFETY_CONFIG = safety_config or SAFETY_CONFIG
    start = time.monotonic()
    result = m2_map_elites.evaluate_theta(
        theta,
        theta_path,
        docs_dir,
        index,
        run_timeout,
        eval_timeout,
        m2_map_elites.os_environ_with_speed(sim_speed_factor),
    )
    record = result.as_dict()
    record["elapsed_wall_s_outer"] = time.monotonic() - start
    record.update(summarize_compare(result.compare_path))
    fairness_path: Path | None = None
    fairness_returncode: int | None = None
    if result.returncode == 0:
        fairness_path, fairness_returncode = run_fairness(theta_path, docs_dir)
    record["fairness_path"] = str(fairness_path) if fairness_path else None
    record["fairness_returncode"] = fairness_returncode
    if fairness_path:
        fairness = load_json(fairness_path).get("fairness", {})
        record["fair_shared_state_shim_pollution"] = bool(fairness.get("fair_shared_state_shim_pollution"))
        record["state_shim_topic_checks"] = fairness.get("state_shim_topic_checks")
        record["state_shim_delivery_valid"] = bool(fairness.get("state_shim_delivery_valid"))
        record["state_shim_delivery_failures"] = fairness.get("state_shim_delivery_failures", [])
        if fairness_returncode:
            record["invalid_reason"] = "state_shim_delivery_failed"
    return record
