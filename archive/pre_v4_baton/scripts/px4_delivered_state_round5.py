#!/usr/bin/env python3
"""Round 5 delivered-state audit from existing JSON/ULOG artifacts.

This script is deliberately read-only with respect to PX4. It parses existing
campaign records, task JSON files, and ULOGs; it does not run simulation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from concurrent.futures import ProcessPoolExecutor
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pyulog import ULog


REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "docs" / "round5_delivered_state_20260709"
DO_SET_MODE = 176
NAV_EXTERNAL1 = 23
NEEDED_TOPICS = [
    "vehicle_status",
    "vehicle_command",
    "vehicle_command_ack",
    "vehicle_attitude",
    "vehicle_attitude_groundtruth",
    "vehicle_angular_velocity",
    "vehicle_angular_velocity_groundtruth",
    "vehicle_local_position",
    "vehicle_local_position_groundtruth",
    "trajectory_setpoint",
]


@dataclass
class EvalRecord:
    population: str
    campaign: str
    tag: str
    controller: str
    seed: int | None
    theta_path: Path
    task_path: Path
    ulog_path: Path
    property_path: Path | None
    compare_path: Path | None
    outcome_severity: int | None
    outcome_label: str | None
    classical_severity: int | None
    primary_bug: bool | None
    source_record: dict[str, Any]


def norm_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    text = str(value)
    if text.startswith("/workspace/"):
        return REPO / text[len("/workspace/") :]
    path = Path(text)
    if path.is_absolute():
        return path
    return REPO / path


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def first_existing(*paths: Path | None) -> Path | None:
    for path in paths:
        if path is not None and path.exists():
            return path
    return None


def record_from_campaign_row(population: str, row: dict[str, Any], controller: str) -> EvalRecord | None:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    theta_path = norm_path(row.get("theta_path") or evidence.get("theta_path"))
    task_paths = evidence.get("task_paths") if isinstance(evidence.get("task_paths"), dict) else {}
    ulog_paths = evidence.get("ulog_paths") if isinstance(evidence.get("ulog_paths"), dict) else {}
    prop_paths = evidence.get("property_paths") if isinstance(evidence.get("property_paths"), dict) else {}
    task_path = norm_path(task_paths.get(controller))
    ulog_path = norm_path(ulog_paths.get(controller))
    property_path = norm_path(prop_paths.get(controller))
    compare_path = norm_path(row.get("compare_path") or evidence.get("compare_path"))
    if theta_path is None or task_path is None or ulog_path is None:
        return None
    if not (theta_path.exists() and task_path.exists() and ulog_path.exists()):
        return None
    fit = row.get("fitness") if isinstance(row.get("fitness"), dict) else {}
    neural_sev = fit.get("neural_severity")
    classical_sev = fit.get("classical_severity")
    label = fit.get("neural_severity_label")
    return EvalRecord(
        population=population,
        campaign=theta_path.parts[-3] if len(theta_path.parts) >= 3 else "",
        tag=str(row.get("tag") or theta_path.stem),
        controller=controller,
        seed=int(row["seed"]) if row.get("seed") is not None else None,
        theta_path=theta_path,
        task_path=task_path,
        ulog_path=ulog_path,
        property_path=property_path if property_path and property_path.exists() else None,
        compare_path=compare_path if compare_path and compare_path.exists() else None,
        outcome_severity=int(neural_sev) if neural_sev is not None else None,
        outcome_label=str(label) if label is not None else None,
        classical_severity=int(classical_sev) if classical_sev is not None else None,
        primary_bug=bool(row.get("primary_bug")) if row.get("primary_bug") is not None else None,
        source_record=row,
    )


def record_from_sweep_row(population: str, row: dict[str, Any], controller: str) -> EvalRecord | None:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    theta_path = norm_path(row.get("theta_path") or evidence.get("theta_path"))
    task_paths = evidence.get("task_paths") if isinstance(evidence.get("task_paths"), dict) else {}
    ulog_paths = evidence.get("ulog_paths") if isinstance(evidence.get("ulog_paths"), dict) else {}
    prop_paths = evidence.get("property_paths") if isinstance(evidence.get("property_paths"), dict) else {}
    task_path = norm_path(task_paths.get(controller))
    ulog_path = norm_path(ulog_paths.get(controller))
    property_path = norm_path(prop_paths.get(controller))
    compare_path = norm_path(row.get("compare_path") or evidence.get("compare_path"))
    if theta_path is None or task_path is None or ulog_path is None:
        return None
    if not (theta_path.exists() and task_path.exists() and ulog_path.exists()):
        return None
    sev = row.get("neural_severity")
    csev = row.get("classical_severity")
    return EvalRecord(
        population=population,
        campaign=theta_path.parts[-3] if len(theta_path.parts) >= 3 else "",
        tag=str(row.get("tag") or theta_path.stem),
        controller=controller,
        seed=int(row["seed"]) if row.get("seed") is not None else None,
        theta_path=theta_path,
        task_path=task_path,
        ulog_path=ulog_path,
        property_path=property_path if property_path and property_path.exists() else None,
        compare_path=compare_path if compare_path and compare_path.exists() else None,
        outcome_severity=int(sev) if sev is not None else None,
        outcome_label=f"S{int(sev)}" if sev is not None else None,
        classical_severity=int(csev) if csev is not None else None,
        primary_bug=bool(row.get("strict_s0_vs_s3")) if row.get("strict_s0_vs_s3") is not None else None,
        source_record=row,
    )


def records_from_summary_array(population: str, path: Path, key: str, controller: str) -> list[EvalRecord]:
    summary = load_json(path)
    rows = summary.get(key) if isinstance(summary.get(key), list) else []
    out = []
    for row in rows:
        rec = record_from_campaign_row(population, row, controller)
        if rec is not None:
            out.append(rec)
    return out


def collect_records(population: str) -> list[EvalRecord]:
    records: list[EvalRecord] = []
    if population in {"mcnn_dense", "mcnn_all", "all"}:
        path = REPO / "runs/campaigns/switch_severity_dense_sweep_20260630/sweep_results.jsonl"
        records.extend(
            rec
            for row in jsonl(path)
            if (rec := record_from_sweep_row("mcnn_dense_rq3", row, "mcnn")) is not None
        )
    if population in {"mcnn_search", "mcnn_all", "all"}:
        for run_dir in sorted((REPO / "runs/campaigns").glob("switch_severity_*")):
            evals = run_dir / "evals.jsonl"
            if not evals.exists():
                continue
            for row in jsonl(evals):
                if row.get("returncode") != 0:
                    continue
                rec = record_from_campaign_row("mcnn_search_success", row, "mcnn")
                if rec is not None:
                    records.append(rec)
    if population in {"raptor_v8", "all"}:
        path = REPO / "runs/campaigns/raptor_switch_severity_dense_sweep_20260705/sweep_results.jsonl"
        records.extend(
            rec
            for row in jsonl(path)
            if (rec := record_from_sweep_row("raptor_dense", row, "raptor")) is not None
        )
        for run_dir in sorted((REPO / "runs/campaigns").glob("raptor_switch_severity_*")):
            if run_dir.name == "raptor_switch_severity_dense_sweep_20260705":
                continue
            evals = run_dir / "evals.jsonl"
            if not evals.exists():
                continue
            for row in jsonl(evals):
                if row.get("returncode") != 0:
                    continue
                rec = record_from_campaign_row("raptor_search_success", row, "raptor")
                if rec is not None:
                    records.append(rec)
        for row in jsonl(REPO / "runs/campaigns/raptor_gate0_stability_20260705/evals.jsonl"):
            if row.get("returncode") != 0:
                continue
            rec = record_from_campaign_row("raptor_gate0_success", row, "raptor")
            if rec is not None:
                records.append(rec)
        records.extend(
            records_from_summary_array(
                "raptor_anchor_boundary",
                REPO / "runs/campaigns/raptor_gate0_anchor_boundary_20260705/summary.json",
                "records_payload",
                "raptor",
            )
        )
        records.extend(
            records_from_summary_array(
                "raptor_anchor_recheck",
                REPO / "runs/campaigns/raptor_gate0_anchor_recheck_20260705/summary.json",
                "anchors",
                "raptor",
            )
        )
    return records


def datasets(ulog: ULog) -> dict[str, dict[str, np.ndarray]]:
    out: dict[str, dict[str, np.ndarray]] = {}
    for dataset in ulog.data_list:
        if dataset.multi_id == 0 and dataset.name not in out:
            out[dataset.name] = dataset.data
    return out


def quat_to_rpy(q: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    q0, q1, q2, q3 = [q[:, idx] for idx in range(4)]
    roll = np.arctan2(2.0 * (q0 * q1 + q2 * q3), 1.0 - 2.0 * (q1 * q1 + q2 * q2))
    sin_pitch = np.clip(2.0 * (q0 * q2 - q3 * q1), -1.0, 1.0)
    pitch = np.arcsin(sin_pitch)
    yaw = np.arctan2(2.0 * (q0 * q3 + q1 * q2), 1.0 - 2.0 * (q2 * q2 + q3 * q3))
    return roll, pitch, yaw


def quat_tilt_deg(q: np.ndarray) -> np.ndarray:
    q0 = q[:, 0]
    q1 = q[:, 1]
    q2 = q[:, 2]
    del q0
    r22 = np.clip(1.0 - 2.0 * (q1 * q1 + q2 * q2), -1.0, 1.0)
    return np.rad2deg(np.arccos(r22))


def matrix(data: dict[str, np.ndarray], prefix: str, count: int) -> np.ndarray:
    return np.vstack([data[f"{prefix}[{i}]"] for i in range(count)]).T.astype(float)


def at_or_before(data: dict[str, np.ndarray] | None, t_us: int | None) -> int | None:
    if data is None or t_us is None or "timestamp" not in data:
        return None
    ts = data["timestamp"].astype(np.int64)
    idx = int(np.searchsorted(ts, int(t_us), side="right") - 1)
    if idx < 0 or idx >= len(ts):
        return None
    return idx


def nearest(data: dict[str, np.ndarray] | None, t_us: int | None) -> int | None:
    if data is None or t_us is None or "timestamp" not in data:
        return None
    ts = data["timestamp"].astype(np.int64)
    pos = int(np.searchsorted(ts, int(t_us)))
    candidates = []
    if pos < len(ts):
        candidates.append(pos)
    if pos > 0:
        candidates.append(pos - 1)
    if not candidates:
        return None
    return min(candidates, key=lambda idx: abs(int(ts[idx]) - int(t_us)))


def state_from_topics(data: dict[str, dict[str, np.ndarray]], t_us: int | None, prefix: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {}
    att = data.get("vehicle_attitude")
    rates = data.get("vehicle_angular_velocity")
    truth_att = data.get("vehicle_attitude_groundtruth")
    truth_rates = data.get("vehicle_angular_velocity_groundtruth")
    lpos = data.get("vehicle_local_position")
    truth_lpos = data.get("vehicle_local_position_groundtruth")
    traj = data.get("trajectory_setpoint")

    def add_att(topic: dict[str, np.ndarray] | None, name: str) -> None:
        idx = nearest(topic, t_us)
        base = f"{prefix}{name}_"
        if topic is None or idx is None:
            for key in ["timestamp_us", "roll_deg", "pitch_deg", "yaw_deg", "tilt_deg", "roll_pitch_abs_deg"]:
                row[base + key] = None
            return
        q = np.array([[float(topic[f"q[{i}]"][idx]) for i in range(4)]])
        roll, pitch, yaw = quat_to_rpy(q)
        row[base + "timestamp_us"] = int(topic["timestamp"][idx])
        row[base + "roll_deg"] = float(np.rad2deg(roll[0]))
        row[base + "pitch_deg"] = float(np.rad2deg(pitch[0]))
        row[base + "yaw_deg"] = float(np.rad2deg(yaw[0]))
        row[base + "tilt_deg"] = float(quat_tilt_deg(q)[0])
        row[base + "roll_pitch_abs_deg"] = max(abs(row[base + "roll_deg"]), abs(row[base + "pitch_deg"]))
        row[base + "trigger_axis"] = "roll" if abs(row[base + "roll_deg"]) >= abs(row[base + "pitch_deg"]) else "pitch"

    def add_rates(topic: dict[str, np.ndarray] | None, name: str) -> None:
        idx = nearest(topic, t_us)
        base = f"{prefix}{name}_"
        if topic is None or idx is None:
            for key in ["timestamp_us", "omega_x", "omega_y", "omega_z", "omega_norm"]:
                row[base + key] = None
            return
        omega = [float(topic[f"xyz[{i}]"][idx]) for i in range(3)]
        row[base + "timestamp_us"] = int(topic["timestamp"][idx])
        row[base + "omega_x"] = omega[0]
        row[base + "omega_y"] = omega[1]
        row[base + "omega_z"] = omega[2]
        row[base + "omega_norm"] = float(math.sqrt(sum(v * v for v in omega)))

    def add_pos(topic: dict[str, np.ndarray] | None, name: str) -> None:
        idx = nearest(topic, t_us)
        base = f"{prefix}{name}_"
        if topic is None or idx is None:
            for key in ["timestamp_us", "x", "y", "z", "vx", "vy", "vz", "v_norm"]:
                row[base + key] = None
            return
        vals = {key: float(topic[key][idx]) for key in ["x", "y", "z", "vx", "vy", "vz"] if key in topic}
        row[base + "timestamp_us"] = int(topic["timestamp"][idx])
        for key in ["x", "y", "z", "vx", "vy", "vz"]:
            row[base + key] = vals.get(key)
        if all(vals.get(key) is not None for key in ["vx", "vy", "vz"]):
            row[base + "v_norm"] = float(math.sqrt(vals["vx"] ** 2 + vals["vy"] ** 2 + vals["vz"] ** 2))
        else:
            row[base + "v_norm"] = None

    add_att(att, "est_att")
    add_att(truth_att, "gt_att")
    add_rates(rates, "est_rate")
    add_rates(truth_rates, "gt_rate")
    add_pos(lpos, "est_pos")
    add_pos(truth_lpos, "gt_pos")

    traj_idx = at_or_before(traj, t_us)
    if traj is not None and traj_idx is not None:
        row[f"{prefix}setpoint_timestamp_us"] = int(traj["timestamp"][traj_idx])
        for i, axis in enumerate("xyz"):
            row[f"{prefix}setpoint_{axis}"] = float(traj[f"position[{i}]"][traj_idx])
        if all(row.get(f"{prefix}est_pos_{axis}") is not None for axis in "xyz"):
            row[f"{prefix}position_error_m"] = float(
                math.sqrt(
                    sum(
                        (float(row[f"{prefix}est_pos_{axis}"]) - float(row[f"{prefix}setpoint_{axis}"])) ** 2
                        for axis in "xyz"
                    )
                )
            )
        else:
            row[f"{prefix}position_error_m"] = None
    else:
        row[f"{prefix}setpoint_timestamp_us"] = None
        for axis in "xyz":
            row[f"{prefix}setpoint_{axis}"] = None
        row[f"{prefix}position_error_m"] = None
    return row


def trigger_from_theta(theta: dict[str, Any]) -> dict[str, Any]:
    return theta.get("setpoint", {}).get("activation_trigger", {}) or {}


def theta_scenario(theta: dict[str, Any]) -> dict[str, Any]:
    sp = theta.get("setpoint", {})
    trig = trigger_from_theta(theta)
    circle = sp.get("circle", {}) if isinstance(sp.get("circle"), dict) else {}
    params = {}
    for key in ["boot_px4_params", "px4_params"]:
        if isinstance(theta.get(key), dict):
            params.update(theta[key])
    wind_n = float(params.get("SIH_WIND_N", theta.get("environment", {}).get("sih_wind_n", 0.0)) or 0.0)
    wind_e = float(params.get("SIH_WIND_E", theta.get("environment", {}).get("sih_wind_e", 0.0)) or 0.0)
    wind = math.sqrt(wind_n * wind_n + wind_e * wind_e)
    return {
        "trigger_rp_min_deg": trig.get("roll_pitch_abs_min_deg"),
        "trigger_rp_max_deg": trig.get("roll_pitch_abs_max_deg"),
        "trigger_rate_min_rad_s": trig.get("angular_rate_norm_min_rad_s"),
        "trigger_rate_max_rad_s": trig.get("angular_rate_norm_max_rad_s"),
        "trigger_start_s": trig.get("start_s"),
        "trigger_deadline_s": trig.get("deadline_s"),
        "trigger_switch_delay_s": trig.get("switch_delay_s", 0.0),
        "max_topic_age_s": trig.get("max_topic_age_s", 0.25),
        "wind_n_m_s": wind_n,
        "wind_e_m_s": wind_e,
        "wind_m_s": wind,
        "radius_m": circle.get("radius_m"),
        "frequency_hz": circle.get("frequency_hz"),
        "phase_rad": circle.get("phase_rad"),
    }


def scenario_key(scenario: dict[str, Any]) -> str:
    keys = [
        "trigger_rp_min_deg",
        "trigger_rp_max_deg",
        "trigger_rate_min_rad_s",
        "trigger_rate_max_rad_s",
        "wind_m_s",
        "radius_m",
        "frequency_hz",
        "phase_rad",
        "trigger_switch_delay_s",
    ]
    return "|".join("na" if scenario.get(key) is None else f"{float(scenario[key]):.6g}" for key in keys)


def task_events(task: dict[str, Any], name: str | None = None) -> list[dict[str, Any]]:
    events = task.get("events") if isinstance(task.get("events"), list) else []
    if name is None:
        return [event for event in events if isinstance(event, dict)]
    return [event for event in events if isinstance(event, dict) and event.get("name") == name]


def event_elapsed(event: dict[str, Any]) -> float | None:
    value = event.get("elapsed_s")
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def ulog_origin_from_task(data: dict[str, dict[str, np.ndarray]], task: dict[str, Any]) -> int | None:
    """Map m1_offboard_task elapsed seconds to ULOG relative timestamps."""
    t_cmd = first_mode_command(data, None)
    final_mode_events = [
        event
        for event in task_events(task, "mode_command")
        if isinstance(event.get("detail"), dict) and event["detail"].get("phase") == "final"
    ]
    if t_cmd is not None and final_mode_events:
        elapsed = event_elapsed(final_mode_events[0])
        if elapsed is not None:
            return int(round(t_cmd - elapsed * 1e6))
    t_nav23 = first_nav_state(data, NAV_EXTERNAL1, None)
    active_events = task_events(task, "controller_active")
    if t_nav23 is not None and active_events:
        elapsed = event_elapsed(active_events[0])
        if elapsed is not None:
            return int(round(t_nav23 - elapsed * 1e6))
    return None


def task_abs_to_ulog(task_timestamp_us: int | None, task: dict[str, Any], ulog_origin_us: int | None) -> int | None:
    if task_timestamp_us is None or ulog_origin_us is None:
        return None
    origin = task.get("origin_us")
    if origin is None:
        return None
    return int(ulog_origin_us + (int(task_timestamp_us) - int(origin)))


def offline_predicate_time(
    data: dict[str, dict[str, np.ndarray]], theta: dict[str, Any], task: dict[str, Any], ulog_origin_us: int | None
) -> tuple[int | None, dict[str, Any] | None]:
    trig = trigger_from_theta(theta)
    if not trig.get("enabled"):
        return None, None
    att = data.get("vehicle_attitude_groundtruth")
    rates = data.get("vehicle_angular_velocity_groundtruth")
    if att is None or rates is None:
        return None, None
    origin = int(ulog_origin_us) if ulog_origin_us is not None else 0
    if origin <= 0:
        return None, None
    start_us = origin + int(float(trig.get("start_s", 0.0)) * 1e6)
    end_us = origin + int(float(trig.get("deadline_s", theta.get("timing", {}).get("controller_switch_s", 0.0))) * 1e6)
    max_age = int(float(trig.get("max_topic_age_s", 0.25)) * 1e6)
    att_ts = att["timestamp"].astype(np.int64)
    rate_ts = rates["timestamp"].astype(np.int64)
    times = np.unique(np.concatenate([att_ts[(att_ts >= start_us) & (att_ts <= end_us)], rate_ts[(rate_ts >= start_us) & (rate_ts <= end_us)]]))
    if len(times) == 0:
        return None, None
    q = matrix(att, "q", 4)
    roll, pitch, yaw = quat_to_rpy(q)
    rp = np.maximum(np.abs(np.rad2deg(roll)), np.abs(np.rad2deg(pitch)))
    omega = matrix(rates, "xyz", 3)
    omega_norm = np.linalg.norm(omega, axis=1)
    for t in times:
        ai = int(np.searchsorted(att_ts, t, side="right") - 1)
        ri = int(np.searchsorted(rate_ts, t, side="right") - 1)
        if ai < 0 or ri < 0:
            continue
        if abs(int(t) - int(att_ts[ai])) > max_age or abs(int(t) - int(rate_ts[ri])) > max_age:
            continue
        value = float(rp[ai])
        rate_value = float(omega_norm[ri])
        if "roll_pitch_abs_min_deg" in trig and value < float(trig["roll_pitch_abs_min_deg"]):
            continue
        if "roll_pitch_abs_max_deg" in trig and value > float(trig["roll_pitch_abs_max_deg"]):
            continue
        if "angular_rate_norm_min_rad_s" in trig and rate_value < float(trig["angular_rate_norm_min_rad_s"]):
            continue
        if "angular_rate_norm_max_rad_s" in trig and rate_value > float(trig["angular_rate_norm_max_rad_s"]):
            continue
        state = {
            "timestamp_us": int(t),
            "attitude_timestamp_us": int(att_ts[ai]),
            "angular_velocity_timestamp_us": int(rate_ts[ri]),
            "roll_deg": float(np.rad2deg(roll[ai])),
            "pitch_deg": float(np.rad2deg(pitch[ai])),
            "yaw_deg": float(np.rad2deg(yaw[ai])),
            "roll_pitch_abs_deg": value,
            "angular_rate_norm_rad_s": rate_value,
        }
        return int(t), state
    return None, None


def first_nav_state(data: dict[str, dict[str, np.ndarray]], nav_state: int, after_us: int | None = None) -> int | None:
    status = data.get("vehicle_status")
    if status is None:
        return None
    ts = status["timestamp"].astype(np.int64)
    nav = status["nav_state"].astype(int)
    mask = nav == nav_state
    if after_us is not None:
        mask &= ts >= int(after_us)
    idx = np.where(mask)[0]
    return int(ts[idx[0]]) if len(idx) else None


def first_mode_command(data: dict[str, dict[str, np.ndarray]], after_us: int | None = None) -> int | None:
    cmd = data.get("vehicle_command")
    if cmd is None:
        return None
    ts = cmd["timestamp"].astype(np.int64)
    mask = cmd["command"].astype(int) == DO_SET_MODE
    if "param2" in cmd:
        mask &= np.isclose(cmd["param2"].astype(float), 4.0, equal_nan=False)
    if "param3" in cmd:
        mask &= cmd["param3"].astype(float) >= 11.0
    if after_us is not None:
        mask &= ts >= int(after_us)
    idx = np.where(mask)[0]
    return int(ts[idx[0]]) if len(idx) else None


def first_command_ack(data: dict[str, dict[str, np.ndarray]], after_us: int | None = None) -> int | None:
    ack = data.get("vehicle_command_ack")
    if ack is None:
        return None
    ts = ack["timestamp"].astype(np.int64)
    mask = ack["command"].astype(int) == DO_SET_MODE
    if after_us is not None:
        mask &= ts >= int(after_us)
    idx = np.where(mask)[0]
    return int(ts[idx[0]]) if len(idx) else None


def analyze_record(rec: EvalRecord) -> dict[str, Any]:
    theta = load_json(rec.theta_path)
    task = load_json(rec.task_path)
    scenario = theta_scenario(theta)
    row: dict[str, Any] = {
        "population": rec.population,
        "campaign": rec.campaign,
        "tag": rec.tag,
        "controller": rec.controller,
        "seed": rec.seed,
        "theta_path": str(rec.theta_path.relative_to(REPO)) if rec.theta_path.is_relative_to(REPO) else str(rec.theta_path),
        "task_path": str(rec.task_path.relative_to(REPO)) if rec.task_path.is_relative_to(REPO) else str(rec.task_path),
        "ulog_path": str(rec.ulog_path.relative_to(REPO)) if rec.ulog_path.is_relative_to(REPO) else str(rec.ulog_path),
        "outcome_severity": rec.outcome_severity,
        "outcome_s3": bool(rec.outcome_severity is not None and rec.outcome_severity >= 3),
        "classical_severity": rec.classical_severity,
        "primary_bug": rec.primary_bug,
        **scenario,
    }
    row["scenario_key"] = scenario_key(scenario)
    try:
        ulog = ULog(str(rec.ulog_path), NEEDED_TOPICS)
        data = datasets(ulog)
        ulog_origin_us = ulog_origin_from_task(data, task)
        t_pred, pred_state = offline_predicate_time(data, theta, task, ulog_origin_us)
        t_cmd = first_mode_command(data, t_pred)
        t_ack = first_command_ack(data, t_cmd)
        t_nav23 = first_nav_state(data, NAV_EXTERNAL1, t_pred)
        harness_trigger_ulog = task_abs_to_ulog(task.get("state_trigger_us"), task, ulog_origin_us)
        harness_active_ulog = task_abs_to_ulog(task.get("controller_active_us"), task, ulog_origin_us)
        row.update(
            {
                "ulog_origin_us": ulog_origin_us,
                "t_pred_us": t_pred,
                "t_cmd_us": t_cmd,
                "t_ack_us": t_ack,
                "t_nav23_us": t_nav23,
                "harness_state_trigger_us": task.get("state_trigger_us"),
                "harness_controller_active_us": task.get("controller_active_us"),
                "harness_state_trigger_ulog_us": harness_trigger_ulog,
                "harness_controller_active_ulog_us": harness_active_ulog,
                "offline_predicate_state": json.dumps(pred_state, sort_keys=True) if pred_state else None,
            }
        )
        for name, a, b in [
            ("L1_cmd_minus_pred_s", t_cmd, t_pred),
            ("L2_nav23_minus_cmd_s", t_nav23, t_cmd),
            ("L_total_nav23_minus_pred_s", t_nav23, t_pred),
            ("ack_minus_cmd_s", t_ack, t_cmd),
            ("nav23_minus_ack_s", t_nav23, t_ack),
            ("harness_trigger_delta_s", harness_trigger_ulog, t_pred),
            ("harness_active_delta_s", harness_active_ulog, t_nav23),
        ]:
            row[name] = (float(int(a) - int(b)) / 1e6) if a is not None and b is not None else None
        if row.get("L1_cmd_minus_pred_s") is not None:
            row["L1_minus_configured_switch_delay_s"] = float(row["L1_cmd_minus_pred_s"]) - float(
                scenario.get("trigger_switch_delay_s") or 0.0
            )
        else:
            row["L1_minus_configured_switch_delay_s"] = None
        row.update(state_from_topics(data, t_pred, "pred_"))
        row.update(state_from_topics(data, t_nav23, "nav23_"))
        for base in ["est_att", "gt_att"]:
            for key in ["roll_pitch_abs_deg", "tilt_deg", "yaw_deg"]:
                a = row.get(f"nav23_{base}_{key}")
                b = row.get(f"pred_{base}_{key}")
                row[f"delta_{base}_{key}"] = float(a) - float(b) if a is not None and b is not None else None
        for base in ["est_rate", "gt_rate"]:
            for key in ["omega_norm", "omega_x", "omega_y", "omega_z"]:
                a = row.get(f"nav23_{base}_{key}")
                b = row.get(f"pred_{base}_{key}")
                row[f"delta_{base}_{key}"] = float(a) - float(b) if a is not None and b is not None else None
        rp = row.get("nav23_est_att_roll_pitch_abs_deg")
        rate = row.get("nav23_est_rate_omega_norm")
        row["nav23_in_label_box"] = (
            rp is not None
            and rate is not None
            and scenario.get("trigger_rp_min_deg") is not None
            and float(scenario["trigger_rp_min_deg"]) <= float(rp) <= float(scenario["trigger_rp_max_deg"])
            and float(scenario["trigger_rate_min_rad_s"]) <= float(rate) <= float(scenario["trigger_rate_max_rad_s"])
        )
        if rp is not None and scenario.get("trigger_rp_min_deg") is not None:
            row["nav23_rp_box_distance_deg"] = max(
                float(scenario["trigger_rp_min_deg"]) - float(rp),
                0.0,
                float(rp) - float(scenario["trigger_rp_max_deg"]),
            )
        else:
            row["nav23_rp_box_distance_deg"] = None
        if rate is not None and scenario.get("trigger_rate_min_rad_s") is not None:
            row["nav23_rate_box_distance_rad_s"] = max(
                float(scenario["trigger_rate_min_rad_s"]) - float(rate),
                0.0,
                float(rate) - float(scenario["trigger_rate_max_rad_s"]),
            )
        else:
            row["nav23_rate_box_distance_rad_s"] = None
        roll = row.get("nav23_est_att_roll_deg")
        pitch = row.get("nav23_est_att_pitch_deg")
        if roll is not None and pitch is not None:
            if abs(float(roll)) >= abs(float(pitch)):
                row["nav23_trigger_axis"] = "roll"
                row["nav23_trigger_axis_value_deg"] = float(roll)
                row["nav23_free_axis_value_deg"] = float(pitch)
            else:
                row["nav23_trigger_axis"] = "pitch"
                row["nav23_trigger_axis_value_deg"] = float(pitch)
                row["nav23_free_axis_value_deg"] = float(roll)
        return row
    except Exception as exc:
        row["analysis_error"] = f"{type(exc).__name__}: {exc}"
        return row


def finite(values: list[Any]) -> np.ndarray:
    out = []
    for value in values:
        if value is None:
            continue
        try:
            f = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            out.append(f)
    return np.array(out, dtype=float)


def qdist(values: list[Any]) -> dict[str, Any]:
    arr = finite(values)
    if len(arr) == 0:
        return {"n": 0, "min": None, "p05": None, "p25": None, "median": None, "p75": None, "p95": None, "max": None}
    return {
        "n": int(len(arr)),
        "min": float(np.min(arr)),
        "p05": float(np.percentile(arr, 5)),
        "p25": float(np.percentile(arr, 25)),
        "median": float(np.percentile(arr, 50)),
        "p75": float(np.percentile(arr, 75)),
        "p95": float(np.percentile(arr, 95)),
        "max": float(np.max(arr)),
    }


def fit_line(x: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    if len(x) < 3 or float(np.var(x)) <= 0.0:
        return {"n": int(len(x)), "slope": None, "intercept": None, "r2": None}
    a, b = np.polyfit(x, y, 1)
    pred = a * x + b
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return {"n": int(len(x)), "slope": float(a), "intercept": float(b), "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else None}


def pair_consistency(rows: list[dict[str, Any]], features: list[str], eps_values: list[float]) -> list[dict[str, Any]]:
    usable = [row for row in rows if all(row.get(key) is not None for key in features) and row.get("outcome_s3") is not None]
    if len(usable) < 2:
        return [{"features": ",".join(features), "epsilon": eps, "pairs": 0, "consistent": 0, "consistency": None} for eps in eps_values]
    x = np.array([[float(row[key]) for key in features] for row in usable], dtype=float)
    std = np.nanstd(x, axis=0)
    std[std <= 1e-12] = 1.0
    z = x / std
    y = np.array([bool(row["outcome_s3"]) for row in usable], dtype=bool)
    out = []
    for eps in eps_values:
        pairs = 0
        consistent = 0
        for i in range(len(z)):
            d = np.linalg.norm(z[i + 1 :] - z[i], axis=1)
            mask = d < eps
            n = int(np.count_nonzero(mask))
            if n == 0:
                continue
            pairs += n
            consistent += int(np.count_nonzero(y[i + 1 :][mask] == y[i]))
        out.append(
            {
                "features": ",".join(features),
                "epsilon_normalized": eps,
                "pairs": pairs,
                "consistent": consistent,
                "consistency": float(consistent / pairs) if pairs else None,
            }
        )
    return out


class TinyTree:
    def __init__(self, max_depth: int = 5, min_leaf: int = 5, rng: np.random.Generator | None = None):
        self.max_depth = max_depth
        self.min_leaf = min_leaf
        self.rng = rng or np.random.default_rng(0)
        self.node: dict[str, Any] | None = None
        self.importance: Counter[int] = Counter()

    @staticmethod
    def gini(y: np.ndarray) -> float:
        if len(y) == 0:
            return 0.0
        p = float(np.mean(y))
        return 2.0 * p * (1.0 - p)

    def build(self, x: np.ndarray, y: np.ndarray, depth: int = 0) -> dict[str, Any]:
        prob = float(np.mean(y)) if len(y) else 0.0
        if depth >= self.max_depth or len(y) < 2 * self.min_leaf or prob in {0.0, 1.0}:
            return {"leaf": True, "prob": prob}
        n_features = x.shape[1]
        feature_count = max(1, int(math.sqrt(n_features)))
        best = None
        parent = self.gini(y)
        for feature in self.rng.choice(n_features, size=feature_count, replace=False):
            values = x[:, feature]
            qs = np.linspace(10, 90, 9)
            thresholds = np.unique(np.percentile(values, qs))
            for threshold in thresholds:
                left = values <= threshold
                right = ~left
                if np.count_nonzero(left) < self.min_leaf or np.count_nonzero(right) < self.min_leaf:
                    continue
                gain = parent - (np.mean(left) * self.gini(y[left]) + np.mean(right) * self.gini(y[right]))
                if best is None or gain > best[0]:
                    best = (float(gain), int(feature), float(threshold), left, right)
        if best is None or best[0] <= 0.0:
            return {"leaf": True, "prob": prob}
        gain, feature, threshold, left, right = best
        self.importance[feature] += gain * len(y)
        return {
            "leaf": False,
            "feature": feature,
            "threshold": threshold,
            "left": self.build(x[left], y[left], depth + 1),
            "right": self.build(x[right], y[right], depth + 1),
        }

    def fit(self, x: np.ndarray, y: np.ndarray) -> "TinyTree":
        self.node = self.build(x, y)
        return self

    def predict_one(self, row: np.ndarray, node: dict[str, Any] | None = None) -> float:
        node = self.node if node is None else node
        assert node is not None
        if node["leaf"]:
            return float(node["prob"])
        if row[node["feature"]] <= node["threshold"]:
            return self.predict_one(row, node["left"])
        return self.predict_one(row, node["right"])

    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.array([self.predict_one(row) for row in x], dtype=float)


class TinyForest:
    def __init__(self, n_estimators: int = 80, max_depth: int = 5, min_leaf: int = 5, seed: int = 0):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_leaf = min_leaf
        self.seed = seed
        self.trees: list[TinyTree] = []
        self.importance: Counter[int] = Counter()

    def fit(self, x: np.ndarray, y: np.ndarray) -> "TinyForest":
        rng = np.random.default_rng(self.seed)
        self.trees = []
        self.importance = Counter()
        for idx in range(self.n_estimators):
            sample = rng.integers(0, len(y), size=len(y))
            tree = TinyTree(self.max_depth, self.min_leaf, np.random.default_rng(self.seed + idx + 1))
            tree.fit(x[sample], y[sample])
            self.trees.append(tree)
            self.importance.update(tree.importance)
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        if not self.trees:
            return np.zeros(len(x))
        return np.mean([tree.predict(x) for tree in self.trees], axis=0)


def balanced_accuracy(y: np.ndarray, pred: np.ndarray) -> float | None:
    if len(np.unique(y)) < 2:
        return None
    tp = np.count_nonzero((y == 1) & (pred == 1))
    tn = np.count_nonzero((y == 0) & (pred == 0))
    fp = np.count_nonzero((y == 0) & (pred == 1))
    fn = np.count_nonzero((y == 1) & (pred == 0))
    tpr = tp / (tp + fn) if (tp + fn) else 0.0
    tnr = tn / (tn + fp) if (tn + fp) else 0.0
    return float(0.5 * (tpr + tnr))


def cv_forest(rows: list[dict[str, Any]], features: list[str], seed: int = 7) -> dict[str, Any]:
    usable = [row for row in rows if all(row.get(key) is not None for key in features)]
    if len(usable) < 10:
        return {"features": features, "n": len(usable), "balanced_accuracy": None, "reason": "too_few_rows"}
    x = np.array([[float(row[key]) for key in features] for row in usable], dtype=float)
    y = np.array([1 if row.get("outcome_s3") else 0 for row in usable], dtype=int)
    if len(np.unique(y)) < 2:
        return {"features": features, "n": len(usable), "balanced_accuracy": None, "reason": "one_class"}
    mean = np.nanmean(x, axis=0)
    std = np.nanstd(x, axis=0)
    std[std <= 1e-12] = 1.0
    x = (x - mean) / std
    rng = np.random.default_rng(seed)
    folds = np.zeros(len(y), dtype=int)
    for cls in [0, 1]:
        idx = np.where(y == cls)[0]
        rng.shuffle(idx)
        for j, item in enumerate(idx):
            folds[item] = j % 5
    preds = np.zeros(len(y), dtype=int)
    importances = np.zeros(len(features), dtype=float)
    for fold in range(5):
        train = folds != fold
        test = ~train
        forest = TinyForest(seed=seed + fold).fit(x[train], y[train])
        preds[test] = forest.predict_proba(x[test]) >= 0.5
        total = sum(forest.importance.values())
        if total:
            for feature, value in forest.importance.items():
                importances[feature] += value / total / 5.0
    return {
        "features": features,
        "n": int(len(y)),
        "positive": int(np.sum(y)),
        "balanced_accuracy": balanced_accuracy(y, preds),
        "feature_importance": {features[i]: float(importances[i]) for i in range(len(features))},
    }


def plot_scatter(rows: list[dict[str, Any]], out: Path, title: str) -> None:
    xs = []
    ys = []
    cs = []
    for row in rows:
        x = row.get("nav23_est_att_roll_pitch_abs_deg")
        y = row.get("nav23_est_rate_omega_norm")
        sev = row.get("outcome_severity")
        if x is None or y is None or sev is None:
            continue
        xs.append(float(x))
        ys.append(float(y))
        cs.append(int(sev))
    if not xs:
        return
    plt.figure(figsize=(7, 5))
    cmap = {0: "#2b8a3e", 1: "#fab005", 2: "#fd7e14", 3: "#c92a2a", 4: "#5f3dc4"}
    for sev in sorted(set(cs)):
        idx = [i for i, value in enumerate(cs) if value == sev]
        plt.scatter([xs[i] for i in idx], [ys[i] for i in idx], s=18, alpha=0.8, label=f"S{sev}", c=cmap.get(sev, "#495057"))
    plt.xlabel("actual roll_pitch_abs at nav23 (deg)")
    plt.ylabel("actual |omega| at nav23 (rad/s)")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out)
    plt.close()


def summarize(rows: list[dict[str, Any]], population: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "population": population,
        "rows": len(rows),
        "analysis_errors": sum(1 for row in rows if row.get("analysis_error")),
        "severity_counts": dict(Counter(str(row.get("outcome_severity")) for row in rows)),
        "delay_distributions_s": {
            "configured_switch_delay_s": qdist([row.get("trigger_switch_delay_s") for row in rows]),
            "L1_cmd_minus_pred_s": qdist([row.get("L1_cmd_minus_pred_s") for row in rows]),
            "L1_minus_configured_switch_delay_s": qdist(
                [row.get("L1_minus_configured_switch_delay_s") for row in rows]
            ),
            "L2_nav23_minus_cmd_s": qdist([row.get("L2_nav23_minus_cmd_s") for row in rows]),
            "L_total_nav23_minus_pred_s": qdist([row.get("L_total_nav23_minus_pred_s") for row in rows]),
            "ack_minus_cmd_s": qdist([row.get("ack_minus_cmd_s") for row in rows]),
            "nav23_minus_ack_s": qdist([row.get("nav23_minus_ack_s") for row in rows]),
        },
        "drift_distributions": {
            "delta_est_att_roll_pitch_abs_deg": qdist([row.get("delta_est_att_roll_pitch_abs_deg") for row in rows]),
            "delta_est_att_tilt_deg": qdist([row.get("delta_est_att_tilt_deg") for row in rows]),
            "delta_est_rate_omega_norm": qdist([row.get("delta_est_rate_omega_norm") for row in rows]),
            "delta_est_att_yaw_deg": qdist([row.get("delta_est_att_yaw_deg") for row in rows]),
        },
        "label_fidelity": {},
    }
    valid_box = [row.get("nav23_in_label_box") for row in rows if row.get("nav23_in_label_box") is not None]
    summary["label_fidelity"]["in_box_count"] = int(sum(1 for v in valid_box if v))
    summary["label_fidelity"]["in_box_denominator"] = len(valid_box)
    summary["label_fidelity"]["in_box_fraction"] = float(sum(1 for v in valid_box if v) / len(valid_box)) if valid_box else None
    summary["label_fidelity"]["rp_box_distance_deg"] = qdist([row.get("nav23_rp_box_distance_deg") for row in rows])
    summary["label_fidelity"]["rate_box_distance_rad_s"] = qdist([row.get("nav23_rate_box_distance_rad_s") for row in rows])
    summary["label_fidelity"]["trigger_axis_counts"] = dict(Counter(row.get("nav23_trigger_axis") for row in rows if row.get("nav23_trigger_axis")))
    summary["label_fidelity"]["free_axis_abs_deg"] = qdist([abs(float(row["nav23_free_axis_value_deg"])) for row in rows if row.get("nav23_free_axis_value_deg") is not None])
    for key in ["nav23_est_att_yaw_deg", "nav23_est_pos_v_norm", "nav23_position_error_m"]:
        summary["label_fidelity"][key] = qdist([row.get(key) for row in rows])
    x = []
    y_tilt = []
    y_rp = []
    for row in rows:
        omega = row.get("pred_est_rate_omega_norm") or row.get("pred_gt_rate_omega_norm")
        delay = row.get("L_total_nav23_minus_pred_s")
        if omega is not None and delay is not None:
            x.append(float(omega) * float(delay) * 180.0 / math.pi)
            y_tilt.append(abs(float(row["delta_est_att_tilt_deg"])) if row.get("delta_est_att_tilt_deg") is not None else math.nan)
            y_rp.append(abs(float(row["delta_est_att_roll_pitch_abs_deg"])) if row.get("delta_est_att_roll_pitch_abs_deg") is not None else math.nan)
    summary["omega_delay_fit"] = {
        "x_units": "pred_est_omega_norm_rad_s * L_total_s converted to degrees",
        "abs_delta_tilt": fit_line(np.array(x), np.array(y_tilt)),
        "abs_delta_roll_pitch_abs": fit_line(np.array(x), np.array(y_rp)),
    }
    base_features = ["nav23_est_att_roll_pitch_abs_deg", "nav23_est_rate_omega_norm"]
    consistency = pair_consistency(rows, base_features, [0.5, 1.0, 2.0, 3.0, 5.0])
    summary["local_consistency"] = consistency
    feature_sets = [
        base_features,
        base_features + ["nav23_est_att_yaw_deg"],
        base_features + ["nav23_est_rate_omega_x", "nav23_est_rate_omega_y", "nav23_est_rate_omega_z"],
        ["nav23_est_att_roll_deg", "nav23_est_att_pitch_deg", "nav23_est_rate_omega_x", "nav23_est_rate_omega_y", "nav23_est_rate_omega_z"],
        [
            "nav23_est_att_roll_deg",
            "nav23_est_att_pitch_deg",
            "nav23_est_att_yaw_deg",
            "nav23_est_rate_omega_x",
            "nav23_est_rate_omega_y",
            "nav23_est_rate_omega_z",
            "nav23_est_pos_v_norm",
            "nav23_position_error_m",
        ],
        [
            "nav23_est_att_roll_deg",
            "nav23_est_att_pitch_deg",
            "nav23_est_att_yaw_deg",
            "nav23_est_rate_omega_x",
            "nav23_est_rate_omega_y",
            "nav23_est_rate_omega_z",
            "nav23_est_pos_v_norm",
            "nav23_position_error_m",
            "wind_m_s",
            "radius_m",
            "frequency_hz",
        ],
    ]
    summary["classifiers"] = [cv_forest(rows, features) for features in feature_sets]
    groups: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("scenario_key")), row.get("seed"))].append(row)
    pair_total = 0
    pair_same = 0
    repeated = []
    for (key, seed), items in groups.items():
        if len(items) < 2:
            continue
        outcomes = [bool(item.get("outcome_s3")) for item in items]
        total = len(outcomes) * (len(outcomes) - 1) // 2
        same = sum(1 for i in range(len(outcomes)) for j in range(i + 1, len(outcomes)) if outcomes[i] == outcomes[j])
        pair_total += total
        pair_same += same
        repeated.append(
            {
                "scenario_key": key,
                "seed": seed,
                "n": len(items),
                "s3_count": int(sum(outcomes)),
                "pair_consistency": float(same / total) if total else None,
                "tags": [item.get("tag") for item in items],
            }
        )
    summary["repeatability"] = {
        "same_scenario_same_seed_groups": repeated,
        "pair_total": pair_total,
        "pair_same": pair_same,
        "pair_consistency": float(pair_same / pair_total) if pair_total else None,
    }
    return summary


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def collect_speed_factors() -> dict[str, Any]:
    values = []
    for path in list((REPO / "runs").rglob("*_task.json")) + list((REPO / "docs").rglob("*_task.json")):
        try:
            data = load_json(path)
        except Exception:
            continue
        if "sim_speed_factor" in data:
            values.append({"path": str(path.relative_to(REPO)), "sim_speed_factor": data.get("sim_speed_factor")})
    metadata = []
    for path in (REPO / "runs/campaigns").glob("*/metadata.json"):
        data = load_json(path)
        if "sim_speed_factor" in data:
            metadata.append({"path": str(path.relative_to(REPO)), "sim_speed_factor": data.get("sim_speed_factor")})
    return {
        "task_json_count": len(values),
        "task_speed_counts": dict(Counter(str(v["sim_speed_factor"]) for v in values)),
        "campaign_metadata": metadata,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", choices=["mcnn_dense", "mcnn_search", "mcnn_all", "raptor_v8", "all"], default="mcnn_dense")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    out_dir = args.output_dir
    records = collect_records(args.population)
    if args.limit:
        records = records[: args.limit]
    if args.workers > 1 and len(records) > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            rows = list(executor.map(analyze_record, records))
    else:
        rows = [analyze_record(record) for record in records]
    prefix = args.population
    write_csv(out_dir / f"{prefix}_delivered_state.csv", rows)
    summary = summarize(rows, args.population)
    summary["record_count_collected"] = len(records)
    summary["commands"] = {
        "script": "python3 scripts/px4_delivered_state_round5.py",
        "this_run": f"python3 scripts/px4_delivered_state_round5.py --population {args.population} --workers {args.workers}",
    }
    write_json(out_dir / f"{prefix}_summary.json", summary)
    write_json(out_dir / "speed_factor_summary.json", collect_speed_factors())
    plot_scatter(rows, out_dir / f"{prefix}_actual_nav23_scatter.png", f"{args.population}: delivered nav23 state")
    print(
        json.dumps(
            {
                "population": args.population,
                "records": len(records),
                "rows": len(rows),
                "analysis_errors": summary["analysis_errors"],
                "csv": str(out_dir / f"{prefix}_delivered_state.csv"),
                "summary": str(out_dir / f"{prefix}_summary.json"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
