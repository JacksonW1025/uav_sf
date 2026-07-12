#!/usr/bin/env python3
"""Yaw-rotation transform helpers for the route-A equivariance probe."""

from __future__ import annotations

import copy
import math
from typing import Any


TAU = 2.0 * math.pi
EPS = 1e-12


def wrap_2pi(value: float) -> float:
    return float(value) % TAU


def _round(value: float | None, digits: int = 9) -> float | None:
    if value is None:
        return None
    value = 0.0 if abs(float(value)) < 10 ** (-(digits + 1)) else float(value)
    return round(value, digits)


def _circle(theta: dict[str, Any]) -> dict[str, Any]:
    setpoint = theta.get("setpoint", {})
    if not isinstance(setpoint, dict):
        return {}
    circle = setpoint.get("circle", {})
    return circle if isinstance(circle, dict) else {}


def _genome(theta: dict[str, Any]) -> dict[str, Any] | None:
    theta_genome = theta.get("theta_genome")
    if not isinstance(theta_genome, dict):
        return None
    genome = theta_genome.get("genome")
    return genome if isinstance(genome, dict) else None


def _setpoint(theta: dict[str, Any]) -> dict[str, Any]:
    setpoint = theta.setdefault("setpoint", {})
    if not isinstance(setpoint, dict):
        raise ValueError("theta.setpoint must be an object")
    return setpoint


def _environment(theta: dict[str, Any]) -> dict[str, Any]:
    env = theta.setdefault("environment", {})
    if not isinstance(env, dict):
        raise ValueError("theta.environment must be an object")
    return env


def yaw_rad(theta: dict[str, Any]) -> float:
    setpoint = theta.get("setpoint", {})
    if isinstance(setpoint, dict):
        return wrap_2pi(float(setpoint.get("yaw_rad", 0.0)))
    return 0.0


def circle_phase_rad(theta: dict[str, Any]) -> float:
    circle = _circle(theta)
    if "phase_rad" in circle:
        return wrap_2pi(float(circle["phase_rad"]))
    env = theta.get("environment", {})
    case = env.get("case") if isinstance(env, dict) else None
    if isinstance(case, dict) and "phase_rad" in case:
        return wrap_2pi(float(case["phase_rad"]))
    genome = _genome(theta)
    if genome is not None and "approach_phase_rad" in genome:
        return wrap_2pi(float(genome["approach_phase_rad"]))
    return 0.0


def circle_bearing_rad(theta: dict[str, Any]) -> float:
    """Return the NED bearing of the circle position vector at t=0.

    `m1_offboard_task.py` encodes the circle as N=sin(phase), E=cos(phase), so
    the semantic NED bearing is pi/2 - phase. A positive yaw rotation therefore
    subtracts from the raw phase field.
    """

    return wrap_2pi((math.pi / 2.0) - circle_phase_rad(theta))


def _wind_components_from_params(theta: dict[str, Any]) -> tuple[float, float] | None:
    for key in ("boot_px4_params", "px4_params"):
        params = theta.get(key)
        if isinstance(params, dict) and ("SIH_WIND_N" in params or "SIH_WIND_E" in params):
            return float(params.get("SIH_WIND_N", 0.0)), float(params.get("SIH_WIND_E", 0.0))
    env = theta.get("environment", {})
    if isinstance(env, dict):
        if "sih_wind_n" in env or "sih_wind_e" in env:
            return float(env.get("sih_wind_n", 0.0)), float(env.get("sih_wind_e", 0.0))
        case = env.get("case")
        if isinstance(case, dict) and ("wind_n" in case or "wind_e" in case):
            return float(case.get("wind_n", 0.0)), float(case.get("wind_e", 0.0))
    return None


def wind_speed_m_s(theta: dict[str, Any]) -> float:
    components = _wind_components_from_params(theta)
    if components is not None:
        return math.hypot(components[0], components[1])
    genome = _genome(theta)
    if genome is not None:
        return float(genome.get("wind_speed_m_s", 0.0))
    return 0.0


def wind_bearing_rad(theta: dict[str, Any]) -> float:
    components = _wind_components_from_params(theta)
    if components is not None and math.hypot(components[0], components[1]) > EPS:
        return wrap_2pi(math.atan2(components[1], components[0]))
    genome = _genome(theta)
    if genome is not None and "wind_direction_rad" in genome:
        return wrap_2pi(float(genome["wind_direction_rad"]))
    return 0.0


def _body_ne_vector(north: float, east: float, yaw: float) -> tuple[float, float]:
    return (
        math.cos(yaw) * north + math.sin(yaw) * east,
        -math.sin(yaw) * north + math.cos(yaw) * east,
    )


