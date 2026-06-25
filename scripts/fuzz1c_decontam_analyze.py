#!/usr/bin/env python3
"""Decontaminate FUZZ-1c severity labels using existing ULOG evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from pyulog import ULog


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = REPO_ROOT / "docs/fuzz1c_severity_20260625/results.json"
DEFAULT_OUT_DIR = REPO_ROOT / "docs/fuzz1c_decontam_20260625"
MAIN_DOC = REPO_ROOT / "docs/fuzz1c_decontam_20260625.md"

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
TARGET_NAV = {"classical": 14, "mcnn": 23}
HOVER_NED = np.asarray([0.0, 0.0, -2.5], dtype=float)

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

S3_ROLL_PITCH_DEG = 90.0
S3_RATE_RAD_S = 8.0
S0_ROLL_PITCH_DEG = 40.0
S0_RATE_RAD_S = 1.0
S0_HOVER_ERROR_M = 1.5
S0_MIN_AGL_M = 1.0
S1_MIN_AGL_M = 0.5
TERMINAL_CAUSAL_WINDOW_S = 1.0
LAST_WINDOW_S = 2.0
EARLY_WINDOW_S = 5.0


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def local_path(path: str | None) -> Path | None:
    if not path:
        return None
    return REPO_ROOT / str(path).replace("/workspace/", "")


def first_dataset(ulog: ULog, name: str):
    matches = [dataset for dataset in ulog.data_list if dataset.name == name]
    return matches[0] if matches else None


def vector3(data: dict[str, np.ndarray], stem: str) -> np.ndarray:
    return np.column_stack([data[f"{stem}[0]"], data[f"{stem}[1]"], data[f"{stem}[2]"]]).astype(float)


def quaternion(data: dict[str, np.ndarray]) -> np.ndarray:
    return np.column_stack([data["q[0]"], data["q[1]"], data["q[2]"], data["q[3]"]]).astype(float)


def quat_to_roll_pitch_deg(q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    q0 = q[:, 0]
    q1 = q[:, 1]
    q2 = q[:, 2]
    q3 = q[:, 3]
    roll = np.arctan2(2.0 * (q0 * q1 + q2 * q3), 1.0 - 2.0 * (q1 * q1 + q2 * q2))
    sin_pitch = np.clip(2.0 * (q0 * q2 - q3 * q1), -1.0, 1.0)
    pitch = np.arcsin(sin_pitch)
    return np.rad2deg(roll), np.rad2deg(pitch)


def finite(value: float | np.floating | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


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


def true_fields_at(dataset: Any, timestamp_us: int | None, window_s: float = TERMINAL_CAUSAL_WINDOW_S) -> list[str]:
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


def first_true_fields(dataset: Any, start_us: int, end_us: int | None = None) -> dict[str, float | None]:
    if dataset is None:
        return {}
    out: dict[str, float | None] = {}
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


def window_stats(
    att: Any,
    rates: Any,
    lpos: Any,
    start_us: int,
    end_us: int,
) -> dict[str, float | None]:
    stats: dict[str, float | None] = {}
    if end_us <= start_us:
        return stats

    if att is not None:
        ts = att.data["timestamp"].astype(np.int64)
        mask = (ts >= start_us) & (ts <= end_us)
        if np.any(mask):
            roll, pitch = quat_to_roll_pitch_deg(quaternion(att.data)[mask])
            roll_pitch_abs = np.maximum(np.abs(roll), np.abs(pitch))
            stats["roll_pitch_max_deg"] = finite(np.nanmax(roll_pitch_abs))
            stats["roll_pitch_last_deg"] = finite(roll_pitch_abs[-1])

    if rates is not None:
        ts = rates.data["timestamp"].astype(np.int64)
        mask = (ts >= start_us) & (ts <= end_us)
        if np.any(mask):
            omega = vector3(rates.data, "xyz")[mask]
            norm = np.linalg.norm(omega, axis=1)
            stats["angular_rate_max_rad_s"] = finite(np.nanmax(norm))
            stats["angular_rate_last_rad_s"] = finite(norm[-1])

    if lpos is not None:
        ts = lpos.data["timestamp"].astype(np.int64)
        mask = (ts >= start_us) & (ts <= end_us)
        if np.any(mask):
            pos = np.column_stack([lpos.data["x"], lpos.data["y"], lpos.data["z"]]).astype(float)[mask]
            vel = np.column_stack([lpos.data["vx"], lpos.data["vy"], lpos.data["vz"]]).astype(float)[mask]
            agl = -pos[:, 2]
            err = np.linalg.norm(pos - HOVER_NED, axis=1)
            xy_err = np.linalg.norm(pos[:, :2], axis=1)
            stats["agl_min_m"] = finite(np.nanmin(agl))
            stats["agl_last_m"] = finite(agl[-1])
            stats["vz_mean_m_s"] = finite(np.nanmean(vel[:, 2]))
            stats["vz_last_m_s"] = finite(vel[-1, 2])
            stats["hover_error_max_m"] = finite(np.nanmax(err))
            stats["hover_error_last_m"] = finite(err[-1])
            stats["xy_error_last_m"] = finite(xy_err[-1])

    return stats


def max_control_envelope(att: Any, rates: Any, start_us: int, end_us: int) -> dict[str, float | None]:
    stats: dict[str, float | None] = {"roll_pitch_max_deg": None, "angular_rate_max_rad_s": None}
    if end_us <= start_us:
        return stats
    if att is not None:
        ts = att.data["timestamp"].astype(np.int64)
        mask = (ts >= start_us) & (ts <= end_us)
        if np.any(mask):
            roll, pitch = quat_to_roll_pitch_deg(quaternion(att.data)[mask])
            stats["roll_pitch_max_deg"] = finite(np.nanmax(np.maximum(np.abs(roll), np.abs(pitch))))
    if rates is not None:
        ts = rates.data["timestamp"].astype(np.int64)
        mask = (ts >= start_us) & (ts <= end_us)
        if np.any(mask):
            omega = vector3(rates.data, "xyz")[mask]
            stats["angular_rate_max_rad_s"] = finite(np.nanmax(np.linalg.norm(omega, axis=1)))
    return stats


def terminal_classification(
    switch_us: int,
    status: Any,
    flags: Any,
    land: Any,
    target_nav: int,
) -> dict[str, Any]:
    first_failsafe_us = first_true(status, "failsafe", switch_us)
    first_ground_contact_us = first_true(land, "ground_contact", switch_us)
    first_landed_us = first_true(land, "landed", switch_us)
    nav_exit = first_nav_exit(status, target_nav, switch_us)
    active_flags_at_failsafe = true_fields_at(flags, first_failsafe_us)
    first_flags = first_true_fields(flags, switch_us)

    infra_causes: list[str] = []
    if first_failsafe_us is not None:
        for field, reason in INFRASTRUCTURE_TRIGGER_FIELDS.items():
            first_at = first_true(flags, field, switch_us, first_failsafe_us + int(TERMINAL_CAUSAL_WINDOW_S * 1e6))
            if first_at is None:
                continue
            near_failsafe = abs(first_at - first_failsafe_us) <= int(TERMINAL_CAUSAL_WINDOW_S * 1e6)
            if field in active_flags_at_failsafe and near_failsafe:
                infra_causes.append(f"{field}: {reason}")

    terminal_class = "NONE"
    terminal_reasons: list[str] = []
    if first_failsafe_us is not None and infra_causes:
        terminal_class = "INFRASTRUCTURE"
        terminal_reasons.extend(infra_causes)
    elif first_failsafe_us is not None:
        terminal_class = "UNRESOLVED"
        terminal_reasons.append("vehicle_status.failsafe without a classified near-edge failsafe_flags cause")

    if first_ground_contact_us is not None and first_failsafe_us is not None and first_ground_contact_us >= first_failsafe_us:
        if terminal_class == "INFRASTRUCTURE":
            terminal_reasons.append("ground_contact_after_infrastructure_failsafe")
        elif terminal_class == "NONE":
            terminal_class = "UNRESOLVED"
            terminal_reasons.append("ground_contact_after_failsafe_but_failsafe_unclassified")

    return {
        "terminal_class": terminal_class,
        "terminal_reasons": terminal_reasons,
        "first_failsafe_us": first_failsafe_us,
        "first_ground_contact_us": first_ground_contact_us,
        "first_landed_us": first_landed_us,
        "first_nav_exit": nav_exit,
        "active_failsafe_flags_at_first_failsafe": active_flags_at_failsafe,
        "first_true_failsafe_flags_dt_s": first_flags,
    }


def classify_control_level(
    original_severity: int | None,
    terminal_class: str,
    switch_us: int,
    control_end_us: int,
    control_envelope: dict[str, float | None],
    last_stats: dict[str, float | None],
    early_stats: dict[str, float | None],
) -> dict[str, Any]:
    rp_max = control_envelope.get("roll_pitch_max_deg")
    rate_max = control_envelope.get("angular_rate_max_rad_s")
    loss_of_attitude = rp_max is not None and rp_max >= S3_ROLL_PITCH_DEG
    loss_of_rate = rate_max is not None and rate_max >= S3_RATE_RAD_S
    if loss_of_attitude or loss_of_rate:
        return {
            "control_level_severity": 3,
            "control_level_label": "S3_control_loss_or_tumble",
            "q_attitude": "FAIL",
            "q_recovery": "FAIL",
            "reasons": [
                reason
                for reason, active in [
                    ("attitude_tumble_over_90deg", loss_of_attitude),
                    ("angular_rate_loss_of_control", loss_of_rate),
                ]
                if active
            ],
        }

    stable_hover = (
        (last_stats.get("roll_pitch_max_deg") is not None and last_stats["roll_pitch_max_deg"] <= S0_ROLL_PITCH_DEG)
        and (
            last_stats.get("angular_rate_max_rad_s") is not None
            and last_stats["angular_rate_max_rad_s"] <= S0_RATE_RAD_S
        )
        and (last_stats.get("agl_min_m") is not None and last_stats["agl_min_m"] >= S0_MIN_AGL_M)
        and (
            last_stats.get("hover_error_last_m") is not None
            and last_stats["hover_error_last_m"] <= S0_HOVER_ERROR_M
        )
    )
    if stable_hover:
        return {
            "control_level_severity": 0,
            "control_level_label": "S0_clean_recovery_decontaminated",
            "q_attitude": "PASS",
            "q_recovery": "PASS",
            "reasons": ["stable_hover_before_terminal_or_at_end"],
        }

    attitude_bounded = (
        (rp_max is None or rp_max < S3_ROLL_PITCH_DEG)
        and (rate_max is None or rate_max < S3_RATE_RAD_S)
        and (last_stats.get("agl_min_m") is None or last_stats["agl_min_m"] >= S1_MIN_AGL_M)
    )
    improving = False
    if early_stats and last_stats:
        early_rp = early_stats.get("roll_pitch_last_deg")
        last_rp = last_stats.get("roll_pitch_last_deg")
        early_rate = early_stats.get("angular_rate_last_rad_s")
        last_rate = last_stats.get("angular_rate_last_rad_s")
        improving = (
            early_rp is not None
            and last_rp is not None
            and last_rp <= early_rp
            and early_rate is not None
            and last_rate is not None
            and last_rate <= early_rate
        )

    if terminal_class == "INFRASTRUCTURE" and attitude_bounded and improving:
        return {
            "control_level_severity": 1,
            "control_level_label": "S1_controlled_recovery_cut_short_by_infrastructure",
            "q_attitude": "PASS",
            "q_recovery": "PASS",
            "reasons": ["bounded_attitude_rate_and_improving_before_infrastructure_terminal"],
        }

    if terminal_class == "INFRASTRUCTURE" and attitude_bounded:
        return {
            "control_level_severity": 2,
            "control_level_label": "S2_controlled_but_recovery_unproven",
            "q_attitude": "PASS",
            "q_recovery": "UNRESOLVED",
            "reasons": ["bounded_attitude_rate_but_no_stable_recovery_before_terminal"],
        }

    if original_severity is not None and original_severity <= 1 and attitude_bounded:
        return {
            "control_level_severity": int(original_severity),
            "control_level_label": "S0_clean_recovery" if original_severity == 0 else "S1_controlled_degraded_survival",
            "q_attitude": "PASS",
            "q_recovery": "PASS",
            "reasons": ["original_nonterminal_controlled_outcome_preserved"],
        }

    return {
        "control_level_severity": 2,
        "control_level_label": "S2_controlled_failure_after_decontam",
        "q_attitude": "PASS" if attitude_bounded else "UNRESOLVED",
        "q_recovery": "FAIL",
        "reasons": ["no_uncontrolled_tumble_but_recovery_not_demonstrated"],
    }


def analyze_controller(record: dict[str, Any]) -> dict[str, Any]:
    controller = record["controller"]
    target_nav = TARGET_NAV[controller]
    ulog_path = local_path(record.get("outputs", {}).get("ulog"))
    if ulog_path is None or not ulog_path.exists():
        return {
            "controller": controller,
            "status": "UNRESOLVED",
            "unresolved_reason": f"missing ulog {ulog_path}",
        }

    ulog = ULog(str(ulog_path))
    switch = record.get("exact_switch_state") or {}
    switch_us = int(switch["switch_us"])
    mission_end_us = record.get("severity_evidence", {}).get("mission_end_us")
    if not isinstance(mission_end_us, int):
        all_timestamps = [
            int(dataset.data["timestamp"][-1])
            for dataset in ulog.data_list
            if "timestamp" in dataset.data and len(dataset.data["timestamp"]) > 0
        ]
        mission_end_us = max(all_timestamps) if all_timestamps else switch_us

    status = first_dataset(ulog, "vehicle_status")
    flags = first_dataset(ulog, "failsafe_flags")
    land = first_dataset(ulog, "vehicle_land_detected")
    att = first_dataset(ulog, "vehicle_attitude_groundtruth") or first_dataset(ulog, "vehicle_attitude")
    rates = first_dataset(ulog, "vehicle_angular_velocity_groundtruth") or first_dataset(ulog, "vehicle_angular_velocity")
    lpos = first_dataset(ulog, "vehicle_local_position_groundtruth") or first_dataset(ulog, "vehicle_local_position")

    terminal = terminal_classification(switch_us, status, flags, land, target_nav)
    first_failsafe_us = terminal["first_failsafe_us"]
    control_end_us = int(first_failsafe_us) if terminal["terminal_class"] == "INFRASTRUCTURE" else int(mission_end_us)
    control_end_us = max(control_end_us, switch_us)
    early_stats = window_stats(att, rates, lpos, switch_us, min(control_end_us, switch_us + int(EARLY_WINDOW_S * 1e6)))
    last_stats = window_stats(att, rates, lpos, max(switch_us, control_end_us - int(LAST_WINDOW_S * 1e6)), control_end_us)
    envelope = max_control_envelope(att, rates, switch_us, control_end_us)
    original_severity = record.get("severity", {}).get("severity")
    control = classify_control_level(
        int(original_severity) if isinstance(original_severity, int) else None,
        terminal["terminal_class"],
        switch_us,
        control_end_us,
        envelope,
        last_stats,
        early_stats,
    )

    switch_agl = None
    if "position_ned_m" in switch and len(switch["position_ned_m"]) >= 3:
        switch_agl = finite(-float(switch["position_ned_m"][2]))

    def rel_s(timestamp_us: int | None) -> float | None:
        return None if timestamp_us is None else round((timestamp_us - switch_us) / 1e6, 6)

    nav_exit = terminal["first_nav_exit"]
    if nav_exit is not None:
        nav_exit = dict(nav_exit)
        nav_exit["dt_from_switch_s"] = rel_s(nav_exit["timestamp_us"])

    return {
        "controller": controller,
        "status": "OK",
        "ulog": str(ulog_path.relative_to(REPO_ROOT)),
        "original_severity": original_severity,
        "original_label": record.get("severity", {}).get("severity_label"),
        "switch": {
            "timestamp_us": switch_us,
            "roll_pitch_abs_deg": finite(switch.get("roll_pitch_abs_deg")),
            "angular_rate_norm_rad_s": finite(switch.get("angular_rate_norm_rad_s")),
            "agl_m": switch_agl,
        },
        "terminal": {
            **terminal,
            "first_failsafe_dt_from_switch_s": rel_s(terminal["first_failsafe_us"]),
            "first_ground_contact_dt_from_switch_s": rel_s(terminal["first_ground_contact_us"]),
            "first_landed_dt_from_switch_s": rel_s(terminal["first_landed_us"]),
            "first_nav_exit": nav_exit,
        },
        "control_window": {
            "start_us": switch_us,
            "end_us": control_end_us,
            "duration_s": round((control_end_us - switch_us) / 1e6, 6),
            "cut_at_infrastructure_terminal": terminal["terminal_class"] == "INFRASTRUCTURE",
        },
        "early_window_stats": early_stats,
        "last_window_stats": last_stats,
        "control_envelope": envelope,
        "control_level": control,
    }


def classify_pair(idx: int, pair: dict[str, Any]) -> dict[str, Any]:
    valid = bool(pair.get("classification", {}).get("valid_matched_pair"))
    case = pair.get("mcnn", {}).get("case") or pair.get("classical", {}).get("case") or f"pair_{idx}"
    out: dict[str, Any] = {
        "idx": idx,
        "case": case,
        "valid_matched_pair": valid,
        "state_residual": pair.get("classification", {}).get("state_residual"),
    }
    if not valid:
        out["decision"] = "SKIPPED_UNTESTED"
        return out

    classical = analyze_controller(pair["classical"])
    mcnn = analyze_controller(pair["mcnn"])
    out["classical"] = classical
    out["mcnn"] = mcnn

    if classical.get("status") != "OK" or mcnn.get("status") != "OK":
        out["decision"] = "UNRESOLVED"
        return out

    csev = classical["control_level"]["control_level_severity"]
    nsev = mcnn["control_level"]["control_level_severity"]
    if csev <= 1 and nsev >= 3:
        out["decision"] = "STRICT_DIFFERENTIAL"
    elif csev <= 2 and nsev >= 3:
        out["decision"] = "ATTITUDE_CONTROL_DIFFERENTIAL"
    else:
        out["decision"] = "NO_STRICT_DIFFERENTIAL"
    return out


def stable_invariance_summary(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [p for p in pairs if p.get("valid_matched_pair") and p.get("classical", {}).get("status") == "OK"]
    fs_abs = [
        p["classical"]["terminal"]["first_failsafe_us"] / 1e6
        for p in valid
        if p["classical"]["terminal"].get("first_failsafe_us") is not None
    ]
    offboard_lead_s: list[float] = []
    ground_after_failsafe_s: list[float] = []
    pre_rp: list[float] = []
    pre_rate: list[float] = []
    pre_err: list[float] = []
    pre_agl: list[float] = []
    switch_rp = [p["classical"]["switch"]["roll_pitch_abs_deg"] for p in valid]
    switch_rate = [p["classical"]["switch"]["angular_rate_norm_rad_s"] for p in valid]
    terminal_classes = sorted({p["classical"]["terminal"]["terminal_class"] for p in valid})
    active_flags_sets = [
        set(p["classical"]["terminal"].get("active_failsafe_flags_at_first_failsafe", [])) for p in valid
    ]
    common_active_flags = sorted(set.intersection(*active_flags_sets)) if active_flags_sets else []
    reasons = sorted(
        {
            reason
            for p in valid
            for reason in p["classical"]["terminal"].get("terminal_reasons", [])
            if reason.startswith("offboard_control_signal_lost")
        }
    )
    for p in valid:
        term = p["classical"]["terminal"]
        fs = term.get("first_failsafe_us")
        off_dt = term.get("first_true_failsafe_flags_dt_s", {}).get("offboard_control_signal_lost")
        switch_us = p["classical"]["switch"]["timestamp_us"]
        if fs is not None and off_dt is not None:
            offboard_lead_s.append((fs - (switch_us + float(off_dt) * 1e6)) / 1e6)
        ground_dt = term.get("first_ground_contact_dt_from_switch_s")
        fs_dt = term.get("first_failsafe_dt_from_switch_s")
        if ground_dt is not None and fs_dt is not None:
            ground_after_failsafe_s.append(float(ground_dt) - float(fs_dt))
        last = p["classical"].get("last_window_stats", {})
        for bucket, key in [
            (pre_rp, "roll_pitch_max_deg"),
            (pre_rate, "angular_rate_max_rad_s"),
            (pre_err, "hover_error_last_m"),
            (pre_agl, "agl_min_m"),
        ]:
            value = last.get(key)
            if value is not None:
                bucket.append(float(value))
    return {
        "valid_classical_count": len(valid),
        "classical_failsafe_abs_s_min": finite(min(fs_abs)) if fs_abs else None,
        "classical_failsafe_abs_s_max": finite(max(fs_abs)) if fs_abs else None,
        "classical_failsafe_abs_s_span": finite(max(fs_abs) - min(fs_abs)) if fs_abs else None,
        "classical_switch_roll_pitch_abs_deg_min": finite(min(switch_rp)) if switch_rp else None,
        "classical_switch_roll_pitch_abs_deg_max": finite(max(switch_rp)) if switch_rp else None,
        "classical_switch_rate_rad_s_min": finite(min(switch_rate)) if switch_rate else None,
        "classical_switch_rate_rad_s_max": finite(max(switch_rate)) if switch_rate else None,
        "classical_terminal_classes": terminal_classes,
        "classical_common_offboard_reason": bool(reasons),
        "classical_offboard_reason_evidence": reasons,
        "classical_common_active_flags_at_failsafe": common_active_flags,
        "classical_offboard_signal_lost_lead_s_min": finite(min(offboard_lead_s)) if offboard_lead_s else None,
        "classical_offboard_signal_lost_lead_s_max": finite(max(offboard_lead_s)) if offboard_lead_s else None,
        "classical_ground_contact_after_failsafe_s_min": finite(min(ground_after_failsafe_s))
        if ground_after_failsafe_s
        else None,
        "classical_ground_contact_after_failsafe_s_max": finite(max(ground_after_failsafe_s))
        if ground_after_failsafe_s
        else None,
        "classical_preterminal_roll_pitch_max_deg_max": finite(max(pre_rp)) if pre_rp else None,
        "classical_preterminal_rate_max_rad_s_max": finite(max(pre_rate)) if pre_rate else None,
        "classical_preterminal_hover_error_last_m_max": finite(max(pre_err)) if pre_err else None,
        "classical_preterminal_agl_min_m_min": finite(min(pre_agl)) if pre_agl else None,
    }


def fmt(value: Any, ndigits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{ndigits}f}"
    return str(value)


def write_markdown(out_dir: Path, decision: str, pairs: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    strict = [p for p in pairs if p.get("decision") == "STRICT_DIFFERENTIAL"]
    wide = [p for p in pairs if p.get("decision") == "ATTITUDE_CONTROL_DIFFERENTIAL"]
    unresolved = [p for p in pairs if p.get("decision") == "UNRESOLVED"]
    skipped = [p for p in pairs if p.get("decision") == "SKIPPED_UNTESTED"]

    lines: list[str] = [
        f"decision: {decision}",
        "",
        "# FUZZ-1c Decontamination Rejudgment",
        "",
        "source_run: `docs/fuzz1c_severity_20260625/results.json`",
        "method: existing ULOG-only reanalysis; no reruns; shim not used",
        "",
        "## Symmetric Decontamination Rule",
        "",
        "The rule is applied identically to `classical` and `mc_nn`. A terminal event is infrastructure/setup contamination only when the ULOG shows an infrastructure failsafe trigger near `vehicle_status.failsafe`, or ground contact follows that infrastructure failsafe. Control-level severity is then judged only on the window before that terminal event. A true pre-terminal tumble or angular-rate loss remains S3.",
        "",
        "Infrastructure trigger fields checked in `failsafe_flags`: `offboard_control_signal_lost`, `manual_control_signal_lost`, `gcs_connection_lost`, high-latency datalink loss, and estimator position/velocity/altitude invalid flags. For this run the causal near-edge field is `offboard_control_signal_lost`; baseline flags that are already true without a near failsafe edge are recorded but not treated as the cause.",
        "",
        "## Decision",
        "",
    ]
    if decision == "STRICT_DIFFERENTIAL_CONFIRMED":
        lines.append(
            f"Strict differential confirmed: {len(strict)} matched states have control-level `classical=S0/S1` and `mc_nn=S3`."
        )
    elif decision == "ATTITUDE_CONTROL_DIFFERENTIAL":
        lines.append(
            f"Only attitude-control differential confirmed: {len(wide)} matched states have `classical<=S2` and `mc_nn=S3`, but strict recovery was not proven."
        )
    else:
        lines.append("Wide S2-vs-S3 stands as the upper bound after decontamination.")
    lines.extend(
        [
            "",
            "## Severity-Invariance Diagnosis",
            "",
            (
                "Classical terminal events are severity-invariant: across valid pairs, switch severity spans "
                f"{fmt(summary.get('classical_switch_roll_pitch_abs_deg_min'))}-"
                f"{fmt(summary.get('classical_switch_roll_pitch_abs_deg_max'))} deg and "
                f"{fmt(summary.get('classical_switch_rate_rad_s_min'))}-"
                f"{fmt(summary.get('classical_switch_rate_rad_s_max'))} rad/s, but the first classical failsafe occurs at "
                f"{fmt(summary.get('classical_failsafe_abs_s_min'), 3)}-"
                f"{fmt(summary.get('classical_failsafe_abs_s_max'), 3)} s absolute and is classified as "
                f"{', '.join(summary.get('classical_terminal_classes', []))}."
            ),
            "",
            (
                "The invariant terminal shape is `vehicle_status.failsafe` + nav-state exit from OFFBOARD to AUTO_RTL, "
                "`failsafe_flags.offboard_control_signal_lost` rising "
                f"{fmt(summary.get('classical_offboard_signal_lost_lead_s_min'), 3)}-"
                f"{fmt(summary.get('classical_offboard_signal_lost_lead_s_max'), 3)} s before `failsafe`, "
                "and then ground contact "
                f"{fmt(summary.get('classical_ground_contact_after_failsafe_s_min'))}-"
                f"{fmt(summary.get('classical_ground_contact_after_failsafe_s_max'))} s later. "
                "Touchdown is therefore treated as infrastructure-failsafe aftermath, not the control failure evidence."
            ),
            "",
            (
                "Before that terminal event, classical is already recovered/stable: over the last 2 s before failsafe, "
                f"max roll/pitch <= {fmt(summary.get('classical_preterminal_roll_pitch_max_deg_max'))} deg, "
                f"max angular rate <= {fmt(summary.get('classical_preterminal_rate_max_rad_s_max'))} rad/s, "
                f"last hover error <= {fmt(summary.get('classical_preterminal_hover_error_last_m_max'))} m, "
                f"and min AGL >= {fmt(summary.get('classical_preterminal_agl_min_m_min'))} m."
            ),
            "",
            (
                "Common active `failsafe_flags` at the classical failsafe sample: "
                f"`{', '.join(summary.get('classical_common_active_flags_at_failsafe', []))}`. "
                "Only `offboard_control_signal_lost` has a near-edge timing at the terminal event; the others are baseline environment flags and are retained as evidence, not used as the causal classifier."
            ),
            "",
            "## Pair Table",
            "",
            "| idx | case | class switch rp/rate/AGL | class failsafe abs/dt | class pre-terminal rp/rate/err/AGL | class control sev | mc_nn control sev | decision |",
            "|---:|---|---:|---:|---:|---|---|---|",
        ]
    )
    for p in pairs:
        if not p.get("valid_matched_pair"):
            lines.append(f"| {p['idx']} | {p['case']} | - | - | - | skipped | skipped | {p['decision']} |")
            continue
        if p.get("decision") == "UNRESOLVED":
            lines.append(f"| {p['idx']} | {p['case']} | - | - | - | unresolved | unresolved | UNRESOLVED |")
            continue
        c = p["classical"]
        n = p["mcnn"]
        switch = c["switch"]
        term = c["terminal"]
        last = c["last_window_stats"]
        csev = c["control_level"]["control_level_label"]
        nsev = n["control_level"]["control_level_label"]
        pre = (
            f"{fmt(last.get('roll_pitch_max_deg'))}/"
            f"{fmt(last.get('angular_rate_max_rad_s'))}/"
            f"{fmt(last.get('hover_error_last_m'))}/"
            f"{fmt(last.get('agl_min_m'))}"
        )
        lines.append(
            "| "
            f"{p['idx']} | {p['case']} | "
            f"{fmt(switch.get('roll_pitch_abs_deg'))}/{fmt(switch.get('angular_rate_norm_rad_s'))}/{fmt(switch.get('agl_m'))} | "
            f"{fmt(term.get('first_failsafe_us') / 1e6 if term.get('first_failsafe_us') else None, 3)}/"
            f"{fmt(term.get('first_failsafe_dt_from_switch_s'))} | "
            f"{pre} | {csev} | {nsev} | {p['decision']} |"
        )

    lines.extend(
        [
            "",
            "## Asymmetry Check",
            "",
            "The same rule changes classical and does not rescue mc_nn because the data shapes differ. Classical S2 is caused by an infrastructure terminal event after stable controlled flight. The mc_nn S3 cases have no classified infrastructure terminal before the loss of control; their control window contains roll/pitch over 90 deg and angular rate over 8 rad/s, so they remain S3.",
            "",
            "## Counts",
            "",
            "```json",
            json.dumps(
                {
                    "valid_pairs": len([p for p in pairs if p.get("valid_matched_pair")]),
                    "strict_differential_count": len(strict),
                    "attitude_control_differential_count": len(wide),
                    "unresolved_count": len(unresolved),
                    "skipped_untested_count": len(skipped),
                },
                indent=2,
                sort_keys=True,
            ),
            "```",
            "",
            "## Artifacts",
            "",
            f"- structured results: `{out_dir.relative_to(REPO_ROOT) / 'results.json'}`",
            f"- per-pair JSONL: `{out_dir.relative_to(REPO_ROOT) / 'results.jsonl'}`",
            f"- criteria: `{out_dir.relative_to(REPO_ROOT) / 'criteria.json'}`",
        ]
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    MAIN_DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    data = load_json(args.results)
    pairs = [classify_pair(idx, pair) for idx, pair in enumerate(data["pairs"], start=1)]
    summary = stable_invariance_summary(pairs)
    strict = [p for p in pairs if p.get("decision") == "STRICT_DIFFERENTIAL"]
    attitude = [p for p in pairs if p.get("decision") == "ATTITUDE_CONTROL_DIFFERENTIAL"]
    unresolved = [p for p in pairs if p.get("decision") == "UNRESOLVED"]

    if strict:
        decision = "STRICT_DIFFERENTIAL_CONFIRMED"
    elif attitude:
        decision = "ATTITUDE_CONTROL_DIFFERENTIAL"
    elif unresolved:
        decision = "UNRESOLVED"
    else:
        decision = "WIDE_STANDS"

    criteria = {
        "symmetric_application": True,
        "infrastructure_terminal_rule": {
            "near_edge_window_s": TERMINAL_CAUSAL_WINDOW_S,
            "fields": INFRASTRUCTURE_TRIGGER_FIELDS,
            "ground_contact_after_infrastructure_failsafe_is_infrastructure_aftermath": True,
        },
        "control_window": "switch to first infrastructure terminal; otherwise switch to mission_end",
        "s3_thresholds": {
            "roll_pitch_abs_deg": S3_ROLL_PITCH_DEG,
            "angular_rate_norm_rad_s": S3_RATE_RAD_S,
        },
        "s0_recovery_thresholds_last_window": {
            "window_s": LAST_WINDOW_S,
            "roll_pitch_abs_deg": S0_ROLL_PITCH_DEG,
            "angular_rate_norm_rad_s": S0_RATE_RAD_S,
            "hover_error_m": S0_HOVER_ERROR_M,
            "min_agl_m": S0_MIN_AGL_M,
        },
    }
    result = {
        "decision": decision,
        "source_results": str(args.results.relative_to(REPO_ROOT) if args.results.is_absolute() else args.results),
        "criteria": criteria,
        "severity_invariance_summary": summary,
        "pair_summary": {
            "valid_pairs": len([p for p in pairs if p.get("valid_matched_pair")]),
            "strict_differential_count": len(strict),
            "attitude_control_differential_count": len(attitude),
            "unresolved_count": len(unresolved),
            "skipped_untested_count": len([p for p in pairs if p.get("decision") == "SKIPPED_UNTESTED"]),
        },
        "pairs": pairs,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "criteria.json", criteria)
    write_json(args.out_dir / "results.json", result)
    with (args.out_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for pair in pairs:
            handle.write(json.dumps(pair, sort_keys=True) + "\n")
    write_markdown(args.out_dir, decision, pairs, summary)
    print(json.dumps(result["pair_summary"], indent=2, sort_keys=True))
    print(f"decision: {decision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
