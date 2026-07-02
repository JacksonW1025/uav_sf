#!/usr/bin/env python3
"""Tier 0.5 theta genome for property-oracle fuzzing.

This module is deliberately offline: it defines a searchable scenario genome,
genetic operators, legality checks, MAP-Elites feature bins, and conversion to
the existing m1_offboard_task.py theta JSON shape. Fitness wiring belongs to
the next Tier 0.5 step.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

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
NOMINAL_TWR = 4.0 * NOMINAL["t_max"] / (NOMINAL["mass"] * 9.80665)

BASE_BOOT_PARAMS = {
    "MC_NN_EN": 0,
    "MC_NN_MANL_CTRL": 0,
}

BASE_PX4_PARAMS = {
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

COMBINED_STEADY_DISTURBANCE_TYPE = "steady_combo"
DISTURBANCE_TYPES = [
    "wind",
    "physics_mismatch",
    COMBINED_STEADY_DISTURBANCE_TYPE,
    "state_contam",
    "switching",
    "step",
]
SHIM_FREE_DISTURBANCE_TYPES = ["wind", "physics_mismatch", "switching", "step"]
AXES = ["x", "y", "z"]
SIGNS = [-1, 1]
SETPOINT_RATES_HZ = [50.0, 80.0, 100.0]
SETTLING_WINDOW_S = 12.0
SWITCH_DESCRIPTOR_ROLL_PITCH_RANGE = (16.0, 50.0)
SWITCH_DESCRIPTOR_RATE_RANGE = (0.45, 2.75)
SWITCH_DESCRIPTOR_WIND_RANGE = (0.0, 6.0)
SWITCH_DESCRIPTOR_BUCKETS = 5


@dataclass(frozen=True)
class VariableSpec:
    name: str
    group: str
    kind: str
    bounds: tuple[float, float] | None
    choices: tuple[Any, ...] | None
    simulator: str
    injection: str
    route_status: str
    enabled: bool
    notes: str

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.bounds is not None:
            data["bounds"] = list(self.bounds)
        if self.choices is not None:
            data["choices"] = list(self.choices)
        return data


VARIABLE_SPECS: list[VariableSpec] = [
    VariableSpec(
        "disturbance_type",
        "map_elites",
        "categorical",
        None,
        tuple(DISTURBANCE_TYPES),
        "SIH",
        "scenario selector",
        "state_contam choice is DEFERRED pending m2b shim patch drift",
        True,
        "Scenario selector. steady_combo is reserved for the steady-wind-physics subspace.",
    ),
    VariableSpec(
        "wind_speed_m_s",
        "wind",
        "continuous",
        (0.0, 8.0),
        None,
        "SIH",
        "SIH_WIND_N/E boot + runtime params",
        "shim-free",
        True,
        "Sustained horizontal wind magnitude. The upper bound matches prior productive SIH wind without going to fault-only extremes.",
    ),
    VariableSpec(
        "wind_direction_rad",
        "wind",
        "continuous",
        (0.0, 2.0 * math.pi),
        None,
        "SIH",
        "SIH_WIND_N/E boot + runtime params",
        "shim-free",
        True,
        "NED horizontal wind direction; components are speed*cos/sin.",
    ),
    VariableSpec(
        "mass_scale",
        "physics_mismatch",
        "continuous",
        (0.85, 1.25),
        None,
        "SIH",
        "SIH_MASS + inertia params",
        "shim-free",
        True,
        "Moderate payload/mass mismatch; excludes both-controllers-disaster mass swings.",
    ),
    VariableSpec(
        "inertia_roll_scale",
        "physics_mismatch",
        "continuous",
        (0.70, 1.60),
        None,
        "SIH",
        "SIH_IXX",
        "shim-free",
        True,
        "Roll inertia scale, coupled with mass_scale.",
    ),
    VariableSpec(
        "inertia_pitch_scale",
        "physics_mismatch",
        "continuous",
        (0.70, 1.60),
        None,
        "SIH",
        "SIH_IYY",
        "shim-free",
        True,
        "Pitch inertia scale, coupled with mass_scale.",
    ),
    VariableSpec(
        "inertia_yaw_scale",
        "physics_mismatch",
        "continuous",
        (0.70, 1.80),
        None,
        "SIH",
        "SIH_IZZ",
        "shim-free",
        True,
        "Yaw inertia scale, coupled with mass_scale.",
    ),
    VariableSpec(
        "twr_scale",
        "physics_mismatch",
        "continuous",
        (0.90, 1.15),
        None,
        "SIH",
        "SIH_T_MAX/SIH_Q_MAX + MPC_THR_HOVER compensation",
        "shim-free; high-TWR findings require multi-seed confirmation",
        True,
        "Thrust-to-weight scale around the nominal X500 SIH plant; bounded to avoid the old high-TWR false-positive corner.",
    ),
    VariableSpec(
        "fake_velocity_bias_m_s",
        "state_contam",
        "continuous",
        (-0.50, 0.50),
        None,
        "SIH",
        "m2b publish-point state shim",
        "DEFERRED - pending m2b_state_shim.patch drift",
        False,
        "False shared velocity belief. Kept in the spec but not routable until the shim patch is realigned.",
    ),
    VariableSpec(
        "fake_angular_rate_bias_rad_s",
        "state_contam",
        "continuous",
        (-0.25, 0.25),
        None,
        "SIH",
        "m2b publish-point state shim",
        "DEFERRED - pending m2b_state_shim.patch drift",
        False,
        "False shared angular-rate belief. Disabled for the delivered shim-free genome.",
    ),
    VariableSpec(
        "position_estimate_jump_m",
        "state_contam",
        "continuous",
        (-0.50, 0.50),
        None,
        "SIH",
        "m2b publish-point state shim",
        "DEFERRED - pending m2b_state_shim.patch drift",
        False,
        "False position jump. Disabled for the delivered shim-free genome.",
    ),
    VariableSpec(
        "approach_radius_m",
        "switching",
        "continuous",
        (1.8, 6.0),
        None,
        "SIH",
        "offboard circle setpoint",
        "shim-free",
        True,
        "Pre-switch circle radius used to create a reachable handoff state.",
    ),
    VariableSpec(
        "approach_frequency_hz",
        "switching",
        "continuous",
        (0.25, 0.50),
        None,
        "SIH",
        "offboard circle setpoint",
        "shim-free",
        True,
        "Pre-switch circle frequency; bounded below extreme FUZZ-1 corners.",
    ),
    VariableSpec(
        "approach_phase_rad",
        "switching",
        "continuous",
        (0.0, 2.0 * math.pi),
        None,
        "SIH",
        "offboard circle setpoint",
        "shim-free",
        True,
        "Circle phase at trajectory start.",
    ),
    VariableSpec(
        "switch_roll_pitch_deg",
        "switching",
        "continuous",
        (12.0, 55.0),
        None,
        "SIH",
        "groundtruth activation_trigger roll/pitch window",
        "shim-free",
        True,
        "Reachable Method-A handoff attitude target. Cross-constrained to the circle's expected tilt.",
    ),
    VariableSpec(
        "switch_rate_rad_s",
        "switching",
        "continuous",
        (0.30, 3.00),
        None,
        "SIH",
        "groundtruth activation_trigger angular-rate window",
        "shim-free",
        True,
        "Reachable Method-A handoff angular-rate target.",
    ),
    VariableSpec(
        "switch_delay_s",
        "switching",
        "continuous",
        (0.0, 1.0),
        None,
        "SIH",
        "activation_trigger.switch_delay_s in m1_offboard_task.py",
        "shim-free",
        True,
        "Delay between groundtruth trigger and controller mode command.",
    ),
    VariableSpec(
        "step_magnitude_m",
        "step",
        "continuous",
        (0.50, 1.50),
        None,
        "SIH",
        "offboard trajectory_setpoint step.delta_ned",
        "shim-free",
        True,
        "Moderate P5 settling step, explicitly not a C-tier amplitude attack.",
    ),
    VariableSpec(
        "step_axis",
        "step",
        "categorical",
        None,
        tuple(AXES),
        "SIH",
        "offboard trajectory_setpoint step.delta_ned",
        "shim-free",
        True,
        "NED axis for the P5 step.",
    ),
    VariableSpec(
        "step_sign",
        "step",
        "discrete",
        None,
        tuple(SIGNS),
        "SIH",
        "offboard trajectory_setpoint step.delta_ned",
        "shim-free",
        True,
        "Direction on the selected NED axis.",
    ),
    VariableSpec(
        "step_time_s",
        "step",
        "continuous",
        (28.0, 40.0),
        None,
        "SIH",
        "timing.trajectory_start_s + setpoint.step.start_s",
        "shim-free",
        True,
        "Step event time; must leave T_set + W_hold + slack before mission_end_s.",
    ),
    VariableSpec(
        "mission_end_s",
        "timing",
        "continuous",
        (46.0, 70.0),
        None,
        "SIH",
        "m1_offboard_task timing.mission_end_s",
        "shim-free",
        True,
        "Mission end used by all scenario types; cross-constrained with step_time_s.",
    ),
    VariableSpec(
        "setpoint_rate_hz",
        "timing",
        "categorical",
        None,
        tuple(SETPOINT_RATES_HZ),
        "SIH",
        "offboard setpoint publication rate",
        "shim-free",
        True,
        "Publication rate stressor; not a stale/missing setpoint attack.",
    ),
]

SPEC_BY_NAME = {spec.name: spec for spec in VARIABLE_SPECS}


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def wrap_2pi(value: float) -> float:
    return float(value) % (2.0 * math.pi)


def nearest_choice(value: Any, choices: list[Any]) -> Any:
    if value in choices:
        return value
    if choices and all(isinstance(item, (int, float)) for item in choices):
        return min(choices, key=lambda item: abs(float(item) - float(value)))
    return choices[0]


def default_genome(disturbance_type: str = "wind") -> dict[str, Any]:
    return normalize_genome(
        {
            "disturbance_type": disturbance_type,
            "wind_speed_m_s": 0.0,
            "wind_direction_rad": 0.0,
            "mass_scale": 1.0,
            "inertia_roll_scale": 1.0,
            "inertia_pitch_scale": 1.0,
            "inertia_yaw_scale": 1.0,
            "twr_scale": 1.0,
            "fake_velocity_bias_m_s": 0.0,
            "fake_angular_rate_bias_rad_s": 0.0,
            "position_estimate_jump_m": 0.0,
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
            "mission_end_s": 54.0,
            "setpoint_rate_hz": 80.0,
        }
    )


def random_genome(rng: random.Random, *, include_deferred: bool = False) -> dict[str, Any]:
    choices = DISTURBANCE_TYPES if include_deferred else SHIM_FREE_DISTURBANCE_TYPES
    weights = [0.30, 0.35, 0.20, 0.15] if not include_deferred else [0.24, 0.27, 0.10, 0.12, 0.15, 0.12]
    disturbance_type = rng.choices(choices, weights=weights[: len(choices)], k=1)[0]
    genome = default_genome(disturbance_type)

    if disturbance_type == "wind":
        genome["wind_speed_m_s"] = rng.uniform(0.5, 8.0)
        genome["wind_direction_rad"] = rng.uniform(0.0, 2.0 * math.pi)
    elif disturbance_type == "physics_mismatch":
        genome["mass_scale"] = rng.uniform(0.88, 1.23)
        genome["inertia_roll_scale"] = rng.uniform(0.75, 1.55)
        genome["inertia_pitch_scale"] = rng.uniform(0.75, 1.55)
        genome["inertia_yaw_scale"] = rng.uniform(0.75, 1.75)
        genome["twr_scale"] = rng.uniform(0.92, 1.13)
    elif disturbance_type == COMBINED_STEADY_DISTURBANCE_TYPE:
        genome["wind_speed_m_s"] = rng.uniform(0.5, 8.0)
        genome["wind_direction_rad"] = rng.uniform(0.0, 2.0 * math.pi)
        genome["mass_scale"] = rng.uniform(0.88, 1.25)
        genome["inertia_roll_scale"] = rng.uniform(0.75, 1.60)
        genome["inertia_pitch_scale"] = rng.uniform(0.75, 1.60)
        genome["inertia_yaw_scale"] = rng.uniform(0.75, 1.80)
        genome["twr_scale"] = rng.uniform(0.92, 1.13)
    elif disturbance_type == "state_contam":
        genome["fake_velocity_bias_m_s"] = rng.uniform(-0.45, 0.45)
        genome["fake_angular_rate_bias_rad_s"] = rng.uniform(-0.20, 0.20)
        genome["position_estimate_jump_m"] = rng.uniform(-0.45, 0.45)
    elif disturbance_type == "switching":
        genome["approach_radius_m"] = rng.uniform(1.8, 6.0)
        genome["approach_frequency_hz"] = rng.uniform(0.25, 0.50)
        genome["approach_phase_rad"] = rng.uniform(0.0, 2.0 * math.pi)
        expected = expected_circle_tilt_deg(genome)
        genome["switch_roll_pitch_deg"] = rng.uniform(max(12.0, expected - 7.0), min(55.0, expected + 7.0))
        genome["switch_rate_rad_s"] = rng.uniform(0.45, 2.8)
        genome["switch_delay_s"] = rng.uniform(0.0, 0.8)
        if rng.random() < 0.55:
            genome["wind_speed_m_s"] = rng.uniform(0.0, 6.0)
            genome["wind_direction_rad"] = rng.uniform(0.0, 2.0 * math.pi)
    elif disturbance_type == "step":
        genome["step_magnitude_m"] = rng.uniform(0.50, 1.25)
        genome["step_axis"] = rng.choice(AXES)
        genome["step_sign"] = rng.choice(SIGNS)
        genome["step_time_s"] = rng.uniform(30.0, 38.0)
        genome["mission_end_s"] = rng.uniform(genome["step_time_s"] + SETTLING_WINDOW_S, 62.0)
        genome["setpoint_rate_hz"] = rng.choice(SETPOINT_RATES_HZ)

    return normalize_genome(genome)


def normalize_genome(genome: dict[str, Any]) -> dict[str, Any]:
    out = dict(default_values())
    out.update(genome)
    for spec in VARIABLE_SPECS:
        value = out.get(spec.name)
        if spec.kind == "continuous":
            lo, hi = spec.bounds or (0.0, 1.0)
            out[spec.name] = clamp(float(value), lo, hi)
        elif spec.kind in {"categorical", "discrete"}:
            choices = list(spec.choices or ())
            if not choices:
                continue
            out[spec.name] = nearest_choice(value, choices)

    out["wind_direction_rad"] = wrap_2pi(float(out["wind_direction_rad"]))
    out["approach_phase_rad"] = wrap_2pi(float(out["approach_phase_rad"]))

    # Keep Method-A switching windows reachable by the chosen circle profile.
    expected_tilt = expected_circle_tilt_deg(out)
    if expected_tilt > 63.0:
        radius = float(out["approach_radius_m"])
        max_lateral = math.tan(math.radians(63.0)) * 9.80665
        out["approach_frequency_hz"] = clamp(
            math.sqrt(max_lateral / radius) / (2.0 * math.pi),
            SPEC_BY_NAME["approach_frequency_hz"].bounds[0],
            SPEC_BY_NAME["approach_frequency_hz"].bounds[1],
        )
    expected_tilt = expected_circle_tilt_deg(out)
    low = max(12.0, expected_tilt - 8.0)
    high = min(55.0, expected_tilt + 8.0)
    if low <= high:
        out["switch_roll_pitch_deg"] = clamp(float(out["switch_roll_pitch_deg"]), low, high)
    expected_rate = 2.0 * math.pi * float(out["approach_frequency_hz"])
    out["switch_rate_rad_s"] = clamp(float(out["switch_rate_rad_s"]), max(0.30, expected_rate - 1.2), min(3.0, expected_rate + 1.0))

    min_end = float(out["step_time_s"]) + SETTLING_WINDOW_S
    if float(out["mission_end_s"]) < min_end:
        out["mission_end_s"] = min(SPEC_BY_NAME["mission_end_s"].bounds[1], min_end)
    if float(out["mission_end_s"]) - float(out["step_time_s"]) < SETTLING_WINDOW_S:
        out["step_time_s"] = float(out["mission_end_s"]) - SETTLING_WINDOW_S

    if out["disturbance_type"] != "state_contam":
        out["fake_velocity_bias_m_s"] = 0.0
        out["fake_angular_rate_bias_rad_s"] = 0.0
        out["position_estimate_jump_m"] = 0.0
    wind_enabled = out["disturbance_type"] in {"wind", "switching", COMBINED_STEADY_DISTURBANCE_TYPE}
    physics_enabled = out["disturbance_type"] in {"physics_mismatch", COMBINED_STEADY_DISTURBANCE_TYPE}
    if not wind_enabled:
        out["wind_speed_m_s"] = 0.0
    if not physics_enabled:
        out["mass_scale"] = 1.0
        out["inertia_roll_scale"] = 1.0
        out["inertia_pitch_scale"] = 1.0
        out["inertia_yaw_scale"] = 1.0
        out["twr_scale"] = 1.0

    return out


def default_values() -> dict[str, Any]:
    return {
        "disturbance_type": "wind",
        "wind_speed_m_s": 0.0,
        "wind_direction_rad": 0.0,
        "mass_scale": 1.0,
        "inertia_roll_scale": 1.0,
        "inertia_pitch_scale": 1.0,
        "inertia_yaw_scale": 1.0,
        "twr_scale": 1.0,
        "fake_velocity_bias_m_s": 0.0,
        "fake_angular_rate_bias_rad_s": 0.0,
        "position_estimate_jump_m": 0.0,
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
        "mission_end_s": 54.0,
        "setpoint_rate_hz": 80.0,
    }


def mutate_genome(parent: dict[str, Any], rng: random.Random, *, include_deferred: bool = False) -> dict[str, Any]:
    genome = dict(parent)
    if rng.random() < 0.08:
        choices = DISTURBANCE_TYPES if include_deferred else SHIM_FREE_DISTURBANCE_TYPES
        genome["disturbance_type"] = rng.choice(choices)

    sigmas = {
        "wind_speed_m_s": 1.2,
        "wind_direction_rad": 0.7,
        "mass_scale": 0.05,
        "inertia_roll_scale": 0.12,
        "inertia_pitch_scale": 0.12,
        "inertia_yaw_scale": 0.15,
        "twr_scale": 0.04,
        "fake_velocity_bias_m_s": 0.08,
        "fake_angular_rate_bias_rad_s": 0.035,
        "position_estimate_jump_m": 0.08,
        "approach_radius_m": 0.45,
        "approach_frequency_hz": 0.035,
        "approach_phase_rad": 0.7,
        "switch_roll_pitch_deg": 4.0,
        "switch_rate_rad_s": 0.25,
        "switch_delay_s": 0.15,
        "step_magnitude_m": 0.12,
        "step_time_s": 1.2,
        "mission_end_s": 1.5,
    }
    for key, sigma in sigmas.items():
        if rng.random() < 0.35:
            genome[key] = float(genome[key]) + rng.gauss(0.0, sigma)
    if rng.random() < 0.10:
        genome["step_axis"] = rng.choice(AXES)
    if rng.random() < 0.10:
        genome["step_sign"] = rng.choice(SIGNS)
    if rng.random() < 0.10:
        genome["setpoint_rate_hz"] = rng.choice(SETPOINT_RATES_HZ)
    return normalize_genome(genome)


def crossover_genome(a: dict[str, Any], b: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    child = {}
    for key in default_values():
        child[key] = a.get(key) if rng.random() < 0.5 else b.get(key)
    if rng.random() < 0.5:
        child["disturbance_type"] = a.get("disturbance_type", child["disturbance_type"])
    else:
        child["disturbance_type"] = b.get("disturbance_type", child["disturbance_type"])
    return normalize_genome(child)


def expected_circle_tilt_deg(genome: dict[str, Any]) -> float:
    radius = float(genome["approach_radius_m"])
    freq = float(genome["approach_frequency_hz"])
    lateral_accel = radius * (2.0 * math.pi * freq) ** 2
    return math.degrees(math.atan2(lateral_accel, 9.80665))


def wind_components(genome: dict[str, Any]) -> tuple[float, float]:
    speed = float(genome["wind_speed_m_s"])
    direction = float(genome["wind_direction_rad"])
    return speed * math.cos(direction), speed * math.sin(direction)


def hover_throttle(mass_kg: float, t_max_n: float) -> float:
    return mass_kg * 9.80665 / (4.0 * t_max_n)


def physical_params(genome: dict[str, Any]) -> dict[str, float]:
    mass = NOMINAL["mass"] * float(genome["mass_scale"])
    twr = NOMINAL_TWR * float(genome["twr_scale"])
    t_max = twr * mass * 9.80665 / 4.0
    ixx = NOMINAL["ixx"] * float(genome["mass_scale"]) * float(genome["inertia_roll_scale"])
    iyy = NOMINAL["iyy"] * float(genome["mass_scale"]) * float(genome["inertia_pitch_scale"])
    izz = NOMINAL["izz"] * float(genome["mass_scale"]) * float(genome["inertia_yaw_scale"])
    wind_n, wind_e = wind_components(genome)
    return {
        "SIH_MASS": mass,
        "SIH_IXX": ixx,
        "SIH_IYY": iyy,
        "SIH_IZZ": izz,
        "SIH_T_MAX": t_max,
        "SIH_Q_MAX": NOMINAL["q_max"] * float(genome["twr_scale"]),
        "SIH_L_ROLL": NOMINAL["l_roll"],
        "SIH_L_PITCH": NOMINAL["l_pitch"],
        "SIH_KDV": NOMINAL["kdv"],
        "SIH_KDW": NOMINAL["kdw"],
        "SIH_T_TAU": NOMINAL["t_tau"],
        "SIH_WIND_N": wind_n,
        "SIH_WIND_E": wind_e,
        "MPC_THR_HOVER": clamp(hover_throttle(mass, t_max), 0.25, 0.9),
    }


def active_step_delta(genome: dict[str, Any]) -> list[float]:
    delta = [0.0, 0.0, 0.0]
    axis = AXES.index(str(genome["step_axis"]))
    delta[axis] = float(genome["step_sign"]) * float(genome["step_magnitude_m"])
    return [round(value, 4) for value in delta]


def genome_severity(genome: dict[str, Any]) -> dict[str, float]:
    wind = float(genome["wind_speed_m_s"]) / 8.0
    physics = max(
        abs(float(genome["mass_scale"]) - 1.0) / 0.25,
        abs(float(genome["inertia_roll_scale"]) - 1.0) / 0.60,
        abs(float(genome["inertia_pitch_scale"]) - 1.0) / 0.60,
        abs(float(genome["inertia_yaw_scale"]) - 1.0) / 0.80,
        abs(float(genome["twr_scale"]) - 1.0) / 0.15,
    )
    state = max(
        abs(float(genome["fake_velocity_bias_m_s"])) / 0.50,
        abs(float(genome["fake_angular_rate_bias_rad_s"])) / 0.25,
        abs(float(genome["position_estimate_jump_m"])) / 0.50,
    )
    switching = max(
        (float(genome["switch_roll_pitch_deg"]) - 12.0) / 43.0,
        float(genome["switch_rate_rad_s"]) / 3.0,
        float(genome["switch_delay_s"]),
    )
    step = (float(genome["step_magnitude_m"]) - 0.50) / 1.0
    return {
        "wind": clamp(wind, 0.0, 1.0),
        "physics_mismatch": clamp(physics, 0.0, 1.0),
        COMBINED_STEADY_DISTURBANCE_TYPE: clamp(max(wind, physics), 0.0, 1.0),
        "state_contam": clamp(state, 0.0, 1.0),
        "switching": clamp(switching, 0.0, 1.0),
        "step": clamp(step, 0.0, 1.0),
    }


def severity_bucket(severity: float) -> str:
    if severity < 0.34:
        return "low"
    if severity < 0.67:
        return "mid"
    return "high"


def numeric_bucket(value: float, lo: float, hi: float, count: int, prefix: str) -> str:
    if count <= 1 or hi <= lo:
        return f"{prefix}_0"
    clamped = clamp(float(value), float(lo), float(hi))
    idx = min(count - 1, int((clamped - lo) / (hi - lo) * count))
    return f"{prefix}_{idx}"


def feature_bin(genome: dict[str, Any]) -> tuple[str, str, float]:
    severities = genome_severity(genome)
    kind = str(genome["disturbance_type"])
    if kind == COMBINED_STEADY_DISTURBANCE_TYPE:
        wind_severity = severities["wind"]
        physics_severity = severities["physics_mismatch"]
        severity = max(wind_severity, physics_severity)
        bucket = f"wind_{severity_bucket(wind_severity)}:physics_{severity_bucket(physics_severity)}"
        return kind, bucket, severity
    if kind == "switching":
        rp_bucket = numeric_bucket(
            float(genome["switch_roll_pitch_deg"]),
            SWITCH_DESCRIPTOR_ROLL_PITCH_RANGE[0],
            SWITCH_DESCRIPTOR_ROLL_PITCH_RANGE[1],
            SWITCH_DESCRIPTOR_BUCKETS,
            "rp",
        )
        wind_bucket = numeric_bucket(
            float(genome["wind_speed_m_s"]),
            SWITCH_DESCRIPTOR_WIND_RANGE[0],
            SWITCH_DESCRIPTOR_WIND_RANGE[1],
            SWITCH_DESCRIPTOR_BUCKETS,
            "wind",
        )
        severity = severities[kind]
        return kind, f"{rp_bucket}:{wind_bucket}", severity
    severity = severities[kind]
    bucket = severity_bucket(severity)
    return kind, bucket, severity


def feature_metadata(genome: dict[str, Any]) -> dict[str, Any]:
    kind, bucket, severity = feature_bin(genome)
    if kind == "switching":
        rp_bucket, wind_bucket = bucket.split(":", 1)
        return {
            "feature_dimensions": ["switch_roll_pitch_bucket", "wind_bucket"],
            "disturbance_type": kind,
            "amplitude_bucket": bucket,
            "switch_roll_pitch_bucket": rp_bucket,
            "wind_bucket": wind_bucket,
            "switch_roll_pitch_deg": round(float(genome["switch_roll_pitch_deg"]), 6),
            "switch_rate_rad_s": round(float(genome["switch_rate_rad_s"]), 6),
            "wind_speed_m_s": round(float(genome["wind_speed_m_s"]), 6),
            "switch_descriptor_roll_pitch_range_deg": list(SWITCH_DESCRIPTOR_ROLL_PITCH_RANGE),
            "switch_descriptor_wind_range_m_s": list(SWITCH_DESCRIPTOR_WIND_RANGE),
            "switch_rate_rad_s_diagnostic_range": list(SWITCH_DESCRIPTOR_RATE_RANGE),
            "switch_descriptor_bucket_count": SWITCH_DESCRIPTOR_BUCKETS,
            "severity": round(severity, 6),
        }
    if kind != COMBINED_STEADY_DISTURBANCE_TYPE:
        return {
            "feature_dimensions": ["disturbance_type", "amplitude_bucket"],
            "disturbance_type": kind,
            "amplitude_bucket": bucket,
            "severity": round(severity, 6),
        }
    severities = genome_severity(genome)
    wind_severity = severities["wind"]
    physics_severity = severities["physics_mismatch"]
    return {
        "feature_dimensions": ["wind_bucket", "physics_bucket"],
        "disturbance_type": kind,
        "amplitude_bucket": bucket,
        "wind_bucket": severity_bucket(wind_severity),
        "physics_bucket": severity_bucket(physics_severity),
        "wind_severity": round(wind_severity, 6),
        "physics_severity": round(physics_severity, 6),
        "severity": round(severity, 6),
    }


def validate_genome(genome: dict[str, Any], *, allow_deferred: bool = False) -> list[str]:
    errors: list[str] = []
    for spec in VARIABLE_SPECS:
        if spec.name not in genome:
            errors.append(f"missing {spec.name}")
            continue
        value = genome[spec.name]
        if spec.kind == "continuous":
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                errors.append(f"{spec.name} must be finite numeric")
                continue
            lo, hi = spec.bounds or (-math.inf, math.inf)
            if float(value) < lo - 1e-9 or float(value) > hi + 1e-9:
                errors.append(f"{spec.name} out of bounds [{lo}, {hi}]: {value}")
        elif spec.kind == "categorical":
            if value not in (spec.choices or ()):
                errors.append(f"{spec.name} not in {spec.choices}: {value}")
        elif spec.kind == "discrete":
            if value not in (spec.choices or ()):
                errors.append(f"{spec.name} not in {spec.choices}: {value}")

    if genome.get("disturbance_type") == "state_contam" and not allow_deferred:
        errors.append("state_contam is DEFERRED pending m2b shim patch drift")

    if float(genome["mission_end_s"]) - float(genome["step_time_s"]) < SETTLING_WINDOW_S - 1e-9:
        errors.append("step_time_s does not leave the P5 settling window before mission_end_s")
    if float(genome["step_magnitude_m"]) < 0.50 or float(genome["step_magnitude_m"]) > 1.50:
        errors.append("step_magnitude_m outside the moderate P5 step range")

    if genome.get("disturbance_type") == "switching":
        expected_tilt = expected_circle_tilt_deg(genome)
        if abs(float(genome["switch_roll_pitch_deg"]) - expected_tilt) > 8.0 + 1e-9:
            errors.append("switch_roll_pitch_deg is not reachable from the selected circle profile")

    hover = physical_params(genome)["MPC_THR_HOVER"]
    if hover > 0.88:
        errors.append(f"MPC_THR_HOVER too close to loss-of-authority: {hover:.3f}")
    return errors


def assert_valid_genome(genome: dict[str, Any], *, allow_deferred: bool = False) -> None:
    errors = validate_genome(genome, allow_deferred=allow_deferred)
    if errors:
        raise ValueError("; ".join(errors))


def theta_from_genome(genome: dict[str, Any], tag: str, seed: int) -> dict[str, Any]:
    genome = normalize_genome(genome)
    assert_valid_genome(genome, allow_deferred=False)
    kind, _, _ = feature_bin(genome)
    params = dict(BASE_PX4_PARAMS)
    physical = {key: round(value, 8) for key, value in physical_params(genome).items()}
    params.update(physical)
    boot_params = dict(BASE_BOOT_PARAMS)
    boot_params.update(physical)
    theta = base_theta(tag, seed, boot_params, params, genome)

    if kind == "switching":
        configure_switching_theta(theta, genome)
    elif kind == "step":
        configure_step_theta(theta, genome)
    else:
        configure_steady_theta(theta, genome)

    theta["theta_genome"] = {
        "generator": "scripts/theta_genome.py",
        "genome": genome,
        "map_elites": feature_metadata(genome),
        "state_contam_status": "DEFERRED - pending m2b_state_shim.patch drift",
        "excluded": {
            "c_tier_setpoint_amplitude_attack": "excluded by design; step axis is moderate P5 settling stimulus only",
            "motor_or_sensor_faults": "deferred to Gazebo route after SIH support boundary is verified",
        },
    }
    return theta


def base_theta(
    tag: str,
    seed: int,
    boot_params: dict[str, Any],
    px4_params: dict[str, Any],
    genome: dict[str, Any],
) -> dict[str, Any]:
    wind_n, wind_e = wind_components(genome)
    return {
        "tag": tag,
        "description": "Tier 0.5 property-oracle theta generated from scripts/theta_genome.py.",
        "seed": int(seed),
        "airframe": {"sim": "sih", "model": "sihsim_x500_v2", "sys_autostart": 10046},
        "timing": {
            "approach_start_s": 14.0,
            "controller_switch_s": 24.0,
            "trajectory_start_s": 31.0,
            "mission_end_s": round(float(genome["mission_end_s"]), 3),
            "mode_command_repeat_s": 0.5,
            "mode_command_timeout_s": 8.0,
            "px4_shutdown_margin_s": 8.0,
            "px4_shutdown_wall_slack_s": 22.0,
            "external_mode_id": 23,
        },
        "setpoint": {
            "rate_hz": float(genome["setpoint_rate_hz"]),
            "max_wall_timer_hz": 800.0,
            "hover_ned": [0.0, 0.0, -2.5],
            "yaw_rad": 0.0,
            "type": "step",
            "step": {"delta_ned": [0.0, 0.0, 0.0]},
        },
        "boot_px4_params": boot_params,
        "px4_params": px4_params,
        "environment": {
            "uses_state_shim": False,
            "sih_wind_n": round(wind_n, 4),
            "sih_wind_e": round(wind_e, 4),
            "mass_scale": round(float(genome["mass_scale"]), 4),
            "inertia_roll_scale": round(float(genome["inertia_roll_scale"]), 4),
            "inertia_pitch_scale": round(float(genome["inertia_pitch_scale"]), 4),
            "inertia_yaw_scale": round(float(genome["inertia_yaw_scale"]), 4),
            "twr_scale": round(float(genome["twr_scale"]), 4),
            "thrust_to_weight_ratio": round(NOMINAL_TWR * float(genome["twr_scale"]), 4),
            "route": "SIH/headless/lockstep",
        },
        "faults": [],
        "sensor_perturbations": [],
        "safe_thresholds": {
            "tracking_error_max_m": 8.0,
            "tracking_error_rms_m": 4.0,
            "final_error_m": 3.0,
            "roll_pitch_max_deg": 75.0,
            "angular_rate_max_rad_s": 8.0,
            "motor_saturation_ratio_max": 0.85,
            "min_altitude_agl_m": 0.25,
        },
        "divergence_thresholds": {"position_divergence_m": 2.0},
    }


def configure_steady_theta(theta: dict[str, Any], genome: dict[str, Any]) -> None:
    theta["description"] += " Steady hover under wind and/or physics mismatch."
    theta["timing"]["trajectory_start_s"] = 31.0
    theta["setpoint"]["type"] = "step"
    theta["setpoint"]["step"] = {"delta_ned": [0.0, 0.0, 0.0], "start_s": 31.0}
    theta["environment"]["steady_property_focus"] = ["P4", "P6", "P7"]
    if genome.get("disturbance_type") == COMBINED_STEADY_DISTURBANCE_TYPE:
        severities = genome_severity(genome)
        theta["environment"]["steady_combo"] = {
            "combined_wind_and_physics": True,
            "wind_speed_m_s": round(float(genome["wind_speed_m_s"]), 4),
            "wind_direction_rad": round(float(genome["wind_direction_rad"]), 6),
            "physics_severity": round(severities["physics_mismatch"], 6),
            "wind_severity": round(severities["wind"], 6),
        }


def configure_step_theta(theta: dict[str, Any], genome: dict[str, Any]) -> None:
    step_time = round(float(genome["step_time_s"]), 3)
    theta["description"] += " Pure moderate setpoint step for P5 settling."
    theta["timing"]["trajectory_start_s"] = step_time
    theta["timing"]["mission_end_s"] = round(float(genome["mission_end_s"]), 3)
    theta["setpoint"]["type"] = "step"
    theta["setpoint"]["step"] = {
        "delta_ned": active_step_delta(genome),
        "start_s": step_time,
    }
    theta["environment"]["step_stimulus"] = {
        "axis": genome["step_axis"],
        "sign": genome["step_sign"],
        "magnitude_m": round(float(genome["step_magnitude_m"]), 4),
        "normal_operation_not_c_tier_attack": True,
        "settling_window_s": SETTLING_WINDOW_S,
    }


def configure_switching_theta(theta: dict[str, Any], genome: dict[str, Any]) -> None:
    target = float(genome["switch_roll_pitch_deg"])
    rate = float(genome["switch_rate_rad_s"])
    theta["description"] += " Circle approach with Method-A groundtruth-triggered controller handoff."
    theta["timing"].update(
        {
            "approach_start_s": 12.0,
            "controller_switch_s": 54.0,
            "trajectory_start_s": 16.0,
            "mission_end_s": 68.0,
        }
    )
    theta["setpoint"].update(
        {
            "rate_hz": float(genome["setpoint_rate_hz"]),
            "type": "circle",
            "feedforward": True,
            "circle": {
                "radius_m": round(float(genome["approach_radius_m"]), 4),
                "frequency_hz": round(float(genome["approach_frequency_hz"]), 4),
                "phase_rad": round(float(genome["approach_phase_rad"]), 6),
                "z_amplitude_m": 0.0,
            },
            "activation_trigger": {
                "enabled": True,
                "method": "SIH groundtruth threshold crossing",
                "start_s": 18.0,
                "deadline_s": 54.0,
                "roll_pitch_abs_min_deg": round(max(0.0, target - 4.0), 4),
                "roll_pitch_abs_max_deg": round(target + 4.0, 4),
                "angular_rate_norm_min_rad_s": round(max(0.0, rate - 0.35), 4),
                "angular_rate_norm_max_rad_s": round(rate + 0.35, 4),
                "switch_delay_s": round(float(genome["switch_delay_s"]), 4),
                "max_topic_age_s": 0.25,
            },
            "post_switch": {
                "type": "hover",
                "hover_ned": [0.0, 0.0, -2.5],
            },
        }
    )
    theta["environment"]["switching"] = {
        "expected_tilt_deg": round(expected_circle_tilt_deg(genome), 4),
        "reachability": "trigger window is cross-constrained to the selected circle approach",
    }


def spec_table_rows() -> list[dict[str, Any]]:
    return [spec.as_dict() for spec in VARIABLE_SPECS]


def spec_markdown_table() -> str:
    lines = [
        "| variable | kind | bounds / choices | simulator + injection | route status |",
        "|---|---|---|---|---|",
    ]
    for spec in VARIABLE_SPECS:
        if spec.bounds is not None:
            domain = f"[{spec.bounds[0]}, {spec.bounds[1]}]"
        else:
            domain = ", ".join(str(item) for item in spec.choices or ())
        lines.append(
            "| "
            + " | ".join(
                [
                    spec.name,
                    spec.kind,
                    domain,
                    f"{spec.simulator}; {spec.injection}",
                    spec.route_status,
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def self_test(count: int, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    generated = [random_genome(rng) for _ in range(count)]
    mutated = [mutate_genome(genome, rng) for genome in generated]
    crossed = [crossover_genome(a, b, rng) for a, b in zip(generated, reversed(mutated))]
    all_genomes = generated + mutated + crossed
    bins: dict[str, int] = {}
    for idx, genome in enumerate(all_genomes):
        assert_valid_genome(genome)
        theta = theta_from_genome(genome, tag=f"theta_genome_selftest_{idx}", seed=seed + idx)
        if theta["theta_genome"]["map_elites"]["disturbance_type"] == "step":
            step = theta["setpoint"]["step"]["delta_ned"]
            if math.sqrt(sum(float(value) * float(value) for value in step)) < 0.5:
                raise AssertionError("step theta did not carry a P5-sized command step")
        bin_name = ":".join(feature_bin(genome)[:2])
        bins[bin_name] = bins.get(bin_name, 0) + 1
    return {
        "seed": seed,
        "count": count,
        "generated": len(generated),
        "mutated": len(mutated),
        "crossed": len(crossed),
        "validated": len(all_genomes),
        "feature_bins": bins,
        "deferred_state_contam": "excluded from default generation pending m2b shim patch drift",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260626)
    parser.add_argument("--dump-spec", action="store_true")
    parser.add_argument("--sample-theta", type=Path)
    args = parser.parse_args()

    if args.dump_spec:
        print(spec_markdown_table())
    if args.self_test:
        print(json.dumps(self_test(args.self_test, args.seed), indent=2, sort_keys=True, allow_nan=False))
    if args.sample_theta:
        rng = random.Random(args.seed)
        theta = theta_from_genome(random_genome(rng), tag="theta_genome_sample", seed=args.seed)
        args.sample_theta.parent.mkdir(parents=True, exist_ok=True)
        with args.sample_theta.open("w", encoding="utf-8") as handle:
            json.dump(theta, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
