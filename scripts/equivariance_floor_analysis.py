#!/usr/bin/env python3
"""Stage 0/1 zero-simulation analysis for the yaw-equivariance probe.

This script only reads existing JSONL/ULOG artifacts. It does not launch PX4,
does not run SITL, and does not create new campaign directories.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from pyulog import ULog

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from m2_5_estimator_fairness import (  # noqa: E402
    finite,
    finite_max,
    finite_rms,
    first_dataset,
    interp_columns,
    local_vs_groundtruth,
    mask_window,
    quat_error_deg,
    quaternion,
    vector3,
    vector_norm,
)
from validity_automation import decontaminated_control_window  # noqa: E402


DENSE_BASE = {
    "roll_pitch_deg": 38.5,
    "requested_rate_rad_s": 1.15,
    "wind_speed_m_s": 0.0,
    "switch_delay_s": 0.09,
    "approach_phase_rad": 0.0,
}
THETA_BASE_FIELDS = [
    "requested_rate_rad_s",
    "switch_delay_s",
    "wind_speed_m_s",
    "approach_phase_rad",
]
ATTITUDE_THETA_IDS = {"attitude_deg_42", "attitude_deg_45", "attitude_deg_48"}
ULOG_TOPICS = [
    "vehicle_attitude",
    "vehicle_attitude_groundtruth",
    "vehicle_local_position",
    "vehicle_local_position_groundtruth",
    "vehicle_angular_velocity",
    "vehicle_angular_velocity_groundtruth",
    "vehicle_status",
    "estimator_status",
    "estimator_status_flags",
]


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def finite_range(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not clean:
        return None
    return max(clean) - min(clean)


def finite_mean(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not clean:
        return None
    return float(sum(clean) / len(clean))


def wrap_angle_deg(angle_deg: float) -> float:
    return ((float(angle_deg) + 180.0) % 360.0) - 180.0


def yaw_error_deg(yaw_est_deg: float, yaw_truth_deg: float) -> float:
    return wrap_angle_deg(float(yaw_est_deg) - float(yaw_truth_deg))


def quat_to_euler_deg(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=float)
    norm = np.linalg.norm(q, axis=1)
    valid = np.isfinite(norm) & (norm > 0.0)
    out = np.full((len(q), 3), np.nan, dtype=float)
    qn = q.copy()
    qn[valid] = qn[valid] / norm[valid, None]
    w = qn[:, 0]
    x = qn[:, 1]
    y = qn[:, 2]
    z = qn[:, 3]

    roll = np.arctan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    pitch_arg = np.clip(2.0 * (w * y - z * x), -1.0, 1.0)
    pitch = np.arcsin(pitch_arg)
    yaw = np.arctan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    out[:, 0] = np.rad2deg(roll)
    out[:, 1] = np.rad2deg(pitch)
    out[:, 2] = np.rad2deg(yaw)
    out[~valid, :] = np.nan
    return out


def quat_tilt_deg(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=float)
    out = np.full(len(q), np.nan, dtype=float)
    if len(q) == 0:
        return out
    norm = np.linalg.norm(q, axis=1)
    valid = np.isfinite(q).all(axis=1) & np.isfinite(norm) & (norm > 0.0)
    qn = q.copy()
    qn[valid] = qn[valid] / norm[valid, None]
    x = qn[valid, 1]
    y = qn[valid, 2]
    r33 = 1.0 - 2.0 * (x * x + y * y)
    out[valid] = np.rad2deg(np.arccos(np.clip(r33, -1.0, 1.0)))
    return out


def fisher_exact_greater(*, success_a: int, total_a: int, success_b: int, total_b: int) -> float:
    """One-sided Fisher exact p-value for success rate A > success rate B."""
    if not (0 <= success_a <= total_a and 0 <= success_b <= total_b):
        raise ValueError("success counts must be within totals")
    total_success = success_a + success_b
    total = total_a + total_b
    lower = max(0, total_success - total_b)
    upper = min(total_a, total_success)
    observed = success_a
    denominator = math.comb(total, total_a)
    tail = 0.0
    for x in range(max(observed, lower), upper + 1):
        tail += math.comb(total_success, x) * math.comb(total - total_success, total_a - x) / denominator
    return float(tail)


def resolve_artifact_path(raw_path: str | None, repo_root: Path = REPO_ROOT) -> Path | None:
    if not raw_path:
        return None
    text = str(raw_path)
    if text.startswith("/workspace/"):
        return repo_root / text.removeprefix("/workspace/")
    path = Path(text)
    if path.is_absolute():
        return path
    return repo_root / path


def compare_theta_base(theta: dict[str, Any], expected_base: dict[str, float]) -> dict[str, Any]:
    base = (
        theta.get("yaw_equivariance_probe", {})
        .get("plan_metadata", {})
        .get("base", {})
    )
    mismatches = []
    values = {}
    for field in THETA_BASE_FIELDS:
        actual = base.get(field)
        expected = expected_base.get(field)
        values[field] = actual
        if actual is None or not math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-9):
            mismatches.append({"field": field, "actual": actual, "expected": expected})
    return {
        "matches": not mismatches,
        "values": values,
        "expected": {field: expected_base[field] for field in THETA_BASE_FIELDS},
        "mismatches": mismatches,
    }


def task_event_elapsed_us(task: dict[str, Any], name: str) -> int | None:
    for event in task.get("events", []):
        if event.get("name") == name:
            return int(round(float(event.get("elapsed_s", 0.0)) * 1e6))
    return None


def task_window(task: dict[str, Any], ulog: ULog, controller: str) -> dict[str, Any]:
    active_elapsed_us = task_event_elapsed_us(task, "controller_active")
    if active_elapsed_us is None:
        active_elapsed_us = task_event_elapsed_us(task, "post_switch_setpoint")
    if active_elapsed_us is None:
        active_elapsed_us = task_event_elapsed_us(task, "state_trigger")
    mission_elapsed_us = task_event_elapsed_us(task, "mission_end")
    origin_us = int(ulog.start_timestamp)
    start_us = int(origin_us + active_elapsed_us) if active_elapsed_us is not None else origin_us
    mission_end_us = (
        int(origin_us + mission_elapsed_us)
        if mission_elapsed_us is not None
        else int(getattr(ulog, "last_timestamp", start_us))
    )
    decontamination = decontaminated_control_window(
        ulog,
        int(start_us),
        int(mission_end_us),
        controller=controller,
    )
    end_us = int(decontamination["control_end_us"])
    return {
        "origin_us": origin_us,
        "trajectory_start_us": int(start_us),
        "mission_end_us": end_us,
        "analysis_start_us": int(start_us),
        "analysis_end_us": int(mission_end_us),
        "control_end_us": end_us,
        "decontamination": decontamination,
    }


def trigger_state(task: dict[str, Any]) -> dict[str, Any]:
    if isinstance(task.get("state_trigger_state"), dict):
        state = task["state_trigger_state"]
        return {
            "trigger_roll_pitch_deg": finite(state.get("roll_pitch_abs_deg")),
            "trigger_angular_rate_norm_rad_s": finite(state.get("angular_rate_norm_rad_s")),
            "trigger_timestamp_us": state.get("timestamp_us"),
        }
    for event in task.get("events", []):
        if event.get("name") != "state_trigger":
            continue
        state = event.get("detail", {}).get("state", {})
        return {
            "trigger_roll_pitch_deg": finite(state.get("roll_pitch_abs_deg")),
            "trigger_angular_rate_norm_rad_s": finite(state.get("angular_rate_norm_rad_s")),
            "trigger_timestamp_us": state.get("timestamp_us"),
        }
    return {
        "trigger_roll_pitch_deg": None,
        "trigger_angular_rate_norm_rad_s": None,
        "trigger_timestamp_us": None,
    }


def task_max_observed(task: dict[str, Any]) -> dict[str, Any]:
    state = task.get("state_trigger_max_observed")
    if not isinstance(state, dict):
        for event in task.get("events", []):
            if event.get("name") == "state_trigger_timeout":
                state = event.get("detail", {}).get("max_observed")
                break
    if not isinstance(state, dict):
        return {"max_roll_pitch_deg": None, "max_angular_rate_norm_rad_s": None}
    return {
        "max_roll_pitch_deg": finite(state.get("roll_pitch_abs_deg")),
        "max_angular_rate_norm_rad_s": finite(state.get("angular_rate_norm_rad_s")),
        "max_observed_source": "task.state_trigger_max_observed",
    }


def plant_metrics(ulog: ULog, window: dict[str, Any]) -> dict[str, Any]:
    start_us = int(window["analysis_start_us"])
    end_us = int(window["control_end_us"])
    att = first_dataset(ulog, "vehicle_attitude_groundtruth")
    rates = first_dataset(ulog, "vehicle_angular_velocity_groundtruth")
    out: dict[str, Any] = {}

    if att is None:
        out.update({"attitude_groundtruth_present": False, "max_roll_pitch_deg": None})
    else:
        ts = att.data["timestamp"].astype(np.int64)
        mask = mask_window(ts, start_us, end_us)
        q = quaternion(att.data)[mask]
        tilt = quat_tilt_deg(q)
        out.update(
            {
                "attitude_groundtruth_present": True,
                "attitude_groundtruth_samples": int(np.count_nonzero(mask)),
                "max_roll_pitch_deg": finite_max(tilt),
            }
        )

    if rates is None:
        out.update({"angular_velocity_groundtruth_present": False, "max_angular_rate_norm_rad_s": None})
    else:
        ts = rates.data["timestamp"].astype(np.int64)
        mask = mask_window(ts, start_us, end_us)
        omega = vector3(rates.data, "xyz")[mask]
        out.update(
            {
                "angular_velocity_groundtruth_present": True,
                "angular_velocity_groundtruth_samples": int(np.count_nonzero(mask)),
                "max_angular_rate_norm_rad_s": finite_max(vector_norm(omega)) if len(omega) else None,
            }
        )
    return out


def attitude_error_components(ulog: ULog, window: dict[str, Any]) -> dict[str, Any]:
    start_us = int(window["analysis_start_us"])
    end_us = int(window["control_end_us"])
    att = first_dataset(ulog, "vehicle_attitude")
    truth = first_dataset(ulog, "vehicle_attitude_groundtruth")
    if att is None or truth is None:
        return {"present": False}

    ats = att.data["timestamp"].astype(np.int64)
    tts = truth.data["timestamp"].astype(np.int64)
    amask = mask_window(ats, start_us, end_us)
    tmask = mask_window(tts, start_us, end_us)
    if not np.any(amask) or not np.any(tmask):
        return {"present": True, "window_samples": 0}

    q_est = quaternion(att.data)[amask]
    q_truth = quaternion(truth.data)[tmask]
    q_truth_i = interp_columns(tts[tmask], q_truth, ats[amask])
    err_quat = quat_error_deg(q_est, q_truth_i)
    est_euler = quat_to_euler_deg(q_est)
    truth_euler = quat_to_euler_deg(q_truth_i)
    delta = np.vectorize(wrap_angle_deg)(est_euler - truth_euler)
    roll = delta[:, 0]
    pitch = delta[:, 1]
    yaw = delta[:, 2]
    return {
        "present": True,
        "window_samples": int(np.count_nonzero(amask)),
        "yaw_error_rms_deg": finite_rms(yaw),
        "yaw_error_max_deg": finite_max(np.abs(yaw)),
        "roll_error_rms_deg": finite_rms(roll),
        "roll_error_max_deg": finite_max(np.abs(roll)),
        "pitch_error_rms_deg": finite_rms(pitch),
        "pitch_error_max_deg": finite_max(np.abs(pitch)),
        "quaternion_error_rms_deg": finite_rms(err_quat),
        "quaternion_error_max_deg": finite_max(err_quat),
    }


def extract_eval_metrics(record: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    evidence = record.get("evidence", {})
    controller = str(record.get("controller", record.get("controller_role", "")))
    if controller not in {"classical", "mcnn", "mc_nn", "raptor"}:
        controller = "mcnn" if str(record.get("tag", "")).endswith("_mcnn") else "classical"
    task_path = resolve_artifact_path(evidence.get("task_path"), repo_root)
    ulog_path = resolve_artifact_path(evidence.get("ulog_path"), repo_root)
    if task_path is None:
        fallback_dir = repo_root / "runs/campaigns/equivariance_probe_20260708/evals" / str(record.get("tag"))
        matches = sorted(fallback_dir.glob("*_task.json"))
        task_path = matches[0] if matches else None
    if task_path is None:
        raise ValueError(f"missing task path for {record.get('tag')}")
    task = read_json(task_path)
    if ulog_path is None or not ulog_path.exists():
        metrics = {
            **task_max_observed(task),
            **trigger_state(task),
            "attitude_error": {"present": False, "reason": "missing_ulog_for_invalid_record"},
            "local_position_error": {"present": False, "reason": "missing_ulog_for_invalid_record"},
            "control_window": None,
        }
        return {
            "tag": record.get("tag"),
            "theta_id": record.get("theta_id"),
            "psi_deg": record.get("psi_deg"),
            "seed": record.get("seed"),
            "controller": controller,
            "stage": record.get("stage"),
            "kind": record.get("kind"),
            "valid": bool(record.get("valid", record.get("returncode") == 0)),
            "returncode": record.get("returncode"),
            "severity": record.get("severity"),
            "severity_label": record.get("severity_label"),
            "theta": record.get("theta"),
            "theta_path": record.get("theta_path"),
            "ulog_path": None,
            "task_path": str(task_path.relative_to(repo_root)) if task_path.is_relative_to(repo_root) else str(task_path),
            "metrics": metrics,
            "error": record.get("error"),
        }
    ulog = ULog(str(ulog_path), ULOG_TOPICS)
    window = task_window(task, ulog, "mcnn" if controller in {"mcnn", "mc_nn"} else controller)
    estimator_window = {
        "trajectory_start_us": window["analysis_start_us"],
        "mission_end_us": window["control_end_us"],
    }
    local = local_vs_groundtruth(ulog, estimator_window)
    metrics = {
        **plant_metrics(ulog, window),
        **trigger_state(task),
        "attitude_error": attitude_error_components(ulog, window),
        "local_position_error": local,
        "control_window": {
            "analysis_start_us": window["analysis_start_us"],
            "control_end_us": window["control_end_us"],
            "control_duration_s": window["decontamination"].get("control_duration_s"),
        },
    }
    return {
        "tag": record.get("tag"),
        "theta_id": record.get("theta_id"),
        "psi_deg": record.get("psi_deg"),
        "seed": record.get("seed"),
        "controller": controller,
        "stage": record.get("stage"),
        "kind": record.get("kind"),
        "valid": bool(record.get("valid", record.get("returncode") == 0)),
        "returncode": record.get("returncode"),
        "severity": record.get("severity"),
        "severity_label": record.get("severity_label"),
        "theta": record.get("theta"),
        "theta_path": record.get("theta_path"),
        "ulog_path": str(ulog_path.relative_to(repo_root)) if ulog_path.is_relative_to(repo_root) else str(ulog_path),
        "task_path": str(task_path.relative_to(repo_root)) if task_path.is_relative_to(repo_root) else str(task_path),
        "metrics": metrics,
    }


def extract_dense_eval_metrics(record: dict[str, Any], controller: str, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    evidence = record.get("evidence", {})
    task_path = resolve_artifact_path(evidence.get("task_paths", {}).get(controller), repo_root)
    ulog_path = resolve_artifact_path(evidence.get("ulog_paths", {}).get(controller), repo_root)
    property_path = resolve_artifact_path(evidence.get("property_paths", {}).get(controller), repo_root)
    if task_path is None or ulog_path is None:
        raise ValueError(f"missing dense task/ulog path for {record.get('tag')} {controller}")
    dense_record = {
        "tag": f"{record.get('tag')}_{controller}",
        "theta_id": record.get("point_id"),
        "psi_deg": 0,
        "seed": record.get("seed"),
        "controller": controller,
        "stage": "dense_seed_jitter",
        "kind": record.get("axis"),
        "valid": record.get("returncode") == 0,
        "returncode": record.get("returncode"),
        "severity": record.get("classical_severity" if controller == "classical" else "neural_severity"),
        "severity_label": None,
        "theta": record.get("actual_genome"),
        "theta_path": record.get("theta_path"),
        "evidence": {"task_path": str(task_path), "ulog_path": str(ulog_path)},
    }
    out = extract_eval_metrics(dense_record, repo_root)
    out["property_path"] = str(property_path.relative_to(repo_root)) if property_path and property_path.is_relative_to(repo_root) else (str(property_path) if property_path else None)
    out["dense_axis"] = record.get("axis")
    out["dense_value"] = record.get("value")
    out["primary_bug"] = record.get("primary_bug")
    return out


def group_by_theta_psi(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("theta_id"))].append(record)
    return dict(sorted(grouped.items()))


def summarize_classical_floor(records: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for theta_id, items in group_by_theta_psi(records).items():
        rows = []
        for item in sorted(items, key=lambda r: int(r.get("psi_deg") or 0)):
            att = item["metrics"]["attitude_error"]
            rows.append(
                {
                    "psi_deg": item.get("psi_deg"),
                    "seed": item.get("seed"),
                    "severity": item.get("severity"),
                    "valid": item.get("valid"),
                    "yaw_error_rms_deg": att.get("yaw_error_rms_deg"),
                    "yaw_error_max_deg": att.get("yaw_error_max_deg"),
                    "roll_error_rms_deg": att.get("roll_error_rms_deg"),
                    "pitch_error_rms_deg": att.get("pitch_error_rms_deg"),
                    "max_roll_pitch_deg": item["metrics"].get("max_roll_pitch_deg"),
                    "max_angular_rate_norm_rad_s": item["metrics"].get("max_angular_rate_norm_rad_s"),
                    "trigger_roll_pitch_deg": item["metrics"].get("trigger_roll_pitch_deg"),
                    "trigger_angular_rate_norm_rad_s": item["metrics"].get("trigger_angular_rate_norm_rad_s"),
                }
            )
        out[theta_id] = {
            "rows": rows,
            "ranges": {
                "yaw_error_rms_deg": finite_range([row["yaw_error_rms_deg"] for row in rows]),
                "yaw_error_max_deg": finite_range([row["yaw_error_max_deg"] for row in rows]),
                "max_roll_pitch_deg": finite_range([row["max_roll_pitch_deg"] for row in rows]),
                "max_angular_rate_norm_rad_s": finite_range([row["max_angular_rate_norm_rad_s"] for row in rows]),
            },
        }
    return out


def summarize_dense_seed_jitter(records: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for theta_id, items in group_by_theta_psi(records).items():
        rows = []
        for item in sorted(items, key=lambda r: int(r.get("seed") or 0)):
            att = item["metrics"]["attitude_error"]
            rows.append(
                {
                    "seed": item.get("seed"),
                    "severity": item.get("severity"),
                    "yaw_error_rms_deg": att.get("yaw_error_rms_deg"),
                    "max_roll_pitch_deg": item["metrics"].get("max_roll_pitch_deg"),
                    "max_angular_rate_norm_rad_s": item["metrics"].get("max_angular_rate_norm_rad_s"),
                }
            )
        out[theta_id] = {
            "rows": rows,
            "ranges": {
                "yaw_error_rms_deg": finite_range([row["yaw_error_rms_deg"] for row in rows]),
                "max_roll_pitch_deg": finite_range([row["max_roll_pitch_deg"] for row in rows]),
                "max_angular_rate_norm_rad_s": finite_range([row["max_angular_rate_norm_rad_s"] for row in rows]),
            },
        }
    out["_max_ranges"] = {
        "yaw_error_rms_deg": finite_max(np.asarray([value["ranges"]["yaw_error_rms_deg"] for key, value in out.items() if key != "_max_ranges"], dtype=float)),
        "max_roll_pitch_deg": finite_max(np.asarray([value["ranges"]["max_roll_pitch_deg"] for key, value in out.items() if key != "_max_ranges"], dtype=float)),
        "max_angular_rate_norm_rad_s": finite_max(np.asarray([value["ranges"]["max_angular_rate_norm_rad_s"] for key, value in out.items() if key != "_max_ranges"], dtype=float)),
    }
    return out


def summarize_mcnn(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_key: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_key[(str(record.get("theta_id")), int(record.get("psi_deg") or 0))].append(record)
    out: dict[str, Any] = {}
    for (theta_id, psi), items in sorted(by_key.items()):
        rows = []
        for item in sorted(items, key=lambda r: int(r.get("seed") or 0)):
            att = item["metrics"]["attitude_error"]
            rows.append(
                {
                    "seed": item.get("seed"),
                    "severity": item.get("severity"),
                    "valid": item.get("valid"),
                    "max_roll_pitch_deg": item["metrics"].get("max_roll_pitch_deg"),
                    "max_angular_rate_norm_rad_s": item["metrics"].get("max_angular_rate_norm_rad_s"),
                    "yaw_error_rms_deg": att.get("yaw_error_rms_deg"),
                }
            )
        out[f"{theta_id}:psi{psi:03d}"] = {
            "theta_id": theta_id,
            "psi_deg": psi,
            "rows": rows,
            "severity_counts": {
                str(sev): sum(1 for row in rows if row["severity"] == sev)
                for sev in sorted({row["severity"] for row in rows}, key=lambda value: (-1 if value is None else int(value)))
            },
            "s3_or_s4_count": sum(1 for row in rows if row["severity"] is not None and int(row["severity"]) >= 3),
            "valid_count": sum(1 for row in rows if row["valid"]),
            "mean_max_roll_pitch_deg": finite_mean([row["max_roll_pitch_deg"] for row in rows]),
            "mean_max_angular_rate_norm_rad_s": finite_mean([row["max_angular_rate_norm_rad_s"] for row in rows]),
            "mean_yaw_error_rms_deg": finite_mean([row["yaw_error_rms_deg"] for row in rows]),
        }
    return out


def escape_analysis(records: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for theta_id, escape_psis in {"attitude_deg_42": {90}, "attitude_deg_48": {0}}.items():
        subset = [record for record in records if record.get("theta_id") == theta_id]
        escape = [record for record in subset if int(record.get("psi_deg") or 0) in escape_psis]
        fail = [record for record in subset if int(record.get("psi_deg") or 0) not in escape_psis]
        result[theta_id] = {
            "escape_psis": sorted(escape_psis),
            "escape": {
                "count": len(escape),
                "severity_values": [record.get("severity") for record in escape],
                "mean_max_roll_pitch_deg": finite_mean([record["metrics"].get("max_roll_pitch_deg") for record in escape]),
                "mean_max_angular_rate_norm_rad_s": finite_mean([record["metrics"].get("max_angular_rate_norm_rad_s") for record in escape]),
            },
            "non_escape": {
                "count": len(fail),
                "severity_values": [record.get("severity") for record in fail],
                "mean_max_roll_pitch_deg": finite_mean([record["metrics"].get("max_roll_pitch_deg") for record in fail]),
                "mean_max_angular_rate_norm_rad_s": finite_mean([record["metrics"].get("max_angular_rate_norm_rad_s") for record in fail]),
            },
        }
    return result


def theta_consistency_for_probe(records: list[dict[str, Any]], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    checks = []
    for record in records:
        psi = record.get("psi_deg")
        if record.get("theta_id") not in ATTITUDE_THETA_IDS or psi is None or int(psi) != 0:
            continue
        theta_path = resolve_artifact_path(record.get("theta_path"), repo_root)
        if theta_path is None:
            continue
        theta = read_json(theta_path)
        check = compare_theta_base(theta, DENSE_BASE)
        checks.append(
            {
                "tag": record.get("tag"),
                "theta_id": record.get("theta_id"),
                "controller": record.get("controller"),
                "theta_path": str(theta_path.relative_to(repo_root)) if theta_path.is_relative_to(repo_root) else str(theta_path),
                **check,
            }
        )
    return {
        "matches": bool(checks) and all(check["matches"] for check in checks),
        "checks": checks,
    }


def pooled_fisher(
    mcnn_probe_records: list[dict[str, Any]],
    dense_mcnn_records: list[dict[str, Any]],
    *,
    allow_dense_pool: bool,
) -> dict[str, Any]:
    dense_by_theta: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if allow_dense_pool:
        for record in dense_mcnn_records:
            dense_by_theta[str(record.get("theta_id"))].append(record)

    def count(theta_id: str, psis: set[int], include_dense: bool) -> tuple[int, int]:
        selected = [
            record
            for record in mcnn_probe_records
            if record.get("theta_id") == theta_id and int(record.get("psi_deg") or 0) in psis and record.get("valid")
        ]
        if include_dense and 0 in psis:
            selected.extend([record for record in dense_by_theta.get(theta_id, []) if record.get("valid")])
        successes = sum(1 for record in selected if record.get("severity") is not None and int(record["severity"]) >= 3)
        return successes, len(selected)

    att42_a = count("attitude_deg_42", {0}, allow_dense_pool)
    att42_b = count("attitude_deg_42", {90}, False)
    att48_a = count("attitude_deg_48", {90, 180, 270}, False)
    att48_b = count("attitude_deg_48", {0}, allow_dense_pool)
    return {
        "dense_pool_allowed": allow_dense_pool,
        "att42_psi0_greater_than_psi90": {
            "a_label": "att42_psi0",
            "a_s3": att42_a[0],
            "a_total": att42_a[1],
            "b_label": "att42_psi90",
            "b_s3": att42_b[0],
            "b_total": att42_b[1],
            "p_one_sided": fisher_exact_greater(
                success_a=att42_a[0], total_a=att42_a[1], success_b=att42_b[0], total_b=att42_b[1]
            )
            if att42_a[1] and att42_b[1]
            else None,
        },
        "att48_psi90_180_270_greater_than_psi0": {
            "a_label": "att48_psi90_180_270",
            "a_s3": att48_a[0],
            "a_total": att48_a[1],
            "b_label": "att48_psi0",
            "b_s3": att48_b[0],
            "b_total": att48_b[1],
            "p_one_sided": fisher_exact_greater(
                success_a=att48_a[0], total_a=att48_a[1], success_b=att48_b[0], total_b=att48_b[1]
            )
            if att48_a[1] and att48_b[1]
            else None,
        },
    }


def recommendation(classical_floor: dict[str, Any], dense_jitter: dict[str, Any]) -> dict[str, Any]:
    floor_yaw = finite_max(
        np.asarray(
            [item["ranges"]["yaw_error_rms_deg"] for item in classical_floor.values() if item["ranges"]["yaw_error_rms_deg"] is not None],
            dtype=float,
        )
    )
    floor_tilt = finite_max(
        np.asarray(
            [item["ranges"]["max_roll_pitch_deg"] for item in classical_floor.values() if item["ranges"]["max_roll_pitch_deg"] is not None],
            dtype=float,
        )
    )
    jitter_yaw = dense_jitter.get("_max_ranges", {}).get("yaw_error_rms_deg")
    jitter_tilt = dense_jitter.get("_max_ranges", {}).get("max_roll_pitch_deg")
    yaw_ratio = (floor_yaw / jitter_yaw) if floor_yaw is not None and jitter_yaw not in (None, 0.0) else None
    tilt_ratio = (floor_tilt / jitter_tilt) if floor_tilt is not None and jitter_tilt not in (None, 0.0) else None
    if yaw_ratio is not None and yaw_ratio > 2.0:
        decision = "先 Stage 3"
        reason = "classical yaw-error psi range exceeds dense seed jitter by >2x"
    elif tilt_ratio is not None and tilt_ratio > 2.0:
        decision = "NO-GO / inspect plant-or-trigger anisotropy before powered Stage 2"
        reason = "classical achieved tilt psi range exceeds dense seed jitter by >2x"
    else:
        decision = "GO Stage 2"
        reason = "classical continuous floor is within the observed seed-jitter scale"
    return {
        "decision": decision,
        "reason": reason,
        "max_classical_floor_yaw_error_rms_range_deg": floor_yaw,
        "max_dense_seed_yaw_error_rms_range_deg": jitter_yaw,
        "yaw_range_to_seed_jitter_ratio": yaw_ratio,
        "max_classical_floor_tilt_range_deg": floor_tilt,
        "max_dense_seed_tilt_range_deg": jitter_tilt,
        "tilt_range_to_seed_jitter_ratio": tilt_ratio,
    }


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    probe_run = (repo_root / args.probe_run).resolve()
    preflight_run = (repo_root / args.preflight_run).resolve()
    dense_run = (repo_root / args.dense_run).resolve()

    probe_records_raw = read_jsonl(probe_run / "equivariance_results.jsonl")
    preflight_records_raw = read_jsonl(preflight_run / "stage0_results.jsonl")
    dense_records_raw = [
        record
        for record in read_jsonl(dense_run / "sweep_results.jsonl")
        if record.get("axis") == "attitude_deg" and record.get("point_id") in ATTITUDE_THETA_IDS and record.get("returncode") == 0
    ]

    print(f"SOURCE: probe_results={probe_run / 'equivariance_results.jsonl'}")
    print(f"VALUE: probe_records_raw={len(probe_records_raw)}")
    print(f"SOURCE: preflight_results={preflight_run / 'stage0_results.jsonl'}")
    print(f"VALUE: preflight_records_raw={len(preflight_records_raw)}")
    print(f"SOURCE: dense_seed_results={dense_run / 'sweep_results.jsonl'}")
    print(f"VALUE: dense_attitude_records_raw={len(dense_records_raw)}")

    theta_consistency = theta_consistency_for_probe(probe_records_raw, repo_root)
    print(f"VALUE: theta_consistency_matches={theta_consistency['matches']}")

    probe_metrics = [extract_eval_metrics(record, repo_root) for record in probe_records_raw]
    preflight_metrics = [extract_eval_metrics(record, repo_root) for record in preflight_records_raw]
    dense_classical_metrics = [extract_dense_eval_metrics(record, "classical", repo_root) for record in dense_records_raw]
    dense_mcnn_metrics = [extract_dense_eval_metrics(record, "mcnn", repo_root) for record in dense_records_raw]

    classical_floor_records = [record for record in probe_metrics if record["controller"] == "classical"]
    mcnn_records = [record for record in probe_metrics if record["controller"] in {"mcnn", "mc_nn"}]
    classical_floor = summarize_classical_floor(classical_floor_records)
    dense_jitter = summarize_dense_seed_jitter(dense_classical_metrics)
    preflight_pair2 = summarize_classical_floor(preflight_metrics)
    hard_cell = classical_floor.get("hard_attitude_deg_50", {})
    att45 = classical_floor.get("attitude_deg_45", {})
    mcnn_summary = summarize_mcnn(mcnn_records)
    fisher = pooled_fisher(mcnn_records, dense_mcnn_metrics, allow_dense_pool=theta_consistency["matches"])

    payload = {
        "stage": "equivariance_stage01_zero_sim_analysis",
        "simulation_run": False,
        "new_ulog_generated": False,
        "sources": {
            "probe_run": str(probe_run.relative_to(repo_root)),
            "preflight_run": str(preflight_run.relative_to(repo_root)),
            "dense_seed_run": str(dense_run.relative_to(repo_root)),
        },
        "counts": {
            "probe_records": len(probe_metrics),
            "classical_floor_records": len(classical_floor_records),
            "mcnn_records": len(mcnn_records),
            "preflight_records": len(preflight_metrics),
            "dense_classical_seed_records": len(dense_classical_metrics),
            "dense_mcnn_seed_records": len(dense_mcnn_metrics),
        },
        "theta_consistency": theta_consistency,
        "classical_floor": classical_floor,
        "dense_seed_jitter": dense_jitter,
        "preflight_pair2": preflight_pair2,
        "hard_attitude_deg_50": hard_cell,
        "attitude_deg_45": att45,
        "mcnn": {
            "by_theta_psi": mcnn_summary,
            "escape_analysis": escape_analysis(mcnn_records),
            "direction_reversal": (
                "attitude_deg_42 is severe at psi0 and escaped at psi90; "
                "attitude_deg_48 escapes at psi0 and is severe at psi90/180/270"
            ),
        },
        "pooled_fisher": fisher,
    }
    payload["recommendation"] = recommendation(classical_floor, dense_jitter)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--probe-run", default="runs/campaigns/equivariance_probe_20260708")
    parser.add_argument("--preflight-run", default="runs/campaigns/equivariance_probe_preflight_20260708")
    parser.add_argument("--dense-run", default="runs/campaigns/switch_severity_dense_sweep_20260630")
    parser.add_argument("--output-json")
    args = parser.parse_args()

    payload = analyze(args)
    if args.output_json:
        output_path = Path(args.output_json)
        write_json(output_path, payload)
        print(f"VALUE: output_json={output_path}")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
