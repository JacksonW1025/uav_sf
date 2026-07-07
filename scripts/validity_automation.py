#!/usr/bin/env python3
"""Validity gates shared by property evaluation and M2 search.

This module centralizes the three campaign hygiene rules that must be applied
fail-loud: symmetric infrastructure decontamination, mc_nn identity checking,
and rho jitter margins for reproduced findings.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


NAV_STATE_NAMES = {
    0: "MANUAL",
    1: "ALTCTL",
    2: "POSCTL",
    3: "AUTO_MISSION",
    4: "AUTO_LOITER",
    5: "AUTO_RTL",
    12: "DESCEND",
    13: "TERMINATION",
    14: "OFFBOARD",
    18: "AUTO_LAND",
    23: "EXTERNAL1",
}
TARGET_NAV = {"classical": 14, "mcnn": 23, "mc_nn": 23, "raptor": 23}
RTL_LAND_NAV_STATES = {5, 12, 18}

INFRASTRUCTURE_TRIGGER_FIELDS = {
    "offboard_control_signal_lost": "offboard proof-of-life/signal loss",
    "manual_control_signal_lost": "RC/manual-control link loss",
    "gcs_connection_lost": "GCS/datalink loss",
    "high_latency_data_link_lost": "high-latency datalink loss",
    "local_position_invalid": "estimator local-position invalid",
    "local_position_invalid_relaxed": "estimator local-position relaxed invalid",
    "local_velocity_invalid": "estimator local-velocity invalid",
    "local_altitude_invalid": "estimator local-altitude invalid",
    "global_position_invalid": "estimator global-position invalid",
    "global_position_invalid_relaxed": "estimator global-position relaxed invalid",
    "gnss_lost": "GNSS loss",
}

TERMINAL_CAUSAL_WINDOW_S = 1.0
MIN_RECOVERY_HEIGHT_M = 1.0

DEFAULT_RHO_JITTER_BANDS: dict[str, float] = {
    # Fixed theta serial pairwise ranges from docs/parallel_profile_20260626.
    # P7 uses max(classical=0.2242437213, mcnn=0.1979852921), matching the
    # documented approximately 0.2 intrinsic P7 jitter.
    "P1": 0.0127931677,
    "P2": 0.0935180205,
    "P3": 0.0,
    "P4": 0.0142966629,
    "P5": 0.2834851297,
    "P6": 0.0136974981,
    "P7": 0.2242437213,
}
DEFAULT_JITTER_MARGIN_FACTOR = 2.0
DEFAULT_MIN_REPRO_MARGIN = 0.02


class ValidityGateError(RuntimeError):
    """Raised when an eval must be excluded rather than silently scored."""


def finite_float(value: Any) -> float | None:
    if not isinstance(value, (int, float, np.floating)):
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def first_dataset(ulog: Any, name: str) -> Any | None:
    matches = [dataset for dataset in getattr(ulog, "data_list", []) if dataset.name == name]
    return matches[0] if matches else None


def first_true(dataset: Any, field: str, start_us: int, end_us: int | None = None) -> int | None:
    if dataset is None or field not in dataset.data:
        return None
    ts = dataset.data["timestamp"].astype(np.int64)
    values = dataset.data[field].astype(bool)
    mask = ts >= start_us
    if end_us is not None:
        mask &= ts <= end_us
    idx = np.where(mask & values)[0]
    if len(idx) == 0:
        return None
    return int(ts[int(idx[0])])


def first_nav_exit(dataset: Any, target_nav: int, start_us: int, end_us: int | None = None) -> dict[str, Any] | None:
    if dataset is None or "nav_state" not in dataset.data:
        return None
    ts = dataset.data["timestamp"].astype(np.int64)
    nav = dataset.data["nav_state"].astype(int)
    mask = ts >= start_us
    if end_us is not None:
        mask &= ts <= end_us
    idx = np.where(mask & (nav != target_nav))[0]
    if len(idx) == 0:
        return None
    at = int(ts[int(idx[0])])
    state = int(nav[int(idx[0])])
    return {"timestamp_us": at, "nav_state": state, "nav_state_name": NAV_STATE_NAMES.get(state, str(state))}


def bool_fields_true_near(dataset: Any, timestamp_us: int | None, window_s: float = TERMINAL_CAUSAL_WINDOW_S) -> list[str]:
    if dataset is None or timestamp_us is None:
        return []
    ts = dataset.data["timestamp"].astype(np.int64)
    mask = (ts >= timestamp_us - int(0.25 * 1e6)) & (ts <= timestamp_us + int(window_s * 1e6))
    if not np.any(mask):
        return []
    fields: list[str] = []
    for field, values in dataset.data.items():
        if field.startswith("timestamp"):
            continue
        arr = np.asarray(values)
        if arr.dtype != np.bool_ and not np.all(np.isin(arr[mask], [0, 1, False, True])):
            continue
        if bool(np.any(arr[mask].astype(bool))):
            fields.append(field)
    return sorted(fields)


def first_true_fields(dataset: Any, start_us: int, end_us: int | None = None) -> dict[str, float]:
    if dataset is None:
        return {}
    out: dict[str, float] = {}
    for field, values in dataset.data.items():
        if field.startswith("timestamp"):
            continue
        arr = np.asarray(values)
        if arr.dtype != np.bool_ and not np.all(np.isin(arr, [0, 1, False, True])):
            continue
        at = first_true(dataset, field, start_us, end_us)
        if at is not None:
            out[field] = round((at - start_us) / 1e6, 6)
    return out


def _infra_causes_near(flags: Any, event_us: int | None, start_us: int) -> tuple[list[str], list[str]]:
    active = bool_fields_true_near(flags, event_us)
    causes: list[str] = []
    if event_us is None:
        return causes, active
    for field, reason in INFRASTRUCTURE_TRIGGER_FIELDS.items():
        first_at = first_true(flags, field, start_us, event_us + int(TERMINAL_CAUSAL_WINDOW_S * 1e6))
        if first_at is None:
            continue
        near_event = abs(first_at - event_us) <= int(TERMINAL_CAUSAL_WINDOW_S * 1e6)
        if field in active and near_event:
            causes.append(f"{field}: {reason}")
    return causes, active


def terminal_classification(ulog: Any, start_us: int, mission_end_us: int, target_nav: int) -> dict[str, Any]:
    status = first_dataset(ulog, "vehicle_status")
    flags = first_dataset(ulog, "failsafe_flags")
    land = first_dataset(ulog, "vehicle_land_detected")

    first_failsafe_us = first_true(status, "failsafe", start_us, mission_end_us)
    first_ground_contact_us = first_true(land, "ground_contact", start_us, mission_end_us)
    first_landed_us = first_true(land, "landed", start_us, mission_end_us)
    nav_exit = first_nav_exit(status, target_nav, start_us, mission_end_us)

    failsafe_causes, active_at_failsafe = _infra_causes_near(flags, first_failsafe_us, start_us)
    nav_event_us = nav_exit["timestamp_us"] if nav_exit is not None else None
    nav_causes, active_at_nav_exit = _infra_causes_near(flags, nav_event_us, start_us)

    terminal_class = "NONE"
    terminal_event_us = None
    terminal_reasons: list[str] = []
    if first_failsafe_us is not None and failsafe_causes:
        terminal_class = "INFRASTRUCTURE"
        terminal_event_us = int(first_failsafe_us)
        terminal_reasons.extend(failsafe_causes)
    elif (
        nav_exit is not None
        and int(nav_exit["nav_state"]) in RTL_LAND_NAV_STATES
        and (nav_causes or (first_failsafe_us is not None and abs(int(nav_event_us) - first_failsafe_us) <= int(1e6)))
    ):
        terminal_class = "INFRASTRUCTURE"
        terminal_event_us = int(nav_event_us)
        terminal_reasons.extend(nav_causes)
        terminal_reasons.append(f"nav_exit_to_{nav_exit['nav_state_name']}_rtl_land_path")
    elif first_failsafe_us is not None:
        terminal_class = "UNRESOLVED"
        terminal_event_us = int(first_failsafe_us)
        terminal_reasons.append("vehicle_status.failsafe without a classified near-edge failsafe_flags cause")

    if first_ground_contact_us is not None and terminal_class == "INFRASTRUCTURE" and terminal_event_us is not None:
        if first_ground_contact_us >= terminal_event_us:
            terminal_reasons.append("ground_contact_after_infrastructure_terminal")

    return {
        "terminal_class": terminal_class,
        "terminal_event_us": terminal_event_us,
        "terminal_reasons": sorted(set(terminal_reasons)),
        "first_failsafe_us": first_failsafe_us,
        "first_ground_contact_us": first_ground_contact_us,
        "first_landed_us": first_landed_us,
        "first_nav_exit": nav_exit,
        "active_failsafe_flags_at_first_failsafe": active_at_failsafe,
        "active_failsafe_flags_at_nav_exit": active_at_nav_exit,
        "first_true_failsafe_flags_dt_s": first_true_fields(flags, start_us, mission_end_us),
    }


def start_agl_m(ulog: Any, start_us: int, max_dt_s: float = 0.5) -> float | None:
    lpos = first_dataset(ulog, "vehicle_local_position_groundtruth") or first_dataset(ulog, "vehicle_local_position")
    if lpos is None or "z" not in lpos.data:
        return None
    ts = lpos.data["timestamp"].astype(np.int64)
    if len(ts) == 0:
        return None
    idx = int(np.argmin(np.abs(ts - int(start_us))))
    if abs(int(ts[idx]) - int(start_us)) > int(max_dt_s * 1e6):
        return None
    return finite_float(-float(lpos.data["z"][idx]))


def decontaminated_control_window(
    ulog: Any,
    start_us: int,
    mission_end_us: int,
    *,
    controller: str | None = None,
    target_nav: int | None = None,
    min_recovery_height_m: float = MIN_RECOVERY_HEIGHT_M,
) -> dict[str, Any]:
    if target_nav is None:
        if controller not in TARGET_NAV:
            raise ValueError(f"unknown controller for target nav: {controller!r}")
        target_nav = TARGET_NAV[str(controller)]
    terminal = terminal_classification(ulog, int(start_us), int(mission_end_us), int(target_nav))
    control_end_us = int(mission_end_us)
    if terminal["terminal_class"] == "INFRASTRUCTURE" and terminal["terminal_event_us"] is not None:
        control_end_us = min(control_end_us, int(terminal["terminal_event_us"]))
    control_end_us = max(int(start_us), control_end_us)

    agl = start_agl_m(ulog, int(start_us))
    invalid_reasons: list[str] = []
    if agl is not None and agl < min_recovery_height_m:
        invalid_reasons.append("start_below_min_recovery_height")
    if terminal["terminal_class"] == "UNRESOLVED":
        invalid_reasons.append("unresolved_failsafe_terminal")

    return {
        "analysis_start_us": int(start_us),
        "analysis_end_us": int(mission_end_us),
        "control_end_us": int(control_end_us),
        "control_duration_s": (int(control_end_us) - int(start_us)) / 1e6,
        "target_nav_state": int(target_nav),
        "target_nav_state_name": NAV_STATE_NAMES.get(int(target_nav), str(target_nav)),
        "terminal": terminal,
        "cut_at_infrastructure_terminal": terminal["terminal_class"] == "INFRASTRUCTURE",
        "start_agl_m": agl,
        "min_recovery_height_m": float(min_recovery_height_m),
        "invalid_reasons": invalid_reasons,
        "valid": not invalid_reasons,
    }


def decontamination_gate(window: dict[str, Any]) -> dict[str, Any]:
    if not window or "valid" not in window:
        return {
            "passed": False,
            "reasons": ["missing_decontamination_record"],
            "terminal_class": None,
            "cut_at_infrastructure_terminal": False,
            "control_duration_s": None,
            "start_agl_m": None,
            "min_recovery_height_m": MIN_RECOVERY_HEIGHT_M,
        }
    reasons = list(window.get("invalid_reasons") or [])
    return {
        "passed": not reasons,
        "reasons": reasons,
        "terminal_class": window.get("terminal", {}).get("terminal_class"),
        "cut_at_infrastructure_terminal": bool(window.get("cut_at_infrastructure_terminal")),
        "control_duration_s": window.get("control_duration_s"),
        "start_agl_m": window.get("start_agl_m"),
        "min_recovery_height_m": window.get("min_recovery_height_m"),
    }


def mcnn_identity_gate(
    identity: dict[str, Any],
    *,
    min_rate_hz: float = 200.0,
    max_rate_hz: float = 280.0,
    min_exact_equal_count: int = 1000,
    min_exact_match_fraction: float = 0.80,
) -> dict[str, Any]:
    reasons: list[str] = []
    if identity.get("controller") != "mcnn":
        reasons.append("identity_controller_not_mcnn")
    if bool(identity.get("raptor_input_present")):
        reasons.append("raptor_input_present")
    samples = identity.get("neural_control_samples")
    if not isinstance(samples, int) or samples <= 100:
        reasons.append("insufficient_neural_control_samples")
    rate = finite_float(identity.get("neural_control_rate_hz"))
    if rate is None or rate < min_rate_hz or rate > max_rate_hz:
        reasons.append("neural_control_rate_outside_expected_mode23_band")
    exact_equal_count = identity.get("network_output_actuator_exact_equal_count")
    if not isinstance(exact_equal_count, int) or exact_equal_count < min_exact_equal_count:
        reasons.append("network_output_not_actuator_motors")
    exact_fraction = finite_float(identity.get("network_output_actuator_exact_match_fraction"))
    if exact_fraction is None or exact_fraction < min_exact_match_fraction:
        reasons.append("network_output_actuator_match_fraction_low")
    p99 = finite_float(identity.get("network_output_actuator_p99_abs_diff"))
    return {
        "passed": not reasons,
        "reasons": reasons,
        "criteria": {
            "min_rate_hz": min_rate_hz,
            "max_rate_hz": max_rate_hz,
            "min_exact_equal_count": min_exact_equal_count,
            "min_exact_match_fraction": min_exact_match_fraction,
            "raptor_input_absent_required": True,
        },
        "evidence": {
            "neural_control_samples": samples,
            "neural_control_rate_hz": rate,
            "raptor_input_present": identity.get("raptor_input_present"),
            "network_output_actuator_exact_equal_count": exact_equal_count,
            "network_output_actuator_exact_match_fraction": exact_fraction,
            "network_output_actuator_p99_abs_diff": p99,
        },
    }


def raptor_identity_gate(
    identity: dict[str, Any],
    *,
    min_active_samples: int = 100,
    min_input_samples: int = 100,
    require_policy_staged: bool = True,
) -> dict[str, Any]:
    reasons: list[str] = []
    if identity.get("controller") != "raptor":
        reasons.append("identity_controller_not_raptor")
    if not bool(identity.get("raptor_status_present")):
        reasons.append("missing_raptor_status_topic")
    status_active = identity.get("raptor_status_active_samples")
    if not isinstance(status_active, int) or status_active < min_active_samples:
        reasons.append("insufficient_raptor_status_active_samples")
    if not bool(identity.get("raptor_input_present")):
        reasons.append("missing_raptor_input_topic")
    input_samples = identity.get("raptor_input_samples")
    if not isinstance(input_samples, int) or input_samples < min_input_samples:
        reasons.append("insufficient_raptor_input_samples")
    input_active = identity.get("raptor_input_active_samples")
    if not isinstance(input_active, int) or input_active < min_input_samples:
        reasons.append("insufficient_raptor_input_active_samples")
    target_nav = identity.get("target_nav_state")
    if target_nav != TARGET_NAV["raptor"]:
        reasons.append("target_nav_state_not_external1")
    target_nav_samples = identity.get("target_nav_state_samples")
    if not isinstance(target_nav_samples, int) or target_nav_samples <= 0:
        reasons.append("missing_target_nav_state_samples")
    target_nav_fraction = finite_float(identity.get("target_nav_state_fraction"))
    if bool(identity.get("neural_control_present")):
        reasons.append("neural_control_present")
    if require_policy_staged and identity.get("policy_tar_staged") is not True:
        reasons.append("policy_tar_not_staged")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "criteria": {
            "min_active_samples": min_active_samples,
            "min_input_samples": min_input_samples,
            "target_nav_fraction": "diagnostic_only_window_may_include_pre_switch_offboard",
            "target_nav_state": TARGET_NAV["raptor"],
            "neural_control_absent_required": True,
            "policy_tar_staged_required": require_policy_staged,
        },
        "evidence": {
            "raptor_status_present": identity.get("raptor_status_present"),
            "raptor_status_active_samples": status_active,
            "raptor_input_present": identity.get("raptor_input_present"),
            "raptor_input_samples": input_samples,
            "raptor_input_active_samples": input_active,
            "target_nav_state": target_nav,
            "target_nav_state_samples": target_nav_samples,
            "target_nav_state_fraction": target_nav_fraction,
            "neural_control_present": identity.get("neural_control_present"),
            "policy_tar_staged": identity.get("policy_tar_staged"),
        },
    }


def assert_mcnn_identity(identity: dict[str, Any]) -> dict[str, Any]:
    gate = mcnn_identity_gate(identity)
    if not gate["passed"]:
        raise ValidityGateError("mcnn_identity_gate_failed: " + ",".join(gate["reasons"]))
    return gate


def assert_raptor_identity(identity: dict[str, Any]) -> dict[str, Any]:
    gate = raptor_identity_gate(identity)
    if not gate["passed"]:
        raise ValidityGateError("raptor_identity_gate_failed: " + ",".join(gate["reasons"]))
    return gate


def reproduction_margins(
    jitter_bands: dict[str, float] | None = None,
    *,
    factor: float = DEFAULT_JITTER_MARGIN_FACTOR,
    min_margin: float = DEFAULT_MIN_REPRO_MARGIN,
) -> dict[str, float]:
    bands = dict(DEFAULT_RHO_JITTER_BANDS if jitter_bands is None else jitter_bands)
    return {prop: max(float(min_margin), float(factor) * float(band)) for prop, band in bands.items()}


def robust_violation_margin(neural_rho: Any) -> float | None:
    rho = finite_float(neural_rho)
    if rho is None:
        return None
    return max(0.0, -rho)


def robust_property_finding(
    classical_rho: Any,
    neural_rho: Any,
    classical_margin: float,
    reproduction_margin: float,
    *,
    vacuous: bool = False,
) -> bool:
    c = finite_float(classical_rho)
    n = finite_float(neural_rho)
    if c is None or n is None or vacuous:
        return False
    return bool(c >= float(classical_margin) and n <= -float(reproduction_margin))
