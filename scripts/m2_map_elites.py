#!/usr/bin/env python3
"""Tier 0.5 MAP-Elites search wired to differential property fitness.

Each real evaluation runs the same theta with the classical controller and
mc_nn mode 23, computes property-oracle rho_i on both ULOGs, then archives by
max valid classical-minus-neural property gap.
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

import m1_diff_runner as m1
import mcnn_gate3_position_error_probe as mcnn_runner
import theta_genome
from m1_compare import property_only_result
from property_fitness import (
    FITNESS_FLOOR,
    differential_property_fitness,
    driver_target_properties,
    normalize_target_properties,
)
from property_oracle import evaluate_ulog, load_thresholds
from validity_automation import decontamination_gate, reproduction_margins


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
TARGET_PRESETS: dict[str, list[str] | None] = {
    "auto": None,
    "behavior": ["P4", "P6", "P7"],
    "behavior-step": ["P4", "P5", "P6", "P7"],
    "route-a-catastrophic": ["P1", "P2"],
    "validation": ["P1", "P2", "P4", "P5", "P6", "P7"],
}
SUBSPACES = ["full", "route-a-switching", "steady-wind-physics"]
STRATEGIES = ["map-elites", "random"]


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
    fitness: dict[str, Any]
    feature_bin: str
    severity: float
    selected_parent_tag: str | None = None
    selected_parent_quality: float | None = None
    mcnn_confirmed: bool | None = None
    error: str | None = None
    seed: int | None = None
    evidence: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "tag": self.tag,
            "seed": self.seed,
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
            "fitness": self.fitness,
            "feature_bin": self.feature_bin,
            "severity": self.severity,
            "selected_parent_tag": self.selected_parent_tag,
            "selected_parent_quality": self.selected_parent_quality,
            "mcnn_confirmed": self.mcnn_confirmed,
            "error": self.error,
            "evidence": self.evidence or {},
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


def parse_target_properties(value: str | None) -> list[str] | None:
    if value is None:
        return None
    value = value.strip()
    if value == "" or value == "auto":
        return None
    if value in TARGET_PRESETS:
        preset = TARGET_PRESETS[value]
        return None if preset is None else normalize_target_properties(preset)
    return normalize_target_properties(item.strip() for item in value.split(",") if item.strip())


def target_properties_for_theta(theta: dict[str, Any], override: list[str] | None) -> list[str]:
    return list(override) if override is not None else driver_target_properties(theta)


def route_a_switching_genome(rng: random.Random) -> dict[str, Any]:
    genome = theta_genome.default_genome("switching")
    genome.update(
        {
            "approach_radius_m": 2.30,
            "approach_frequency_hz": 0.33,
            "approach_phase_rad": 0.0,
            "wind_speed_m_s": 6.0,
            "wind_direction_rad": 0.0,
            "setpoint_rate_hz": 80.0,
            "switch_roll_pitch_deg": rng.uniform(38.0, 46.0),
            "switch_rate_rad_s": rng.uniform(1.10, 1.80),
            "switch_delay_s": rng.uniform(0.0, 0.18),
        }
    )
    return theta_genome.normalize_genome(genome)


def mutate_route_a_switching_genome(parent: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    if parent.get("disturbance_type") != "switching" or rng.random() < 0.10:
        return route_a_switching_genome(rng)
    genome = dict(parent)
    genome.update(
        {
            "disturbance_type": "switching",
            "approach_radius_m": 2.30,
            "approach_frequency_hz": 0.33,
            "approach_phase_rad": 0.0,
            "wind_speed_m_s": 6.0,
            "wind_direction_rad": 0.0,
            "setpoint_rate_hz": 80.0,
            "switch_roll_pitch_deg": float(genome["switch_roll_pitch_deg"]) + rng.gauss(0.0, 2.6),
            "switch_rate_rad_s": float(genome["switch_rate_rad_s"]) + rng.gauss(0.0, 0.22),
            "switch_delay_s": float(genome["switch_delay_s"]) + rng.gauss(0.0, 0.055),
        }
    )
    return project_genome_to_subspace(genome, "route-a-switching", rng)


def steady_wind_physics_genome(rng: random.Random, kind: str | None = None) -> dict[str, Any]:
    del kind
    genome = theta_genome.default_genome(theta_genome.COMBINED_STEADY_DISTURBANCE_TYPE)
    genome.update({"mission_end_s": 54.0, "setpoint_rate_hz": rng.choice(theta_genome.SETPOINT_RATES_HZ)})
    genome["wind_speed_m_s"] = rng.uniform(0.5, 8.0)
    genome["wind_direction_rad"] = rng.uniform(0.0, 2.0 * math.pi)
    genome["mass_scale"] = rng.uniform(0.88, 1.25)
    genome["inertia_roll_scale"] = rng.uniform(0.75, 1.60)
    genome["inertia_pitch_scale"] = rng.uniform(0.75, 1.60)
    genome["inertia_yaw_scale"] = rng.uniform(0.75, 1.80)
    genome["twr_scale"] = rng.uniform(0.92, 1.13)
    return theta_genome.normalize_genome(genome)


def mutate_steady_wind_physics_genome(parent: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    if parent.get("disturbance_type") != theta_genome.COMBINED_STEADY_DISTURBANCE_TYPE or rng.random() < 0.10:
        return steady_wind_physics_genome(rng)
    genome = dict(parent)
    genome["disturbance_type"] = theta_genome.COMBINED_STEADY_DISTURBANCE_TYPE
    genome["mission_end_s"] = 54.0
    if rng.random() < 0.10:
        genome["setpoint_rate_hz"] = rng.choice(theta_genome.SETPOINT_RATES_HZ)
    for key, sigma in [
        ("wind_speed_m_s", 1.1),
        ("wind_direction_rad", 0.55),
        ("mass_scale", 0.05),
        ("inertia_roll_scale", 0.12),
        ("inertia_pitch_scale", 0.12),
        ("inertia_yaw_scale", 0.14),
        ("twr_scale", 0.035),
    ]:
        if rng.random() < 0.45:
            genome[key] = float(genome[key]) + rng.gauss(0.0, sigma)
    return project_genome_to_subspace(genome, "steady-wind-physics", rng)


def ensure_steady_combo_stress(genome: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    out = dict(genome)
    if float(out.get("wind_speed_m_s", 0.0)) < 0.5:
        out["wind_speed_m_s"] = rng.uniform(0.5, 8.0)
        out["wind_direction_rad"] = rng.uniform(0.0, 2.0 * math.pi)
    if theta_genome.genome_severity(out)["physics_mismatch"] < 0.05:
        out["mass_scale"] = rng.uniform(0.88, 1.25)
        out["inertia_roll_scale"] = rng.uniform(0.75, 1.60)
        out["inertia_pitch_scale"] = rng.uniform(0.75, 1.60)
        out["inertia_yaw_scale"] = rng.uniform(0.75, 1.80)
        out["twr_scale"] = rng.uniform(0.92, 1.13)
    return out


def project_genome_to_subspace(genome: dict[str, Any], subspace: str, rng: random.Random) -> dict[str, Any]:
    if subspace == "full":
        return theta_genome.normalize_genome(genome)
    if subspace == "route-a-switching":
        projected = dict(genome)
        projected.update(
            {
                "disturbance_type": "switching",
                "approach_radius_m": 2.30,
                "approach_frequency_hz": 0.33,
                "approach_phase_rad": 0.0,
                "wind_speed_m_s": 6.0,
                "wind_direction_rad": 0.0,
                "setpoint_rate_hz": 80.0,
            }
        )
        projected["switch_roll_pitch_deg"] = clamp(float(projected["switch_roll_pitch_deg"]), 38.0, 46.0)
        projected["switch_rate_rad_s"] = clamp(float(projected["switch_rate_rad_s"]), 1.10, 1.80)
        projected["switch_delay_s"] = clamp(float(projected["switch_delay_s"]), 0.0, 0.18)
        return theta_genome.normalize_genome(projected)
    if subspace == "steady-wind-physics":
        projected = dict(genome)
        projected.update(
            {
                "disturbance_type": theta_genome.COMBINED_STEADY_DISTURBANCE_TYPE,
                "mission_end_s": 54.0,
                "approach_radius_m": 3.0,
                "approach_frequency_hz": 0.35,
                "approach_phase_rad": 0.0,
                "switch_roll_pitch_deg": 35.0,
                "switch_rate_rad_s": 1.3,
                "switch_delay_s": 0.0,
                "step_magnitude_m": 0.75,
                "step_axis": "x",
                "step_sign": 1,
                "step_time_s": 32.0,
            }
        )
        projected = ensure_steady_combo_stress(projected, rng)
        return theta_genome.normalize_genome(projected)
    raise ValueError(f"unknown subspace {subspace!r}; expected one of {SUBSPACES}")


def random_candidate_genome(subspace: str, rng: random.Random) -> dict[str, Any]:
    if subspace == "route-a-switching":
        return route_a_switching_genome(rng)
    if subspace == "steady-wind-physics":
        return steady_wind_physics_genome(rng)
    return theta_genome.random_genome(rng)


def mutate_candidate_genome(parent: dict[str, Any], subspace: str, rng: random.Random) -> dict[str, Any]:
    if subspace == "route-a-switching":
        return mutate_route_a_switching_genome(parent, rng)
    if subspace == "steady-wind-physics":
        return mutate_steady_wind_physics_genome(parent, rng)
    return theta_genome.mutate_genome(parent, rng)


def crossover_candidate_genome(
    a: dict[str, Any],
    b: dict[str, Any],
    subspace: str,
    rng: random.Random,
) -> dict[str, Any]:
    genome = theta_genome.crossover_genome(a, b, rng)
    return project_genome_to_subspace(genome, subspace, rng)


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


def theta_genome_bin(genome: dict[str, Any]) -> tuple[str, float, str]:
    kind, bucket, severity = theta_genome.feature_bin(genome)
    return kind, float(severity), f"{kind}:{bucket}"


def empty_fitness(targets: list[str] | None = None) -> dict[str, Any]:
    return {
        "fitness": FITNESS_FLOOR,
        "fitness_floor": FITNESS_FLOOR,
        "target_properties": targets or [],
        "best_property": None,
        "valid_property_count": 0,
        "candidate_differential_properties": [],
        "strict_differential_properties": [],
        "clean_differential_properties": [],
        "relative_degradation_differential_properties": [],
        "strict_differential_finding": False,
        "relative_degradation_finding": False,
        "property_finding": False,
        "per_property": {},
    }


def target_properties_from_lists(fitness: dict[str, Any], keys: list[str]) -> set[str]:
    props: set[str] = set()
    for key in keys:
        values = fitness.get(key)
        if isinstance(values, list):
            props.update(str(prop) for prop in values)
    targets = fitness.get("target_properties")
    if isinstance(targets, list) and targets:
        props.intersection_update(str(prop) for prop in targets)
    return props


def target_finding_properties(fitness: dict[str, Any]) -> set[str]:
    return target_properties_from_lists(
        fitness,
        [
            "strict_differential_properties",
            "clean_differential_properties",
            "relative_degradation_differential_properties",
        ],
    )


def target_strict_differential_properties(fitness: dict[str, Any]) -> set[str]:
    return target_properties_from_lists(fitness, ["strict_differential_properties", "clean_differential_properties"])


def target_relative_degradation_properties(fitness: dict[str, Any]) -> set[str]:
    return target_properties_from_lists(fitness, ["relative_degradation_differential_properties"])


def mock_property_pair(
    theta: dict[str, Any],
    genome: dict[str, Any],
    target_properties: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    targets = target_properties_for_theta(theta, target_properties)
    kind, _, severity = theta_genome.feature_bin(genome)
    prop_by_kind = {
        "wind": "P6",
        "physics_mismatch": "P7",
        theta_genome.COMBINED_STEADY_DISTURBANCE_TYPE: "P7",
        "switching": "P4",
        "step": "P5",
    }
    target_candidates = [prop for prop in targets if prop in {"P1", "P2", "P4", "P5", "P6", "P7"}]
    if kind == "switching" and any(prop in targets for prop in ["P1", "P2"]):
        affected = ["P1", "P2"]
    elif kind == theta_genome.COMBINED_STEADY_DISTURBANCE_TYPE:
        affected = [prop for prop in ["P6", "P7"] if prop in targets] or ["P7"]
    else:
        affected = [prop_by_kind.get(kind, target_candidates[0] if target_candidates else "P4")]
    base_rho = {
        "P1": 1.5,
        "P2": 6.0,
        "P3": 0.5,
        "P4": 0.7,
        "P5": 0.4,
        "P6": 0.25,
        "P7": 0.4,
    }
    neural_rho = dict(base_rho)
    for prop in affected:
        if prop == "P1":
            neural_rho[prop] = base_rho[prop] - (0.55 + 2.2 * float(severity))
        elif prop == "P2":
            neural_rho[prop] = base_rho[prop] - (2.0 + 7.0 * float(severity))
        else:
            neural_rho[prop] = base_rho[prop] - (0.15 + 1.25 * float(severity))
            if float(severity) > 0.72:
                neural_rho[prop] = -0.15 - float(severity)
    details = {prop: {"vacuous": False} for prop in base_rho}
    if "P5" not in targets:
        details["P5"] = {"vacuous": True}
    nsev = 0
    if neural_rho.get("P1", 1.0) <= 0.0 or neural_rho.get("P2", 1.0) <= 0.0:
        nsev = 3
    elif neural_rho.get("P5", 1.0) <= 0.0:
        nsev = 2
    elif any(neural_rho.get(prop, 1.0) <= 0.0 for prop in ["P4", "P6", "P7"]):
        nsev = 1
    labels = {
        0: "S0_clean_recovery",
        1: "S1_controlled_degraded_survival",
        2: "S2_controlled_safe_failure",
        3: "S3_uncontrolled_tumble_or_spin",
    }
    classical_property = {
        "tag": theta.get("tag"),
        "controller": "classical",
        "rho": base_rho,
        "details": details,
        "severity": {"severity": 0, "label": labels[0], "reasons": []},
        "window": {"terminal": {"terminal_class": "NONE"}},
        "controller_identity": {"controller": "classical", "raptor_input_present": False},
    }
    neural_property = {
        "tag": theta.get("tag"),
        "controller": "mcnn",
        "rho": neural_rho,
        "details": details,
        "severity": {"severity": nsev, "label": labels[nsev], "reasons": []},
        "window": {"terminal": {"terminal_class": "NONE"}},
        "controller_identity": {
            "controller": "mcnn",
            "mcnn_confirmed": True,
            "neural_control_rate_hz": 228.0,
            "raptor_input_present": False,
        },
    }
    return classical_property, neural_property


def evaluate_theta(
    theta: dict[str, Any],
    theta_path: Path,
    docs_dir: Path,
    index: int,
    run_timeout_s: int,
    env: dict[str, str],
    thresholds: dict[str, float],
    selected_parent_tag: str | None = None,
    selected_parent_quality: float | None = None,
    mock_evaluator: bool = False,
    target_properties: list[str] | None = None,
) -> EvalResult:
    write_json(theta_path, theta)
    tag = str(theta["tag"])
    docs_dir.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    returncode = 1
    error: str | None = None
    genome = theta.get("theta_genome", {}).get("genome")
    if isinstance(genome, dict):
        _, severity, bin_name = theta_genome_bin(genome)
    else:
        severity, bin_name = 0.0, "unknown"
    target_properties = target_properties_for_theta(theta, target_properties)
    compare_path = docs_dir / f"m1_diff_{tag}.json"
    seed = int(theta["seed"]) if isinstance(theta.get("seed"), int) else None
    evidence: dict[str, Any] = {
        "tag": tag,
        "seed": seed,
        "theta_path": str(theta_path),
        "docs_dir": str(docs_dir),
        "ulog_paths": {},
        "task_paths": {},
        "property_paths": {},
        "compare_path": str(compare_path),
        "validity": {},
    }
    fitness = empty_fitness(target_properties)
    classical_property: dict[str, Any] = {}
    mcnn_property: dict[str, Any] = {}
    mcnn_confirmed: bool | None = None

    try:
        if mock_evaluator:
            if not isinstance(genome, dict):
                raise ValueError("mock evaluator requires theta_genome.genome")
            classical_property, mcnn_property = mock_property_pair(theta, genome, target_properties)
        else:
            outputs: dict[str, dict[str, Path]] = {}
            for controller in ["classical", "mcnn"]:
                outputs[controller] = mcnn_runner.run_one(
                    REPO_ROOT,
                    theta_path,
                    theta,
                    controller,
                    docs_dir,
                    env,
                    run_timeout_s,
                    SAFETY_CONFIG,
                )
            evidence["ulog_paths"] = {controller: str(paths["ulog"]) for controller, paths in outputs.items()}
            evidence["task_paths"] = {controller: str(paths["task"]) for controller, paths in outputs.items()}
            classical_property = evaluate_ulog(
                outputs["classical"]["ulog"],
                controller="classical",
                theta=theta,
                task=load_json(outputs["classical"]["task"]),
                thresholds=thresholds,
            )
            mcnn_property = evaluate_ulog(
                outputs["mcnn"]["ulog"],
                controller="mcnn",
                theta=theta,
                task=load_json(outputs["mcnn"]["task"]),
                thresholds=thresholds,
            )
        classical_property_path = docs_dir / f"{tag}_classical_property.json"
        mcnn_property_path = docs_dir / f"{tag}_mcnn_property.json"
        write_json(classical_property_path, classical_property)
        write_json(mcnn_property_path, mcnn_property)
        evidence["property_paths"] = {
            "classical": str(classical_property_path),
            "mcnn": str(mcnn_property_path),
        }

        if mock_evaluator:
            decontam_gates = {
                "classical": {"passed": True, "reasons": [], "mock_evaluator": True},
                "mcnn": {"passed": True, "reasons": [], "mock_evaluator": True},
            }
        else:
            decontam_gates = {
                "classical": decontamination_gate(
                    classical_property.get("window", {}).get("decontamination", {})
                ),
                "mcnn": decontamination_gate(mcnn_property.get("window", {}).get("decontamination", {})),
            }
        mcnn_identity = mcnn_property.get("controller_identity", {})
        identity_gate = (
            {"passed": True, "reasons": [], "mock_evaluator": True}
            if mock_evaluator
            else mcnn_identity.get("identity_gate", {"passed": False, "reasons": ["missing_identity_gate"]})
        )
        mcnn_confirmed = bool(identity_gate.get("passed"))
        evidence["validity"] = {
            "decontamination": decontam_gates,
            "mcnn_identity": identity_gate,
            "rho_jitter_reproduction_margins": reproduction_margins(),
        }
        write_json(docs_dir / f"{tag}_validity.json", evidence["validity"])

        gate_failures: list[str] = []
        if not mock_evaluator:
            for controller, gate in decontam_gates.items():
                if not bool(gate.get("passed")):
                    gate_failures.append(f"{controller}_decontamination:{','.join(gate.get('reasons', []))}")
            if not bool(identity_gate.get("passed")):
                gate_failures.append(f"mcnn_identity:{','.join(identity_gate.get('reasons', []))}")

        if gate_failures:
            error = "validity_gate_failed: " + ";".join(gate_failures)
            returncode = 2
        else:
            fitness = differential_property_fitness(
                classical_property,
                mcnn_property,
                target_properties=target_properties,
            )
            comparison = property_only_result(theta, classical_property, mcnn_property)
            comparison["property_oracle"]["fitness"] = fitness
            write_json(compare_path, comparison)
            returncode = 0
    except Exception as exc:  # fail loud into the eval record, keep the campaign alive
        error = f"{type(exc).__name__}: {exc}"
        returncode = 1
        fitness = empty_fitness(target_properties)
        mcnn_confirmed = None
    elapsed = time.monotonic() - start
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
            quality=FITNESS_FLOOR,
            fitness=fitness,
            feature_bin=bin_name,
            severity=severity,
            selected_parent_tag=selected_parent_tag,
            selected_parent_quality=selected_parent_quality,
            mcnn_confirmed=mcnn_confirmed,
            error=error or f"runner_returncode_{returncode}",
            seed=seed,
            evidence=evidence,
        )
    quality = float(fitness["fitness"])
    csev = fitness.get("classical_severity")
    nsev = fitness.get("neural_severity")
    classical_usable = bool(fitness.get("valid_property_count", 0) > 0)
    primary_bug = bool(target_strict_differential_properties(fitness))
    relative_degradation = bool(target_relative_degradation_properties(fitness))
    terminal = classical_property.get("window", {}).get("terminal", {}) if isinstance(classical_property, dict) else {}
    return EvalResult(
        index=index,
        tag=tag,
        theta_path=str(theta_path),
        docs_dir=str(docs_dir),
        returncode=returncode,
        elapsed_wall_s=elapsed,
        compare_path=str(compare_path),
        quadrant=(
            "strict_differential"
            if primary_bug
            else "relative_degradation_differential"
            if relative_degradation
            else "property_gradient"
        ),
        primary_bug=primary_bug,
        classical_usable=classical_usable,
        classical_safe=bool(csev is not None and int(csev) <= 2),
        raptor_safe=bool(nsev is not None and int(nsev) <= 2),
        infrastructure_limited=terminal.get("terminal_class") == "INFRASTRUCTURE",
        quality=quality,
        fitness=fitness,
        feature_bin=bin_name,
        severity=severity,
        selected_parent_tag=selected_parent_tag,
        selected_parent_quality=selected_parent_quality,
        mcnn_confirmed=mcnn_confirmed,
        error=None,
        seed=seed,
        evidence=evidence,
    )


def select_parent(archive: dict[str, dict[str, Any]], rng: random.Random) -> dict[str, Any] | None:
    if not archive:
        return None
    elites = sorted(archive.values(), key=lambda item: float(item["result"]["quality"]), reverse=True)
    pool = elites[: max(1, min(8, len(elites)))]
    return dict(rng.choice(pool))


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


def qd_score(archive: dict[str, dict[str, Any]]) -> float:
    return float(sum(max(0.0, float(value["result"]["quality"])) for value in archive.values()))


def best_result(results: list[EvalResult]) -> EvalResult | None:
    if not results:
        return None
    return max(results, key=lambda result: float(result.quality))


def append_progress(
    path: Path,
    result: EvalResult,
    results: list[EvalResult],
    archive: dict[str, dict[str, Any]],
    selection_source: str,
) -> dict[str, Any]:
    best = best_result(results)
    archive_best = None
    if archive:
        archive_best = max(archive.values(), key=lambda item: float(item["result"]["quality"]))["result"]
    record = {
        "eval": result.index,
        "tag": result.tag,
        "seed": result.seed,
        "selection_source": selection_source,
        "selected_parent_tag": result.selected_parent_tag,
        "selected_parent_quality": result.selected_parent_quality,
        "quality": result.quality,
        "best_so_far_tag": best.tag if best else None,
        "best_so_far_quality": best.quality if best else FITNESS_FLOOR,
        "archive_bins": len(archive),
        "archive_best_tag": archive_best.get("tag") if archive_best else None,
        "archive_best_quality": archive_best.get("quality") if archive_best else FITNESS_FLOOR,
        "qd_score": qd_score(archive),
        "feature_bin": result.feature_bin,
        "best_property": result.fitness.get("best_property"),
        "primary_bug": result.primary_bug,
        "error": result.error,
        "theta_ulog_map": {
            "theta_path": result.theta_path,
            "seed": result.seed,
            "ulog_paths": (result.evidence or {}).get("ulog_paths", {}),
        },
    }
    append_jsonl(path, record)
    return record


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
        "strategy": args.strategy,
        "subspace": args.subspace,
        "safety_config": str(SAFETY_CONFIG.relative_to(REPO_ROOT)),
        "px4_commit": "3042f906abaab7ab59ae838ad5a530a9ef3df9a6",
        "searcher": "MAP-Elites" if args.strategy == "map-elites" else "random baseline",
        "genome": "scripts/theta_genome.py shim-free Tier 0.5 genome",
        "bins": (
            "steady-wind-physics uses steady_combo wind_bucket x physics_bucket; "
            "other subspaces use disturbance_type x amplitude_bucket"
        ),
        "fitness": (
            "differential property gap: max_i rho_i(classical)-rho_i(mcnn) with per-property classical margin; "
            "strict findings require neural rho beyond per-property rho jitter reproduction margin; "
            "relative-degradation findings require both controllers controlled and gap beyond the same margin"
        ),
        "target_property_override": args.target_properties,
        "resolved_target_properties": args.resolved_target_properties,
        "driver_target_properties": {
            "default": ["P4", "P6", "P7"],
            "step_theta": ["P4", "P5", "P6", "P7"],
            "excluded_from_driver": ["P1", "P2", "P3"],
        },
        "neural_controller": "mc_nn_control mode 23",
        "mode_23_identity_required": True,
        "validity_automation": {
            "symmetric_decontamination": True,
            "fail_loud_gates": ["decontamination", "mcnn_identity"],
            "rho_jitter_reproduction_margins": reproduction_margins(),
            "theta_seed_ulog_mapping": "result.evidence and progress.theta_ulog_map",
        },
        "mock_evaluator": bool(args.mock_evaluator),
        "scope_note": "Tier 0.5 fitness-wire run; not a convergence or baseline experiment.",
    }
    write_json(run_dir / "metadata.json", metadata)

    env = dict(**os_environ_with_speed(args.sim_speed_factor))
    thresholds = load_thresholds(args.thresholds_json)
    if not args.mock_evaluator:
        if args.skip_build:
            m1.run_checked([str(REPO_ROOT / "scripts/install_mcnn_sih_board.sh")], cwd=REPO_ROOT, log=run_dir / "build.log", env=env)
            m1.run_checked([str(REPO_ROOT / "scripts/install_m1_sih_x500.sh")], cwd=REPO_ROOT, log=run_dir / "build.log", env=env)
        else:
            build_env = env.copy()
            build_env["PX4_MCNN_SIH_BUILD_LOG"] = str(run_dir / "px4_mcnn_sih_build.log")
            m1.run_checked([str(REPO_ROOT / "scripts/build_px4_mcnn_sih.sh")], cwd=REPO_ROOT, log=run_dir / "build.log", env=build_env)
    archive: dict[str, dict[str, Any]] = {}
    results: list[EvalResult] = []
    primary_candidates: list[dict[str, Any]] = []
    deadline = time.monotonic() + args.max_wall_clock_s if args.max_wall_clock_s else None

    for index in range(args.budget):
        if deadline is not None and time.monotonic() >= deadline:
            break
        selected_parent_tag = None
        selected_parent_quality = None
        if args.strategy == "random":
            genome = random_candidate_genome(args.subspace, rng)
            selection_source = "random_baseline"
        else:
            parent = select_parent(archive, rng)
            if parent is None or index < args.bootstrap:
                genome = random_candidate_genome(args.subspace, rng)
                selection_source = "bootstrap_random"
            else:
                selected_parent_tag = parent["result"].get("tag")
                selected_parent_quality = float(parent["result"]["quality"])
                parent_genome = parent["genome"]
                if args.crossover and len(archive) > 1 and rng.random() < args.crossover_rate:
                    mate = select_parent(archive, rng)
                    mate_genome = mate["genome"] if mate is not None else parent_genome
                    genome = crossover_candidate_genome(parent_genome, mate_genome, args.subspace, rng)
                    genome = mutate_candidate_genome(genome, args.subspace, rng)
                    selection_source = "elite_crossover_mutation"
                else:
                    genome = mutate_candidate_genome(parent_genome, args.subspace, rng)
                    selection_source = "elite_mutation"
        tag = f"{run_id}_e{index:04d}"
        theta = theta_genome.theta_from_genome(genome, tag, args.seed + index)
        theta.setdefault("m2_map_elites", {})["selection"] = {
            "source": selection_source,
            "selected_parent_tag": selected_parent_tag,
            "selected_parent_quality": selected_parent_quality,
        }
        theta_path = theta_dir / f"{tag}.json"
        docs_dir = evals_dir / tag
        result = evaluate_theta(
            theta,
            theta_path,
            docs_dir,
            index,
            args.run_timeout,
            env,
            thresholds,
            selected_parent_tag=selected_parent_tag,
            selected_parent_quality=selected_parent_quality,
            mock_evaluator=args.mock_evaluator,
            target_properties=args.resolved_target_properties,
        )
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

        progress = append_progress(run_dir / "progress.jsonl", result, results, archive, selection_source)
        print(
            json.dumps(
                {
                    "eval": index,
                    "tag": tag,
                    "bin": bin_name,
                    "quality": result.quality,
                    "best_so_far_quality": progress["best_so_far_quality"],
                    "archive_bins": progress["archive_bins"],
                    "qd_score": progress["qd_score"],
                    "best_property": result.fitness.get("best_property"),
                    "valid_property_count": result.fitness.get("valid_property_count"),
                    "quadrant": result.quadrant,
                    "primary_bug": result.primary_bug,
                    "classical_usable": result.classical_usable,
                    "selection_source": selection_source,
                    "selected_parent_tag": selected_parent_tag,
                    "selected_parent_quality": selected_parent_quality,
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
    env = m1.agent_env(REPO_ROOT)
    env = with_ros_environment(env)
    env["PX4_SIM_SPEED_FACTOR"] = str(sim_speed_factor)
    return env


def with_ros_environment(env: dict[str, str]) -> dict[str, str]:
    setup_files = [Path("/opt/ros/jazzy/setup.bash"), REPO_ROOT / "ros2_ws/install/setup.bash"]
    existing = [path for path in setup_files if path.exists()]
    if shutil.which("ros2", path=env.get("PATH")) and not (REPO_ROOT / "ros2_ws/install/setup.bash").exists():
        return env
    if not existing:
        return env
    source_cmd = " && ".join(f"source {path}" for path in existing)
    result = subprocess.run(
        ["bash", "-lc", f"{source_cmd} && env -0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    overlay: dict[str, str] = {}
    for item in result.stdout.decode("utf-8", errors="replace").split("\0"):
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        overlay[key] = value
    merged = dict(env)
    for key in [
        "PATH",
        "LD_LIBRARY_PATH",
        "PYTHONPATH",
        "AMENT_PREFIX_PATH",
        "CMAKE_PREFIX_PATH",
        "COLCON_PREFIX_PATH",
        "ROS_DISTRO",
        "ROS_PYTHON_VERSION",
        "ROS_VERSION",
    ]:
        if key in overlay:
            merged[key] = overlay[key]
    return merged


def robust_properties_from_result(result: dict[str, Any]) -> set[str]:
    fitness = result.get("fitness", {}) if isinstance(result, dict) else {}
    if not isinstance(fitness, dict):
        return set()
    return target_finding_properties(fitness)


def strict_properties_from_result(result: dict[str, Any]) -> set[str]:
    fitness = result.get("fitness", {}) if isinstance(result, dict) else {}
    if not isinstance(fitness, dict):
        return set()
    return target_strict_differential_properties(fitness)


def confirm_candidates(
    run_dir: Path,
    candidates: list[dict[str, Any]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    env = os_environ_with_speed(args.sim_speed_factor)
    thresholds = load_thresholds(args.thresholds_json)
    confirmed: list[dict[str, Any]] = []
    selected = sorted(candidates, key=lambda item: float(item["result"]["quality"]), reverse=True)[
        : args.max_confirm_candidates
    ]
    confirmed_relative: list[dict[str, Any]] = []
    for cidx, candidate in enumerate(selected):
        theta = load_json(Path(candidate["theta_path"]))
        required_properties = robust_properties_from_result(candidate["result"])
        strict_required_properties = strict_properties_from_result(candidate["result"])
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
                env,
                thresholds,
                selected_parent_tag=original_tag,
                selected_parent_quality=float(candidate["result"]["quality"]),
                mock_evaluator=args.mock_evaluator,
                target_properties=args.resolved_target_properties,
            )
            result_record = result.as_dict()
            repeated_properties = robust_properties_from_result(result_record)
            result_record["confirmation_required_properties"] = sorted(required_properties)
            result_record["confirmation_repeated_properties"] = sorted(repeated_properties)
            result_record["confirmation_property_match"] = bool(required_properties & repeated_properties)
            repeats.append(result_record)
            if result.returncode != 0 or not bool(required_properties & repeated_properties):
                all_passed = False
        record = {
            "candidate": candidate,
            "passed": all_passed,
            "required_properties": sorted(required_properties),
            "strict_required_properties": sorted(strict_required_properties),
            "rho_jitter_reproduction_margins": reproduction_margins(),
            "repeats": repeats,
        }
        if all_passed:
            if strict_required_properties:
                confirmed.append(record)
                primary_dir = REPO_ROOT / "config" / "m2_primary_bugs"
                primary_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate["theta_path"], primary_dir / Path(candidate["theta_path"]).name)
            else:
                confirmed_relative.append(record)
        append_jsonl(run_dir / "confirmations.jsonl", record)
        write_json(run_dir / "confirmed_primary_bugs.json", confirmed)
        write_json(run_dir / "confirmed_relative_degradations.json", confirmed_relative)
    write_json(run_dir / "confirmed_primary_bugs.json", confirmed)
    write_json(run_dir / "confirmed_relative_degradations.json", confirmed_relative)
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
        "## progress",
    ]
    progress_records: list[dict[str, Any]] = []
    progress_path = run_dir / "progress.jsonl"
    if progress_path.exists():
        with progress_path.open("r", encoding="utf-8") as handle:
            progress_records = [json.loads(line) for line in handle if line.strip()]
    if not progress_records:
        lines.append("- none")
    else:
        wanted = {0, len(progress_records) // 2, len(progress_records) - 1}
        lines.append("| eval | best quality | archive bins | QD-score | source | parent quality |")
        lines.append("|---:|---:|---:|---:|---|---:|")
        for idx, record in enumerate(progress_records):
            if idx not in wanted:
                continue
            parent_quality = record.get("selected_parent_quality")
            parent_text = "n/a" if parent_quality is None else f"{float(parent_quality):.6g}"
            lines.append(
                f"| {record['eval']} | {float(record['best_so_far_quality']):.6g} | "
                f"{record['archive_bins']} | {float(record['qd_score']):.6g} | "
                f"{record['selection_source']} | {parent_text} |"
            )
    lines.extend(
        [
            "",
            "## best elites",
        ]
    )
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
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--thresholds-json", type=Path)
    parser.add_argument("--mock-evaluator", action="store_true")
    parser.add_argument("--strategy", choices=STRATEGIES, default="map-elites")
    parser.add_argument("--subspace", choices=SUBSPACES, default="full")
    parser.add_argument(
        "--target-properties",
        default="auto",
        help=(
            "Target preset or comma list. Presets: auto, behavior, behavior-step, "
            "route-a-catastrophic, validation."
        ),
    )
    parser.add_argument("--crossover", action="store_true")
    parser.add_argument("--crossover-rate", type=float, default=0.25)
    args = parser.parse_args()
    args.resolved_target_properties = parse_target_properties(args.target_properties)

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
