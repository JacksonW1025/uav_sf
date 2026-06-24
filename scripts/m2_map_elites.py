#!/usr/bin/env python3
"""M2 guided theta search using a small MAP-Elites loop.

The evaluator is the M1 differential runner. This script only bootstraps and
guides candidates; it is not a random/grid baseline experiment.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SAFETY_CONFIG = REPO_ROOT / "config/m2_safety_envelope.json"

NOMINAL = {
    "mass": 2.0,
    "ixx": 0.0216667,
    "iyy": 0.0216667,
    "izz": 0.04,
    "t_max": 8.54858,
    "q_max": 0.136777,
    "l_roll": 0.21,
    "l_pitch": 0.13,
    "kdv": 1.0,
    "kdw": 0.025,
    "t_tau": 0.02,
}

BASE_PX4_PARAMS = {
    "NAV_DLL_ACT": 0,
    "COM_DISARM_LAND": -1,
    "COM_OF_LOSS_T": 5.0,
    "IMU_GYRO_RATEMAX": 400,
    "COM_RC_IN_MODE": 4,
    "COM_RCL_EXCEPT": 8,
    "MC_RAPTOR_ENABLE": 1,
    "MC_RAPTOR_OFFB": 0,
    "MC_RAPTOR_INTREF": 0,
    "SYS_FAILURE_EN": 1,
    "CA_FAILURE_MODE": 1,
}

FAMILIES = ["A_estimator", "A_physical", "A_wind", "B_timing", "C_setpoint"]
CONFIRM_SEEDS = [202601, 202602, 202603]


@dataclass
class EvalResult:
    index: int
    tag: str
    theta_path: str
    docs_dir: str
    returncode: int
    elapsed_wall_s: float
    compare_path: str | None
    quadrant: str | None
    primary_bug: bool
    classical_usable: bool
    classical_safe: bool | None
    raptor_safe: bool | None
    infrastructure_limited: bool | None
    quality: float
    feature_bin: str
    severity: float
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "tag": self.tag,
            "theta_path": self.theta_path,
            "docs_dir": self.docs_dir,
            "returncode": self.returncode,
            "elapsed_wall_s": self.elapsed_wall_s,
            "compare_path": self.compare_path,
            "quadrant": self.quadrant,
            "primary_bug": self.primary_bug,
            "classical_usable": self.classical_usable,
            "classical_safe": self.classical_safe,
            "raptor_safe": self.raptor_safe,
            "infrastructure_limited": self.infrastructure_limited,
            "quality": self.quality,
            "feature_bin": self.feature_bin,
            "severity": self.severity,
            "error": self.error,
        }


def load_json(path: Path) -> dict[str, Any]:
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


def choose_family(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.35:
        return "A_estimator"
    if roll < 0.70:
        return "A_physical"
    if roll < 0.83:
        return "A_wind"
    if roll < 0.96:
        return "B_timing"
    return "C_setpoint"


def random_genome(rng: random.Random, family: str | None = None) -> dict[str, Any]:
    family = family or choose_family(rng)
    genome: dict[str, Any] = {
        "family_hint": family,
        "mass_scale": rng.uniform(0.9, 1.18),
        "inertia_roll_scale": rng.uniform(0.75, 1.65),
        "inertia_pitch_scale": rng.uniform(0.75, 1.65),
        "inertia_yaw_scale": rng.uniform(0.75, 1.9),
        "cross_xy": rng.uniform(-0.12, 0.12),
        "cross_xz": rng.uniform(-0.08, 0.08),
        "cross_yz": rng.uniform(-0.08, 0.08),
        "thrust_scale": rng.uniform(0.82, 1.08),
        "torque_scale": rng.uniform(0.7, 1.35),
        "roll_arm_scale": rng.uniform(0.82, 1.22),
        "pitch_arm_scale": rng.uniform(0.82, 1.22),
        "drag_scale": rng.uniform(0.3, 2.0),
        "angular_damper_scale": rng.uniform(0.25, 2.2),
        "thrust_tau_s": rng.uniform(0.015, 0.08),
        "wind_n": rng.uniform(-2.0, 2.0),
        "wind_e": rng.uniform(-2.0, 2.0),
        "gps_delay_ms": rng.uniform(0.0, 180.0),
        "gps_position_noise_m": rng.uniform(0.25, 2.0),
        "gps_velocity_noise_m_s": rng.uniform(0.12, 1.5),
        "gps_position_gate_sd": rng.uniform(2.0, 8.0),
        "gps_velocity_gate_sd": rng.uniform(2.0, 8.0),
        "ekf_tau_vel_s": rng.uniform(0.15, 0.75),
        "ekf_tau_pos_s": rng.uniform(0.15, 0.75),
        "imu_pos_x_m": rng.uniform(-0.05, 0.05),
        "imu_pos_y_m": rng.uniform(-0.05, 0.05),
        "imu_pos_z_m": rng.uniform(-0.04, 0.04),
        "switch_s": rng.uniform(16.0, 22.0),
        "setpoint_rate_hz": rng.choice([30.0, 50.0, 75.0, 100.0]),
        "setpoint_type": rng.choice(["step", "sine"]),
        "setpoint_axis": rng.choice(["x", "y"]),
        "step_m": rng.uniform(0.05, 0.45),
        "sine_amplitude_m": rng.uniform(0.05, 0.45),
        "sine_frequency_hz": rng.uniform(0.8, 5.5),
    }

    if family == "A_estimator":
        genome["gps_delay_ms"] = rng.uniform(60.0, 260.0)
        genome["gps_position_noise_m"] = rng.uniform(0.05, 1.5)
        genome["gps_velocity_noise_m_s"] = rng.uniform(0.03, 1.0)
        genome["gps_position_gate_sd"] = rng.uniform(1.0, 10.0)
        genome["gps_velocity_gate_sd"] = rng.uniform(1.0, 10.0)
        genome["ekf_tau_vel_s"] = rng.uniform(0.1, 1.0)
        genome["ekf_tau_pos_s"] = rng.uniform(0.1, 1.0)
        genome["imu_pos_x_m"] = rng.uniform(-0.18, 0.18)
        genome["imu_pos_y_m"] = rng.uniform(-0.18, 0.18)
        genome["imu_pos_z_m"] = rng.uniform(-0.12, 0.12)
        genome["setpoint_type"] = "sine"
        genome["sine_amplitude_m"] = rng.uniform(0.2, 0.5)
        genome["sine_frequency_hz"] = rng.uniform(2.0, 6.0)
        genome["setpoint_rate_hz"] = rng.choice([50.0, 75.0, 100.0])
    elif family == "A_physical":
        genome["mass_scale"] = rng.uniform(0.85, 1.38)
        genome["thrust_scale"] = rng.uniform(0.72, 1.05)
        genome["inertia_roll_scale"] = rng.uniform(0.55, 2.15)
        genome["inertia_pitch_scale"] = rng.uniform(0.55, 2.15)
        genome["inertia_yaw_scale"] = rng.uniform(0.55, 2.45)
        genome["thrust_tau_s"] = rng.uniform(0.02, 0.12)
    elif family == "A_wind":
        genome["wind_n"] = rng.uniform(-6.0, 6.0)
        genome["wind_e"] = rng.uniform(-6.0, 6.0)
    elif family == "B_timing":
        genome["switch_s"] = rng.uniform(14.0, 24.0)
        genome["setpoint_rate_hz"] = rng.choice([20.0, 25.0, 30.0, 50.0])
    elif family == "C_setpoint":
        genome["setpoint_type"] = "sine"
        genome["sine_amplitude_m"] = rng.uniform(0.2, 0.5)
        genome["sine_frequency_hz"] = rng.uniform(4.0, 8.0)
        genome["setpoint_rate_hz"] = rng.choice([50.0, 75.0, 100.0])

    return normalize_genome(genome)


def nominal_genome() -> dict[str, Any]:
    return normalize_genome(
        {
            "family_hint": "A_physical",
            "mass_scale": 1.0,
            "inertia_roll_scale": 1.0,
            "inertia_pitch_scale": 1.0,
            "inertia_yaw_scale": 1.0,
            "cross_xy": 0.0,
            "cross_xz": 0.0,
            "cross_yz": 0.0,
            "thrust_scale": 1.0,
            "torque_scale": 1.0,
            "roll_arm_scale": 1.0,
            "pitch_arm_scale": 1.0,
            "drag_scale": 1.0,
            "angular_damper_scale": 1.0,
            "thrust_tau_s": NOMINAL["t_tau"],
            "wind_n": 0.0,
            "wind_e": 0.0,
            "gps_delay_ms": 0.0,
            "gps_position_noise_m": 0.5,
            "gps_velocity_noise_m_s": 0.3,
            "gps_position_gate_sd": 5.0,
            "gps_velocity_gate_sd": 5.0,
            "ekf_tau_vel_s": 0.25,
            "ekf_tau_pos_s": 0.25,
            "imu_pos_x_m": 0.0,
            "imu_pos_y_m": 0.0,
            "imu_pos_z_m": 0.0,
            "switch_s": 18.0,
            "setpoint_rate_hz": 100.0,
            "setpoint_type": "step",
            "setpoint_axis": "x",
            "step_m": 0.25,
            "sine_amplitude_m": 0.25,
            "sine_frequency_hz": 2.0,
        }
    )


def seed_bank() -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []

    def add(**updates: Any) -> None:
        genome = nominal_genome()
        genome.update(updates)
        seeds.append(normalize_genome(genome))

    add(
        family_hint="A_estimator",
        gps_delay_ms=120.0,
        gps_position_noise_m=0.25,
        gps_velocity_noise_m_s=0.08,
        ekf_tau_vel_s=0.25,
        ekf_tau_pos_s=0.25,
        setpoint_type="sine",
        sine_amplitude_m=0.35,
        sine_frequency_hz=4.0,
        setpoint_rate_hz=100.0,
    )
    add(
        family_hint="A_estimator",
        gps_delay_ms=220.0,
        gps_position_noise_m=0.1,
        gps_velocity_noise_m_s=0.05,
        gps_position_gate_sd=8.0,
        gps_velocity_gate_sd=8.0,
        ekf_tau_vel_s=0.55,
        ekf_tau_pos_s=0.55,
        setpoint_type="sine",
        sine_amplitude_m=0.3,
        sine_frequency_hz=5.0,
        setpoint_rate_hz=100.0,
    )
    add(
        family_hint="A_physical",
        mass_scale=1.0,
        thrust_scale=0.72,
        thrust_tau_s=0.14,
        angular_damper_scale=1.0,
        inertia_roll_scale=1.0,
        inertia_pitch_scale=1.0,
        inertia_yaw_scale=1.0,
        cross_xy=0.0,
        switch_s=18.0,
        setpoint_type="step",
        step_m=0.4,
    )
    add(
        family_hint="A_physical",
        mass_scale=1.18,
        thrust_scale=0.82,
        thrust_tau_s=0.09,
        inertia_roll_scale=1.55,
        inertia_pitch_scale=1.45,
        inertia_yaw_scale=1.9,
        setpoint_type="sine",
        sine_amplitude_m=0.2,
        sine_frequency_hz=4.5,
        setpoint_rate_hz=50.0,
    )
    add(
        family_hint="A_physical",
        mass_scale=1.0,
        thrust_scale=0.78,
        thrust_tau_s=0.12,
        angular_damper_scale=0.15,
        inertia_roll_scale=0.6,
        inertia_pitch_scale=2.0,
        cross_xy=0.12,
        setpoint_type="step",
        step_m=0.4,
    )
    add(
        family_hint="A_physical",
        mass_scale=0.9,
        thrust_scale=1.0,
        torque_scale=0.5,
        roll_arm_scale=0.7,
        pitch_arm_scale=1.3,
        inertia_yaw_scale=2.4,
        setpoint_type="sine",
        sine_amplitude_m=0.35,
        sine_frequency_hz=5.5,
    )
    add(
        family_hint="A_wind",
        wind_n=5.0,
        wind_e=0.0,
        mass_scale=1.05,
        thrust_tau_s=0.06,
        setpoint_type="step",
        step_m=0.35,
    )
    add(
        family_hint="A_wind",
        wind_n=3.5,
        wind_e=-3.5,
        thrust_scale=0.88,
        setpoint_type="sine",
        sine_amplitude_m=0.3,
        sine_frequency_hz=4.8,
        setpoint_rate_hz=50.0,
    )
    add(
        family_hint="B_timing",
        switch_s=14.0,
        setpoint_rate_hz=20.0,
        thrust_tau_s=0.07,
        setpoint_type="sine",
        sine_amplitude_m=0.45,
        sine_frequency_hz=3.8,
    )
    add(
        family_hint="C_setpoint",
        setpoint_type="sine",
        sine_amplitude_m=0.5,
        sine_frequency_hz=7.5,
        setpoint_rate_hz=100.0,
        thrust_tau_s=0.05,
    )
    add(
        family_hint="A_physical",
        mass_scale=1.28,
        thrust_scale=0.9,
        drag_scale=0.0,
        angular_damper_scale=0.0,
        thrust_tau_s=0.08,
        inertia_roll_scale=1.9,
        inertia_pitch_scale=0.55,
        cross_xz=0.1,
        cross_yz=-0.1,
        setpoint_type="step",
        step_m=0.45,
    )
    return seeds


def mutate_genome(parent: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    genome = dict(parent)
    numeric_sigmas = {
        "mass_scale": 0.08,
        "inertia_roll_scale": 0.18,
        "inertia_pitch_scale": 0.18,
        "inertia_yaw_scale": 0.22,
        "cross_xy": 0.04,
        "cross_xz": 0.03,
        "cross_yz": 0.03,
        "thrust_scale": 0.06,
        "torque_scale": 0.12,
        "roll_arm_scale": 0.08,
        "pitch_arm_scale": 0.08,
        "drag_scale": 0.25,
        "angular_damper_scale": 0.25,
        "thrust_tau_s": 0.015,
        "wind_n": 1.2,
        "wind_e": 1.2,
        "gps_delay_ms": 35.0,
        "gps_position_noise_m": 0.2,
        "gps_velocity_noise_m_s": 0.08,
        "gps_position_gate_sd": 1.0,
        "gps_velocity_gate_sd": 1.0,
        "ekf_tau_vel_s": 0.12,
        "ekf_tau_pos_s": 0.12,
        "imu_pos_x_m": 0.04,
        "imu_pos_y_m": 0.04,
        "imu_pos_z_m": 0.03,
        "switch_s": 1.0,
        "step_m": 0.08,
        "sine_amplitude_m": 0.08,
        "sine_frequency_hz": 0.8,
    }
    for key, sigma in numeric_sigmas.items():
        if rng.random() < 0.35:
            genome[key] = float(genome[key]) + rng.gauss(0.0, sigma)
    if rng.random() < 0.15:
        genome["setpoint_rate_hz"] = rng.choice([20.0, 25.0, 30.0, 50.0, 75.0, 100.0])
    if rng.random() < 0.12:
        genome["setpoint_axis"] = rng.choice(["x", "y"])
    if rng.random() < 0.10:
        genome["setpoint_type"] = rng.choice(["step", "sine"])
    if rng.random() < 0.08:
        genome["family_hint"] = choose_family(rng)
    return normalize_genome(genome)


def normalize_genome(genome: dict[str, Any]) -> dict[str, Any]:
    bounds = {
        "mass_scale": (0.75, 1.45),
        "inertia_roll_scale": (0.45, 2.3),
        "inertia_pitch_scale": (0.45, 2.3),
        "inertia_yaw_scale": (0.45, 2.6),
        "cross_xy": (-0.18, 0.18),
        "cross_xz": (-0.12, 0.12),
        "cross_yz": (-0.12, 0.12),
        "thrust_scale": (0.68, 1.15),
        "torque_scale": (0.45, 1.6),
        "roll_arm_scale": (0.65, 1.35),
        "pitch_arm_scale": (0.65, 1.35),
        "drag_scale": (0.0, 2.8),
        "angular_damper_scale": (0.0, 3.0),
        "thrust_tau_s": (0.01, 0.14),
        "wind_n": (-6.0, 6.0),
        "wind_e": (-6.0, 6.0),
        "gps_delay_ms": (0.0, 300.0),
        "gps_position_noise_m": (0.01, 10.0),
        "gps_velocity_noise_m_s": (0.01, 5.0),
        "gps_position_gate_sd": (1.0, 12.0),
        "gps_velocity_gate_sd": (1.0, 12.0),
        "ekf_tau_vel_s": (0.1, 1.0),
        "ekf_tau_pos_s": (0.1, 1.0),
        "imu_pos_x_m": (-0.25, 0.25),
        "imu_pos_y_m": (-0.25, 0.25),
        "imu_pos_z_m": (-0.20, 0.20),
        "switch_s": (14.0, 24.0),
        "step_m": (0.0, 0.5),
        "sine_amplitude_m": (0.0, 0.5),
        "sine_frequency_hz": (0.5, 8.0),
    }
    out = dict(genome)
    for key, (lo, hi) in bounds.items():
        out[key] = clamp(float(out[key]), lo, hi)
    out["setpoint_rate_hz"] = float(out.get("setpoint_rate_hz", 50.0))
    if out["setpoint_rate_hz"] < 20.0:
        out["setpoint_rate_hz"] = 20.0
    out["setpoint_axis"] = out.get("setpoint_axis", "x") if out.get("setpoint_axis") in {"x", "y"} else "x"
    out["setpoint_type"] = out.get("setpoint_type", "step") if out.get("setpoint_type") in {"step", "sine"} else "step"
    out["family_hint"] = out.get("family_hint", "A_physical")
    return out


def hover_throttle(mass_kg: float, t_max_n: float) -> float:
    return mass_kg * 9.80665 / (4.0 * t_max_n)


def physical_params(genome: dict[str, Any]) -> dict[str, float]:
    mass = NOMINAL["mass"] * float(genome["mass_scale"])
    t_max = NOMINAL["t_max"] * float(genome["thrust_scale"])
    hover = hover_throttle(mass, t_max)
    if hover > 0.9:
        t_max = mass * 9.80665 / (4.0 * 0.88)
        hover = hover_throttle(mass, t_max)
    ixx = NOMINAL["ixx"] * float(genome["mass_scale"]) * float(genome["inertia_roll_scale"])
    iyy = NOMINAL["iyy"] * float(genome["mass_scale"]) * float(genome["inertia_pitch_scale"])
    izz = NOMINAL["izz"] * float(genome["mass_scale"]) * float(genome["inertia_yaw_scale"])
    ixy = float(genome["cross_xy"]) * math.sqrt(ixx * iyy)
    ixz = float(genome["cross_xz"]) * math.sqrt(ixx * izz)
    iyz = float(genome["cross_yz"]) * math.sqrt(iyy * izz)
    return {
        "SIH_MASS": mass,
        "SIH_IXX": ixx,
        "SIH_IYY": iyy,
        "SIH_IZZ": izz,
        "SIH_IXY": ixy,
        "SIH_IXZ": ixz,
        "SIH_IYZ": iyz,
        "SIH_T_MAX": t_max,
        "SIH_Q_MAX": NOMINAL["q_max"] * float(genome["torque_scale"]),
        "SIH_L_ROLL": NOMINAL["l_roll"] * float(genome["roll_arm_scale"]),
        "SIH_L_PITCH": NOMINAL["l_pitch"] * float(genome["pitch_arm_scale"]),
        "SIH_KDV": NOMINAL["kdv"] * float(genome["drag_scale"]),
        "SIH_KDW": NOMINAL["kdw"] * float(genome["angular_damper_scale"]),
        "SIH_T_TAU": float(genome["thrust_tau_s"]),
        "SIH_WIND_N": float(genome["wind_n"]),
        "SIH_WIND_E": float(genome["wind_e"]),
        "MPC_THR_HOVER": clamp(hover, 0.25, 0.9),
    }


def estimator_params(genome: dict[str, Any]) -> dict[str, float | int]:
    gps_delay_ms = int(round(float(genome["gps_delay_ms"])))
    return {
        "SENS_GPS0_DELAY": gps_delay_ms,
        "SENS_GPS1_DELAY": gps_delay_ms,
        "EKF2_DELAY_MAX": max(200, gps_delay_ms),
        "EKF2_GPS_P_NOISE": round(float(genome["gps_position_noise_m"]), 4),
        "EKF2_GPS_V_NOISE": round(float(genome["gps_velocity_noise_m_s"]), 4),
        "EKF2_GPS_P_GATE": round(float(genome["gps_position_gate_sd"]), 4),
        "EKF2_GPS_V_GATE": round(float(genome["gps_velocity_gate_sd"]), 4),
        "EKF2_TAU_VEL": round(float(genome["ekf_tau_vel_s"]), 4),
        "EKF2_TAU_POS": round(float(genome["ekf_tau_pos_s"]), 4),
        "EKF2_IMU_POS_X": round(float(genome["imu_pos_x_m"]), 4),
        "EKF2_IMU_POS_Y": round(float(genome["imu_pos_y_m"]), 4),
        "EKF2_IMU_POS_Z": round(float(genome["imu_pos_z_m"]), 4),
    }


def genome_severity(genome: dict[str, Any]) -> dict[str, float]:
    estimator = max(
        abs(float(genome["gps_delay_ms"])) / 300.0,
        abs(float(genome["gps_position_noise_m"]) - 0.5) / 9.5,
        abs(float(genome["gps_velocity_noise_m_s"]) - 0.3) / 4.7,
        abs(float(genome["gps_position_gate_sd"]) - 5.0) / 7.0,
        abs(float(genome["gps_velocity_gate_sd"]) - 5.0) / 7.0,
        abs(float(genome["ekf_tau_vel_s"]) - 0.25) / 0.75,
        abs(float(genome["ekf_tau_pos_s"]) - 0.25) / 0.75,
        math.hypot(float(genome["imu_pos_x_m"]), float(genome["imu_pos_y_m"])) / 0.25,
        abs(float(genome["imu_pos_z_m"])) / 0.2,
    )
    physical = max(
        abs(float(genome["mass_scale"]) - 1.0) / 0.45,
        abs(float(genome["thrust_scale"]) - 1.0) / 0.32,
        abs(float(genome["inertia_roll_scale"]) - 1.0) / 1.3,
        abs(float(genome["inertia_pitch_scale"]) - 1.0) / 1.3,
        abs(float(genome["inertia_yaw_scale"]) - 1.0) / 1.6,
        abs(float(genome["thrust_tau_s"]) - NOMINAL["t_tau"]) / 0.12,
    )
    wind = math.hypot(float(genome["wind_n"]), float(genome["wind_e"])) / 6.0
    timing = max(
        abs(float(genome["switch_s"]) - 18.0) / 6.0,
        abs(float(genome["setpoint_rate_hz"]) - 100.0) / 80.0,
    )
    setpoint = max(
        float(genome["step_m"]) / 0.5,
        float(genome["sine_amplitude_m"]) / 0.5,
        max(0.0, float(genome["sine_frequency_hz"]) - 4.0) / 4.0,
    )
    return {
        "A_estimator": clamp(estimator, 0.0, 1.5),
        "A_physical": clamp(physical, 0.0, 1.5),
        "A_wind": clamp(wind, 0.0, 1.5),
        "B_timing": clamp(timing, 0.0, 1.5),
        "C_setpoint": clamp(setpoint, 0.0, 1.5),
    }


def feature_bin(genome: dict[str, Any]) -> tuple[str, float, str]:
    severities = genome_severity(genome)
    hint = str(genome.get("family_hint", ""))
    if hint in FAMILIES and severities.get(hint, 0.0) > 0.05:
        family = hint
    else:
        family = max(FAMILIES, key=lambda key: severities[key])
    severity = severities[family]
    if severity < 0.35:
        bucket = "low"
    elif severity < 0.75:
        bucket = "mid"
    else:
        bucket = "high"
    return family, severity, f"{family}:{bucket}"


def theta_from_genome(genome: dict[str, Any], tag: str, seed: int) -> dict[str, Any]:
    params = dict(BASE_PX4_PARAMS)
    params.update({key: round(value, 8) for key, value in physical_params(genome).items()})
    est_params = estimator_params(genome)
    params.update(est_params)
    switch_s = float(genome["switch_s"])
    trajectory_start_s = max(switch_s + 4.0, 22.0)
    mission_end_s = trajectory_start_s + 16.0
    axis = str(genome["setpoint_axis"])
    delta = [0.0, 0.0, 0.0]
    delta[0 if axis == "x" else 1] = round(float(genome["step_m"]), 4)
    theta = {
        "tag": tag,
        "description": "M2 MAP-Elites generated theta; M1 differential runner is the evaluator.",
        "seed": seed,
        "airframe": {
            "sim": "sih",
            "model": "sihsim_x500_v2",
            "sys_autostart": 10046,
        },
        "timing": {
            "controller_switch_s": round(switch_s, 3),
            "trajectory_start_s": round(trajectory_start_s, 3),
            "mission_end_s": round(mission_end_s, 3),
            "mode_command_repeat_s": 0.5,
            "mode_command_timeout_s": 6.0,
        },
        "setpoint": {
            "rate_hz": float(genome["setpoint_rate_hz"]),
            "hover_ned": [0.0, 0.0, -2.5],
            "yaw_rad": 0.0,
            "type": str(genome["setpoint_type"]),
            "step": {
                "delta_ned": delta,
            },
            "sine": {
                "axis": axis,
                "amplitude_m": round(float(genome["sine_amplitude_m"]), 4),
                "frequency_hz": round(float(genome["sine_frequency_hz"]), 4),
            },
        },
        "boot_px4_params": est_params,
        "px4_params": params,
        "environment": {
            "sih_wind_n": round(float(genome["wind_n"]), 4),
            "sih_wind_e": round(float(genome["wind_e"]), 4),
            "mass_scale": round(float(genome["mass_scale"]), 4),
            "inertia_roll_scale": round(float(genome["inertia_roll_scale"]), 4),
            "inertia_pitch_scale": round(float(genome["inertia_pitch_scale"]), 4),
            "inertia_yaw_scale": round(float(genome["inertia_yaw_scale"]), 4),
            "thrust_scale_effective": round(params["SIH_T_MAX"] / NOMINAL["t_max"], 4),
            "torque_scale": round(float(genome["torque_scale"]), 4),
            "thrust_tau_s": round(float(genome["thrust_tau_s"]), 4),
            "estimator_pollution": {
                "sih_ok": True,
                "shared_estimate": True,
                "gps_delay_ms": int(round(float(genome["gps_delay_ms"]))),
                "gps_position_noise_m": round(float(genome["gps_position_noise_m"]), 4),
                "gps_velocity_noise_m_s": round(float(genome["gps_velocity_noise_m_s"]), 4),
                "gps_position_gate_sd": round(float(genome["gps_position_gate_sd"]), 4),
                "gps_velocity_gate_sd": round(float(genome["gps_velocity_gate_sd"]), 4),
                "ekf_tau_vel_s": round(float(genome["ekf_tau_vel_s"]), 4),
                "ekf_tau_pos_s": round(float(genome["ekf_tau_pos_s"]), 4),
                "imu_pos_m": [
                    round(float(genome["imu_pos_x_m"]), 4),
                    round(float(genome["imu_pos_y_m"]), 4),
                    round(float(genome["imu_pos_z_m"]), 4),
                ],
                "px4_params": est_params,
            },
        },
        "faults": [],
        "sensor_perturbations": [
            {
                "type": "shared_ekf_estimate_pollution",
                "simulator": "sih",
                "mechanism": "PX4 EKF/GNSS delay-noise-gate-tau-imu-position parameters",
                "params": est_params,
            }
        ],
        "divergence_thresholds": {
            "position_divergence_m": 1.0,
        },
        "m2": {
            "generator": "scripts/m2_map_elites.py",
            "genome": genome,
            "feature_family": feature_bin(genome)[0],
            "feature_severity": feature_bin(genome)[1],
            "feature_bin": feature_bin(genome)[2],
            "safety_config": str(SAFETY_CONFIG.relative_to(REPO_ROOT)),
        },
    }
    return theta


def evaluate_theta(
    theta: dict[str, Any],
    theta_path: Path,
    docs_dir: Path,
    index: int,
    run_timeout_s: int,
    eval_timeout_s: int,
    env: dict[str, str],
) -> EvalResult:
    write_json(theta_path, theta)
    tag = str(theta["tag"])
    log_path = docs_dir / "m2_eval.log"
    docs_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/m1_diff_runner.py"),
        "--theta",
        str(theta_path),
        "--skip-build",
        "--run-timeout",
        str(run_timeout_s),
        "--docs-dir",
        str(docs_dir),
        "--safety-config",
        str(SAFETY_CONFIG),
    ]
    start = time.monotonic()
    returncode = 1
    error: str | None = None
    with log_path.open("w", encoding="utf-8") as log_handle:
        log_handle.write("$ " + " ".join(cmd) + "\n")
        log_handle.flush()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(REPO_ROOT),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                timeout=eval_timeout_s,
                check=False,
            )
            returncode = int(proc.returncode)
        except subprocess.TimeoutExpired as exc:
            error = f"eval_timeout_after_{eval_timeout_s}s"
            returncode = 124
            log_handle.write(f"\nERROR: {error}: {exc}\n")
    elapsed = time.monotonic() - start
    compare_path = docs_dir / f"m1_diff_{tag}.json"
    genome = theta.get("m2", {}).get("genome", {})
    family, severity, bin_name = feature_bin(genome) if isinstance(genome, dict) else ("unknown", 0.0, "unknown")
    if returncode != 0 or not compare_path.exists():
        return EvalResult(
            index=index,
            tag=tag,
            theta_path=str(theta_path),
            docs_dir=str(docs_dir),
            returncode=returncode,
            elapsed_wall_s=elapsed,
            compare_path=str(compare_path) if compare_path.exists() else None,
            quadrant=None,
            primary_bug=False,
            classical_usable=False,
            classical_safe=None,
            raptor_safe=None,
            infrastructure_limited=None,
            quality=0.0,
            feature_bin=bin_name,
            severity=severity,
            error=error or f"runner_returncode_{returncode}",
        )
    compare = load_json(compare_path)
    classical = compare.get("classical", {})
    raptor = compare.get("raptor", {})
    quality = float(compare.get("divergence", {}).get("quality") or 0.0)
    classical_usable = bool(compare.get("classical_usable_for_primary"))
    primary_bug = bool(compare.get("primary_bug")) and classical_usable and quality > 0.0
    return EvalResult(
        index=index,
        tag=tag,
        theta_path=str(theta_path),
        docs_dir=str(docs_dir),
        returncode=returncode,
        elapsed_wall_s=elapsed,
        compare_path=str(compare_path),
        quadrant=compare.get("quadrant"),
        primary_bug=primary_bug,
        classical_usable=classical_usable,
        classical_safe=bool(classical.get("safe")),
        raptor_safe=bool(raptor.get("safe")),
        infrastructure_limited=bool(classical.get("infrastructure_limited")),
        quality=quality,
        feature_bin=bin_name,
        severity=severity,
        error=None,
    )


def select_parent(archive: dict[str, dict[str, Any]], rng: random.Random) -> dict[str, Any] | None:
    if not archive:
        return None
    elites = sorted(archive.values(), key=lambda item: float(item["result"]["quality"]), reverse=True)
    pool = elites[: max(1, min(8, len(elites)))]
    return dict(rng.choice(pool)["genome"])


def write_archive(path: Path, archive: dict[str, dict[str, Any]]) -> None:
    serializable = {
        key: {
            "genome": value["genome"],
            "theta_path": value["theta_path"],
            "compare_path": value["compare_path"],
            "result": value["result"],
        }
        for key, value in sorted(archive.items())
    }
    write_json(path, serializable)


def search(args: argparse.Namespace) -> tuple[Path, list[EvalResult], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rng = random.Random(args.seed)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("m2_%Y%m%dT%H%M%SZ")
    run_dir = (REPO_ROOT / "docs" / run_id).resolve()
    theta_dir = run_dir / "theta"
    evals_dir = run_dir / "evals"
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "budget": args.budget,
        "run_timeout_s": args.run_timeout,
        "eval_timeout_s": args.eval_timeout,
        "safety_config": str(SAFETY_CONFIG.relative_to(REPO_ROOT)),
        "px4_commit": "3042f906abaab7ab59ae838ad5a530a9ef3df9a6",
        "searcher": "MAP-Elites",
        "bins": "dominant disturbance family x severity bucket",
        "scope_note": "MAP-Elites random initialization is algorithm bootstrap, not an M3 random baseline.",
    }
    write_json(run_dir / "metadata.json", metadata)

    env = dict(**os_environ_with_speed(args.sim_speed_factor))
    archive: dict[str, dict[str, Any]] = {}
    results: list[EvalResult] = []
    primary_candidates: list[dict[str, Any]] = []
    deadline = time.monotonic() + args.max_wall_clock_s if args.max_wall_clock_s else None

    for index in range(args.budget):
        if deadline is not None and time.monotonic() >= deadline:
            break
        fixed_seeds = seed_bank()
        parent = select_parent(archive, rng)
        if index < len(fixed_seeds):
            genome = fixed_seeds[index]
        elif parent is None or index < args.bootstrap:
            genome = random_genome(rng)
        else:
            genome = mutate_genome(parent, rng)
        tag = f"{run_id}_e{index:04d}"
        theta = theta_from_genome(genome, tag, args.seed + index)
        theta_path = theta_dir / f"{tag}.json"
        docs_dir = evals_dir / tag
        result = evaluate_theta(theta, theta_path, docs_dir, index, args.run_timeout, args.eval_timeout, env)
        results.append(result)
        append_jsonl(run_dir / "evals.jsonl", result.as_dict())

        bin_name = result.feature_bin
        if result.classical_usable and (bin_name not in archive or result.quality > archive[bin_name]["result"]["quality"]):
            archive[bin_name] = {
                "genome": genome,
                "theta_path": str(theta_path),
                "compare_path": result.compare_path,
                "result": result.as_dict(),
            }
            write_archive(run_dir / "archive.json", archive)

        if result.primary_bug:
            candidate = {
                "genome": genome,
                "theta_path": str(theta_path),
                "compare_path": result.compare_path,
                "result": result.as_dict(),
            }
            primary_candidates.append(candidate)
            write_json(run_dir / "primary_candidates.json", primary_candidates)

        print(
            json.dumps(
                {
                    "eval": index,
                    "tag": tag,
                    "bin": bin_name,
                    "quality": result.quality,
                    "quadrant": result.quadrant,
                    "primary_bug": result.primary_bug,
                    "classical_usable": result.classical_usable,
                    "error": result.error,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    write_archive(run_dir / "archive.json", archive)
    write_json(run_dir / "primary_candidates.json", primary_candidates)
    return run_dir, results, primary_candidates, archive


def os_environ_with_speed(sim_speed_factor: float) -> dict[str, str]:
    import os

    env = os.environ.copy()
    env["PX4_SIM_SPEED_FACTOR"] = str(sim_speed_factor)
    return env


def confirm_candidates(
    run_dir: Path,
    candidates: list[dict[str, Any]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    env = os_environ_with_speed(args.sim_speed_factor)
    confirmed: list[dict[str, Any]] = []
    selected = sorted(candidates, key=lambda item: float(item["result"]["quality"]), reverse=True)[
        : args.max_confirm_candidates
    ]
    for cidx, candidate in enumerate(selected):
        theta = load_json(Path(candidate["theta_path"]))
        repeats: list[dict[str, Any]] = []
        all_passed = True
        for ridx in range(args.confirm_repeats):
            seed = CONFIRM_SEEDS[ridx % len(CONFIRM_SEEDS)] + cidx * 100
            confirm_theta = json.loads(json.dumps(theta))
            original_tag = str(theta["tag"])
            confirm_tag = f"{original_tag}_confirm_s{seed}"
            confirm_theta["tag"] = confirm_tag
            confirm_theta["seed"] = seed
            confirm_theta.setdefault("m2", {})["confirmation_of"] = original_tag
            confirm_theta.setdefault("m2", {})["confirmation_seed"] = seed
            theta_path = run_dir / "confirm" / "theta" / f"{confirm_tag}.json"
            docs_dir = run_dir / "confirm" / "evals" / confirm_tag
            result = evaluate_theta(
                confirm_theta,
                theta_path,
                docs_dir,
                100000 + cidx * 100 + ridx,
                args.run_timeout,
                args.eval_timeout,
                env,
            )
            repeats.append(result.as_dict())
            if not result.primary_bug:
                all_passed = False
        record = {
            "candidate": candidate,
            "passed": all_passed,
            "repeats": repeats,
        }
        if all_passed:
            confirmed.append(record)
            primary_dir = REPO_ROOT / "config" / "m2_primary_bugs"
            primary_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate["theta_path"], primary_dir / Path(candidate["theta_path"]).name)
        append_jsonl(run_dir / "confirmations.jsonl", record)
        write_json(run_dir / "confirmed_primary_bugs.json", confirmed)
    write_json(run_dir / "confirmed_primary_bugs.json", confirmed)
    return confirmed


def write_summary(
    run_dir: Path,
    results: list[EvalResult],
    archive: dict[str, dict[str, Any]],
    candidates: list[dict[str, Any]],
    confirmed: list[dict[str, Any]],
) -> None:
    total = len(results)
    errors = sum(1 for result in results if result.error)
    usable = sum(1 for result in results if result.classical_usable)
    primary = sum(1 for result in results if result.primary_bug)
    lines = [
        "# M2 MAP-Elites run summary",
        "",
        f"run_dir: `{run_dir.relative_to(REPO_ROOT)}`",
        f"evals: {total}",
        f"runner_errors: {errors}",
        f"classical_usable: {usable}",
        f"archive_bins: {len(archive)}",
        f"primary_candidates: {primary}",
        f"confirmed_primary_bugs: {len(confirmed)}",
        "",
        "## best elites",
    ]
    for key, elite in sorted(archive.items(), key=lambda item: float(item[1]["result"]["quality"]), reverse=True)[:10]:
        result = elite["result"]
        lines.append(
            f"- {key}: quality={result['quality']:.6g} quadrant={result['quadrant']} "
            f"theta=`{Path(elite['theta_path']).relative_to(REPO_ROOT)}`"
        )
    lines.extend(["", "## primary candidates"])
    if not candidates:
        lines.append("- none")
    for candidate in candidates:
        result = candidate["result"]
        lines.append(
            f"- {result['tag']}: quality={result['quality']:.6g} "
            f"theta=`{Path(candidate['theta_path']).relative_to(REPO_ROOT)}` "
            f"compare=`{Path(candidate['compare_path']).relative_to(REPO_ROOT) if candidate.get('compare_path') else None}`"
        )
    lines.extend(["", "## confirmed"])
    if not confirmed:
        lines.append("- none")
    for item in confirmed:
        result = item["candidate"]["result"]
        lines.append(f"- {result['tag']}: {len(item['repeats'])} repeats passed")
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=int, default=18)
    parser.add_argument("--bootstrap", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260624)
    parser.add_argument("--run-id")
    parser.add_argument("--run-timeout", type=int, default=130)
    parser.add_argument("--eval-timeout", type=int, default=260)
    parser.add_argument("--max-wall-clock-s", type=float, default=0.0)
    parser.add_argument("--sim-speed-factor", type=float, default=1.0)
    parser.add_argument("--confirm-repeats", type=int, default=3)
    parser.add_argument("--max-confirm-candidates", type=int, default=3)
    parser.add_argument("--no-confirm", action="store_true")
    args = parser.parse_args()

    run_dir, results, candidates, archive = search(args)
    confirmed: list[dict[str, Any]] = []
    if candidates and not args.no_confirm and args.confirm_repeats > 0:
        confirmed = confirm_candidates(run_dir, candidates, args)
    write_summary(run_dir, results, archive, candidates, confirmed)
    print(f"M2_RUN_DIR={run_dir}")
    print(f"M2_SUMMARY={run_dir / 'summary.md'}")
    print(f"M2_CONFIRMED_PRIMARY={len(confirmed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