def _circle_body_samples(theta: dict[str, Any], sample_times_s: tuple[float, ...]) -> list[dict[str, Any]]:
    circle = _circle(theta)
    radius = float(circle.get("radius_m", 0.0))
    frequency = float(circle.get("frequency_hz", 0.0))
    phase = circle_phase_rad(theta)
    yaw = yaw_rad(theta)
    omega = TAU * frequency
    samples: list[dict[str, Any]] = []
    for t in sample_times_s:
        omega_t = omega * float(t) + phase
        pos = (radius * math.sin(omega_t), radius * math.cos(omega_t))
        vel = (radius * omega * math.cos(omega_t), -radius * omega * math.sin(omega_t))
        acc = (-radius * omega * omega * math.sin(omega_t), -radius * omega * omega * math.cos(omega_t))
        body_pos = _body_ne_vector(pos[0], pos[1], yaw)
        body_vel = _body_ne_vector(vel[0], vel[1], yaw)
        body_acc = _body_ne_vector(acc[0], acc[1], yaw)
        samples.append(
            {
                "t_s": _round(float(t), 6),
                "pos_body_ne_m": [_round(body_pos[0]), _round(body_pos[1])],
                "vel_body_ne_m_s": [_round(body_vel[0]), _round(body_vel[1])],
                "acc_body_ne_m_s2": [_round(body_acc[0]), _round(body_acc[1])],
            }
        )
    return samples


def body_frame_maneuver_signature(
    theta: dict[str, Any],
    *,
    sample_times_s: tuple[float, ...] = (0.0, 0.25, 0.5, 1.0),
) -> dict[str, Any]:
    speed = wind_speed_m_s(theta)
    wind_body_bearing = None
    if speed > EPS:
        wind_body_bearing = wrap_2pi(wind_bearing_rad(theta) - yaw_rad(theta))
    return {
        "body_circle_bearing_rad": _round(wrap_2pi(circle_bearing_rad(theta) - yaw_rad(theta))),
        "body_circle_samples": _circle_body_samples(theta, sample_times_s),
        "body_wind_speed_m_s": _round(speed),
        "body_wind_bearing_rad": _round(wind_body_bearing),
    }


def _set_circle_phase(theta: dict[str, Any], phase_rad: float) -> None:
    phase = wrap_2pi(phase_rad)
    setpoint = _setpoint(theta)
    circle = setpoint.get("circle")
    if isinstance(circle, dict):
        circle["phase_rad"] = phase
    genome = _genome(theta)
    if genome is not None and "approach_phase_rad" in genome:
        genome["approach_phase_rad"] = phase
    env = theta.get("environment", {})
    if isinstance(env, dict):
        case = env.get("case")
        if isinstance(case, dict) and "phase_rad" in case:
            case["phase_rad"] = phase


def _set_wind(theta: dict[str, Any], speed: float, direction: float) -> None:
    speed = max(0.0, float(speed))
    direction = wrap_2pi(direction)
    wind_n = speed * math.cos(direction)
    wind_e = speed * math.sin(direction)

    genome = _genome(theta)
    if genome is not None:
        if "wind_speed_m_s" in genome:
            genome["wind_speed_m_s"] = speed
        if "wind_direction_rad" in genome:
            genome["wind_direction_rad"] = direction

    for key in ("boot_px4_params", "px4_params"):
        params = theta.get(key)
        if isinstance(params, dict) and ("SIH_WIND_N" in params or "SIH_WIND_E" in params):
            params["SIH_WIND_N"] = wind_n
            params["SIH_WIND_E"] = wind_e

    env = theta.get("environment", {})
    if isinstance(env, dict):
        if "sih_wind_n" in env or "sih_wind_e" in env:
            env["sih_wind_n"] = wind_n
            env["sih_wind_e"] = wind_e
        case = env.get("case")
        if isinstance(case, dict) and ("wind_n" in case or "wind_e" in case):
            case["wind_n"] = wind_n
            case["wind_e"] = wind_e


def apply_yaw_rotation(theta: dict[str, Any], psi: float) -> dict[str, Any]:
    """Return a deep-copied theta rotated by a world-z yaw angle.

    The executable commanded yaw and wind bearing add `psi`. The route-A circle
    semantic bearing also adds `psi`; because the raw circle phase uses
    N=sin(phase), E=cos(phase), that means the raw phase field subtracts `psi`.
    """

    out = copy.deepcopy(theta)
    psi = float(psi)
    setpoint = _setpoint(out)
    setpoint["yaw_rad"] = wrap_2pi(float(setpoint.get("yaw_rad", 0.0)) + psi)
    _set_circle_phase(out, circle_phase_rad(theta) - psi)
    _set_wind(out, wind_speed_m_s(theta), wind_bearing_rad(theta) + psi)
    _environment(out).setdefault("yaw_equivariance", {}).update(
        {
            "rotation_psi_rad": wrap_2pi(psi),
            "rotation_psi_deg": math.degrees(wrap_2pi(psi)),
            "circle_phase_convention": "m1_offboard_task N=sin(phase), E=cos(phase); raw phase subtracts psi",
        }
    )
    return out


def zero_wind(theta: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(theta)
    _set_wind(out, 0.0, wind_bearing_rad(theta))
    env = _environment(out)
    env.setdefault("yaw_equivariance", {})["wind_zero_applied"] = True
    map_elites = out.get("theta_genome", {}).get("map_elites") if isinstance(out.get("theta_genome"), dict) else None
    if isinstance(map_elites, dict):
        if "wind_speed_m_s" in map_elites:
            map_elites["wind_speed_m_s"] = 0.0
        if "wind_bucket" in map_elites:
            map_elites["wind_bucket"] = "wind_0"
    return out
