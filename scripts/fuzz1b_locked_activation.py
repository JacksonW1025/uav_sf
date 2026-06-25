#!/usr/bin/env python3
"""FUZZ-1b locked differential check for mc_nn violent activation.

This runner uses Method A from the FUZZ-1b prompt: state-triggered switching on
SIH groundtruth attitude/rate. SIH has no built-in full-state snapshot/restore
API, so the trigger residual is measured and reported explicitly.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
from pyulog import ULog

import fuzz1_activation_mcnn as fuzz1
import m1_diff_runner as m1
import mcnn_gate3_position_error_probe as gate3
from m1_metrics import quaternion, quat_to_roll_pitch, vector3


RUN_ID = "fuzz1b_locked_20260625"


@dataclass(frozen=True)
class LockedCase:
    tag: str
    roll_pitch_min_deg: float
    roll_pitch_max_deg: float
    rate_min_rad_s: float
    rate_max_rad_s: float
    radius_m: float = 6.0
    frequency_hz: float = 0.45
    phase_rad: float = 0.0
    wind_n: float = 6.0
    wind_e: float = 0.0
    setup_profile: str = "relaxed_limits"
    trigger_start_s: float = 20.0
    trigger_deadline_s: float = 38.0
    trajectory_start_s: float = 16.0
    mission_end_s: float = 52.0
    stage: str = "target_2p6"


SCAN_CASES = [
    LockedCase("target_rp48_62_rate2p45_2p85", 48.0, 62.0, 2.45, 2.85, stage="target_2p6"),
    LockedCase("scan_rp45_65_rate2p20_2p60", 45.0, 65.0, 2.20, 2.60, stage="scan_down"),
    LockedCase("scan_rp40_65_rate1p80_2p30", 40.0, 65.0, 1.80, 2.30, stage="scan_down"),
    LockedCase("scan_rp35_65_rate1p40_1p90", 35.0, 65.0, 1.40, 1.90, stage="scan_down"),
    LockedCase("scan_rp30_65_rate1p00_1p50", 30.0, 65.0, 1.00, 1.50, stage="scan_down"),
    LockedCase("easy_rp25_65_rate0p65_1p10", 25.0, 65.0, 0.65, 1.10, stage="scan_down"),
]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    fuzz1.write_json(path, payload)


def expected_tilt_deg(case: LockedCase) -> float:
    lateral_accel = case.radius_m * (2.0 * math.pi * case.frequency_hz) ** 2
    return math.degrees(math.atan2(lateral_accel, 9.80665))


def theta_for_case(run_id: str, case: LockedCase, seed: int) -> dict[str, Any]:
    tag = f"{run_id}_{case.tag}_s{seed}"
    boot_params = dict(fuzz1.COMMON_BOOT_PARAMS)
    if case.wind_n or case.wind_e:
        boot_params["SIH_WIND_N"] = case.wind_n
        boot_params["SIH_WIND_E"] = case.wind_e
    return {
        "tag": tag,
        "description": (
            "FUZZ-1b mc_nn_control locked differential: classical Offboard circle approach, "
            "SIH groundtruth state-triggered switch, post-switch hover recovery."
        ),
        "seed": int(seed),
        "airframe": {"sim": "sih", "model": "sihsim_x500_v2", "sys_autostart": 10046},
        "timing": {
            "approach_start_s": 12.0,
            "controller_switch_s": case.trigger_deadline_s,
            "trajectory_start_s": case.trajectory_start_s,
            "mission_end_s": case.mission_end_s,
            "mode_command_repeat_s": 0.5,
            "mode_command_timeout_s": 8.0,
            "px4_shutdown_margin_s": 8.0,
            "px4_shutdown_wall_slack_s": 22.0,
            "external_mode_id": 23,
        },
        "setpoint": {
            "rate_hz": 80.0,
            "max_wall_timer_hz": 800.0,
            "hover_ned": [0.0, 0.0, -2.5],
            "yaw_rad": 0.0,
            "type": "circle",
            "feedforward": True,
            "circle": {
                "radius_m": case.radius_m,
                "frequency_hz": case.frequency_hz,
                "phase_rad": case.phase_rad,
                "z_amplitude_m": 0.0,
            },
            "activation_trigger": {
                "enabled": True,
                "method": "SIH groundtruth threshold crossing",
                "start_s": case.trigger_start_s,
                "deadline_s": case.trigger_deadline_s,
                "roll_pitch_abs_min_deg": case.roll_pitch_min_deg,
                "roll_pitch_abs_max_deg": case.roll_pitch_max_deg,
                "angular_rate_norm_min_rad_s": case.rate_min_rad_s,
                "angular_rate_norm_max_rad_s": case.rate_max_rad_s,
                "max_topic_age_s": 0.25,
            },
            "post_switch": {
                "type": "hover",
                "hover_ned": [0.0, 0.0, -2.5],
            },
        },
        "boot_px4_params": boot_params,
        "px4_params": {**fuzz1.COMMON_PX4_PARAMS, **fuzz1.setup_params(case.setup_profile)},
        "environment": {
            "fuzz_family": "violent_activation_locked",
            "state_control_method": "A_state_triggered_switch",
            "sih_state_api_probe": (
                "PX4 simulator_sih has private dynamics state and no built-in snapshot/restore/direct-state API; "
                "Method A is used and residuals are quantified."
            ),
            "case": asdict(case),
            "expected_lateral_accel_m_s2": case.radius_m * (2.0 * math.pi * case.frequency_hz) ** 2,
            "expected_tilt_deg": expected_tilt_deg(case),
            "reachability": (
                "Classical Offboard circle approach plus SIH wind creates the switch state. "
                "Relaxed limits, when used, are IC setup only and are reported explicitly."
            ),
            "uses_state_shim": False,
        },
        "faults": [],
        "sensor_perturbations": [],
        "safe_thresholds": {
            "tracking_error_max_m": 8.0,
            "tracking_error_rms_m": 4.0,
            "final_error_m": 4.0,
            "roll_pitch_max_deg": 75.0,
            "angular_rate_max_rad_s": 8.0,
            "motor_saturation_ratio_max": 0.99,
            "min_altitude_agl_m": 0.25,
        },
        "divergence_thresholds": {"position_divergence_m": 2.0},
    }


def first_dataset(ulog: ULog, name: str):
    matches = [dataset for dataset in ulog.data_list if dataset.name == name]
    return matches[0] if matches else None


def nearest_index(timestamps: np.ndarray, target_us: int) -> int | None:
    if len(timestamps) == 0:
        return None
    idx = int(np.searchsorted(timestamps, target_us))
    candidates = [max(0, min(len(timestamps) - 1, idx))]
    if idx > 0:
        candidates.append(idx - 1)
    if idx + 1 < len(timestamps):
        candidates.append(idx + 1)
    return min(candidates, key=lambda item: abs(int(timestamps[item]) - target_us))


def exact_switch_state(ulog: ULog, switch_us: int | None) -> dict[str, Any]:
    state: dict[str, Any] = {"switch_us": switch_us}
    if switch_us is None:
        return state

    att = first_dataset(ulog, "vehicle_attitude_groundtruth") or first_dataset(ulog, "vehicle_attitude")
    rates = first_dataset(ulog, "vehicle_angular_velocity_groundtruth") or first_dataset(ulog, "vehicle_angular_velocity")
    lpos = first_dataset(ulog, "vehicle_local_position_groundtruth") or first_dataset(ulog, "vehicle_local_position")

    if att is not None:
        ts = att.data["timestamp"].astype(np.int64)
        idx = nearest_index(ts, switch_us)
        if idx is not None:
            q = quaternion(att.data)[idx : idx + 1]
            roll, pitch = quat_to_roll_pitch(q)
            state.update(
                {
                    "attitude_topic": att.name,
                    "attitude_timestamp_us": int(ts[idx]),
                    "attitude_dt_ms": float((int(ts[idx]) - switch_us) / 1000.0),
                    "roll_deg": float(np.rad2deg(roll[0])),
                    "pitch_deg": float(np.rad2deg(pitch[0])),
                    "roll_pitch_abs_deg": float(np.rad2deg(max(abs(roll[0]), abs(pitch[0])))),
                }
            )

    if rates is not None:
        ts = rates.data["timestamp"].astype(np.int64)
        idx = nearest_index(ts, switch_us)
        if idx is not None:
            omega = vector3(rates.data, "xyz")[idx]
            state.update(
                {
                    "angular_velocity_topic": rates.name,
                    "angular_velocity_timestamp_us": int(ts[idx]),
                    "angular_velocity_dt_ms": float((int(ts[idx]) - switch_us) / 1000.0),
                    "angular_rate_xyz_rad_s": [float(value) for value in omega.tolist()],
                    "angular_rate_norm_rad_s": float(np.linalg.norm(omega)),
                    "roll_rate_abs_rad_s": float(abs(omega[0])),
                    "pitch_rate_abs_rad_s": float(abs(omega[1])),
                    "yaw_rate_abs_rad_s": float(abs(omega[2])),
                }
            )

    if lpos is not None:
        ts = lpos.data["timestamp"].astype(np.int64)
        idx = nearest_index(ts, switch_us)
        if idx is not None:
            velocity = [float(lpos.data[field][idx]) for field in ["vx", "vy", "vz"] if field in lpos.data]
            position = [float(lpos.data[field][idx]) for field in ["x", "y", "z"] if field in lpos.data]
            state.update(
                {
                    "local_position_topic": lpos.name,
                    "local_position_timestamp_us": int(ts[idx]),
                    "local_position_dt_ms": float((int(ts[idx]) - switch_us) / 1000.0),
                    "position_ned_m": position,
                    "velocity_ned_m_s": velocity,
                    "velocity_norm_m_s": float(np.linalg.norm(velocity)) if len(velocity) == 3 else None,
                }
            )
    return state


def matched_switch_us_from_trigger(ulog: ULog, trigger_state: dict[str, Any] | None) -> tuple[int | None, dict[str, Any]]:
    if not trigger_state:
        return None, {"matched": False, "reason": "missing_trigger_state"}
    att = first_dataset(ulog, "vehicle_attitude_groundtruth") or first_dataset(ulog, "vehicle_attitude")
    rates = first_dataset(ulog, "vehicle_angular_velocity_groundtruth") or first_dataset(ulog, "vehicle_angular_velocity")
    if att is None or rates is None:
        return None, {"matched": False, "reason": "missing_groundtruth_topics"}

    ats = att.data["timestamp"].astype(np.int64)
    rts = rates.data["timestamp"].astype(np.int64)
    q = quaternion(att.data)
    roll, pitch = quat_to_roll_pitch(q)
    omega = vector3(rates.data, "xyz")
    omega_at_att = np.column_stack([np.interp(ats, rts, omega[:, idx]) for idx in range(3)])

    target_roll = math.radians(float(trigger_state["roll_deg"]))
    target_pitch = math.radians(float(trigger_state["pitch_deg"]))
    target_omega = np.asarray(trigger_state["angular_rate_xyz_rad_s"], dtype=float)
    score = (
        np.abs(roll - target_roll) / math.radians(1.0)
        + np.abs(pitch - target_pitch) / math.radians(1.0)
        + np.linalg.norm(omega_at_att - target_omega, axis=1) / 0.05
    )
    idx = int(np.nanargmin(score))
    match = {
        "matched": True,
        "switch_us": int(ats[idx]),
        "score": float(score[idx]),
        "roll_error_deg": float(abs(math.degrees(float(roll[idx]) - target_roll))),
        "pitch_error_deg": float(abs(math.degrees(float(pitch[idx]) - target_pitch))),
        "angular_rate_error_norm_rad_s": float(np.linalg.norm(omega_at_att[idx] - target_omega)),
    }
    return int(ats[idx]), match


def nav_active_us(ulog: ULog, nav_state: int, after_us: int) -> int | None:
    status = first_dataset(ulog, "vehicle_status")
    if status is None or "nav_state" not in status.data:
        return None
    ts = status.data["timestamp"].astype(np.int64)
    nav = status.data["nav_state"].astype(int)
    idx = np.where((ts >= after_us) & (nav == nav_state))[0]
    if len(idx) == 0:
        return None
    return int(ts[int(idx[0])])


def detector_with_switch(
    outputs: dict[str, Path],
    controller: str,
    theta: dict[str, Any],
    safety_config: Path,
    switch_us: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ulog = ULog(str(outputs["ulog"]))
    mission_end_us = int(ulog.last_timestamp)
    target_nav = 23 if controller == "mcnn" else 14
    active_us = nav_active_us(ulog, target_nav, switch_us)
    analysis_start_us = active_us if controller == "mcnn" and active_us is not None else switch_us
    context = fuzz1.switch_context(ulog, switch_us, mission_end_us, active_us)
    detector: dict[str, Any] = {
        "controller": controller,
        "hit": False,
        "severity": 0,
        "severity_label": "none",
        "hit_reasons": [],
        "tracking_only_reasons_ignored": [],
        "console": fuzz1.console_faults(Path(outputs["console"])),
        "source_map": {
            "observation": "mc_nn_control.cpp PopulateInputTensor() fills _input_data; neural_control.cpp publish loop copies it.",
            "network_output": "mc_nn_control.cpp RescaleActions() mutates output tensor before neural_control.network_output publish.",
            "actuator_motors": "mc_nn_control.cpp PublishOutput() writes active actuator_motors.control[0..3].",
        },
        "analysis_start_us": analysis_start_us,
        "switch_us_source": "matched_groundtruth_state",
    }
    if detector["console"]["fault"]:
        detector["hit_reasons"].append("px4_console_fault")
        detector["severity"] = max(detector["severity"], 4)

    neural = first_dataset(ulog, "neural_control")
    if neural is not None and controller == "mcnn":
        nts = neural.data["timestamp"].astype(np.int64)
        nmask = fuzz1.mask_window(nts, analysis_start_us, mission_end_us)
        detector["neural_control_samples"] = int(np.count_nonzero(nmask))
        network = fuzz1.field_matrix(neural, "network_output", 4, nmask)
        observation = fuzz1.field_matrix(neural, "observation", 15, nmask)
        detector["network_output_nonfinite"] = fuzz1.nonfinite_summary(network, nts[nmask] if np.any(nmask) else None)
        detector["observation_nonfinite"] = fuzz1.nonfinite_summary(observation, nts[nmask] if np.any(nmask) else None)
        if detector["network_output_nonfinite"]["nonfinite_count"]:
            detector["hit_reasons"].append("neural_control_network_output_nonfinite")
            detector["severity"] = max(detector["severity"], 4)
    elif controller == "mcnn":
        detector["hit_reasons"].append("missing_neural_control_topic")
        detector["severity"] = max(detector["severity"], 2)

    motors = first_dataset(ulog, "actuator_motors")
    if motors is not None:
        mts = motors.data["timestamp"].astype(np.int64)
        mmask = fuzz1.mask_window(mts, analysis_start_us, mission_end_us)
        active = fuzz1.field_matrix(motors, "control", fuzz1.ACTIVE_MOTORS, mmask)
        detector["active_motor_nonfinite"] = fuzz1.nonfinite_summary(active, mts[mmask] if np.any(mmask) else None)
        if detector["active_motor_nonfinite"]["nonfinite_count"]:
            detector["hit_reasons"].append("actuator_motors_active_nonfinite")
            detector["severity"] = max(detector["severity"], 4)
        if active is not None and active.size:
            finite = np.isfinite(active)
            finite_count = int(np.count_nonzero(finite))
            if finite_count:
                sat = finite & ((active <= 0.02) | (active >= 0.98) | (np.abs(active) >= 0.98))
                detector["active_motor_saturation_ratio"] = float(np.count_nonzero(sat)) / float(finite_count)
                detector["active_motor_saturation_count"] = int(np.count_nonzero(sat))
                if detector["active_motor_saturation_ratio"] > theta.get("safe_thresholds", {}).get(
                    "motor_saturation_ratio_max", 0.99
                ):
                    detector["hit_reasons"].append("motor_saturation")
                    detector["severity"] = max(detector["severity"], 2)

    status = first_dataset(ulog, "vehicle_status")
    if status is not None:
        sts = status.data["timestamp"].astype(np.int64)
        smask = fuzz1.mask_window(sts, switch_us, mission_end_us)
        if np.any(smask):
            disarmed = bool(np.any(status.data["arming_state"].astype(int)[smask] != 2))
            failsafe = bool(np.any(status.data["failsafe"].astype(bool)[smask]))
            detector["post_switch_disarmed"] = disarmed
            detector["post_switch_failsafe"] = failsafe
            if disarmed:
                detector["hit_reasons"].append("unexpected_disarm")
                detector["severity"] = max(detector["severity"], 2)
            if failsafe:
                detector["hit_reasons"].append("failsafe")
                detector["severity"] = max(detector["severity"], 2)

    if (
        context.get("post_switch_roll_pitch_max_deg") is not None
        and context["post_switch_roll_pitch_max_deg"] > theta.get("safe_thresholds", {}).get("roll_pitch_max_deg", 75.0)
    ):
        detector["hit_reasons"].append("attitude_loss_of_control")
        detector["severity"] = max(detector["severity"], 3)
    if (
        context.get("post_switch_angular_rate_max_rad_s") is not None
        and context["post_switch_angular_rate_max_rad_s"]
        > theta.get("safe_thresholds", {}).get("angular_rate_max_rad_s", 8.0)
    ):
        detector["hit_reasons"].append("angular_rate_loss_of_control")
        detector["severity"] = max(detector["severity"], 3)
    if (
        context.get("post_switch_min_altitude_agl_m") is not None
        and context["post_switch_min_altitude_agl_m"] < theta.get("safe_thresholds", {}).get("min_altitude_agl_m", 0.25)
    ):
        detector["hit_reasons"].append("ground_contact_post_switch")
        detector["severity"] = max(detector["severity"], 2)

    detector["hit_reasons"] = sorted(set(detector["hit_reasons"]))
    detector["hit"] = detector["severity"] > 0
    detector["severity_label"] = {0: "none", 2: "medium", 3: "high", 4: "highest"}.get(
        detector["severity"], "unknown"
    )
    return detector, context


def task_event_us(task: dict[str, Any], name: str) -> int | None:
    for event in task.get("events", []):
        if event.get("name") == name and isinstance(event.get("timestamp_us"), int):
            return int(event["timestamp_us"])
    return None


def task_event(task: dict[str, Any], name: str) -> dict[str, Any] | None:
    for event in task.get("events", []):
        if event.get("name") == name:
            return event
    return None


def augment_record(record: dict[str, Any], outputs: dict[str, Path]) -> None:
    task = load_json(Path(outputs["task"]))
    record["state_trigger"] = {
        "enabled": bool(task.get("state_trigger_enabled")),
        "fired": bool(task.get("state_trigger_fired")),
        "state": task.get("state_trigger_state"),
        "max_observed": task.get("state_trigger_max_observed"),
        "event": task_event(task, "state_trigger"),
        "timeout_event": task_event(task, "state_trigger_timeout"),
    }
    try:
        ulog = ULog(str(outputs["ulog"]))
        switch_us, match = matched_switch_us_from_trigger(ulog, task.get("state_trigger_state"))
        if switch_us is None:
            switch_us = task_event_us(task, "post_switch_setpoint") or task_event_us(task, "state_trigger")
        record["trigger_ulog_match"] = match
        record["exact_switch_state"] = exact_switch_state(ulog, switch_us)
    except Exception as exc:
        record["trigger_ulog_match"] = {"matched": False, "error": repr(exc)}
        record["exact_switch_state"] = {"switch_us": None, "error": repr(exc)}


def run_controller_eval(
    repo: Path,
    docs: Path,
    run_id: str,
    case: LockedCase,
    seed: int,
    controller: str,
    env: dict[str, str],
    run_timeout: int,
    safety_config: Path,
) -> dict[str, Any]:
    theta = theta_for_case(run_id, case, seed)
    eval_dir = docs / "evals" / theta["tag"]
    eval_dir.mkdir(parents=True, exist_ok=True)
    theta_path = eval_dir / f"{theta['tag']}.json"
    write_json(theta_path, theta)
    print(f"RUN_CONTROLLER={controller} CASE={case.tag} SEED={seed}", flush=True)
    try:
        outputs = gate3.run_one(repo, theta_path, theta, controller, eval_dir, env, run_timeout, safety_config)
        record = fuzz1.analyze_run(outputs, controller, theta, safety_config)
        augment_record(record, outputs)
        switch_us = record.get("exact_switch_state", {}).get("switch_us")
        if isinstance(switch_us, int):
            detector, context = detector_with_switch(outputs, controller, theta, safety_config, switch_us)
            record["detector"] = detector
            record["switch_context"] = context
        record["run_error"] = None
    except Exception as exc:
        prefix = f"mcnn_gate3_{theta['tag']}_{controller}"
        console = eval_dir / f"{prefix}_px4_console.log"
        record = {
            "controller": controller,
            "outputs": {"console": str(console)},
            "metrics": {},
            "detector": {
                "controller": controller,
                "hit": False,
                "severity": 0,
                "severity_label": "harness_error",
                "hit_reasons": [],
                "console": fuzz1.console_faults(console),
                "harness_exception": repr(exc),
            },
            "switch_context": {},
            "state_trigger": {"enabled": True, "fired": False, "error": repr(exc)},
            "exact_switch_state": {},
            "run_error": repr(exc),
        }
    record["theta"] = theta
    record["case"] = asdict(case)
    record["seed"] = int(seed)
    record["tag"] = theta["tag"]
    write_json(eval_dir / f"{controller}_record.json", record)
    return record


def state_residual(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    def diff(key: str) -> float | None:
        av = a.get(key)
        bv = b.get(key)
        if av is None or bv is None:
            return None
        return abs(float(av) - float(bv))

    residual = {
        "roll_pitch_abs_deg": diff("roll_pitch_abs_deg"),
        "roll_deg": diff("roll_deg"),
        "pitch_deg": diff("pitch_deg"),
        "angular_rate_norm_rad_s": diff("angular_rate_norm_rad_s"),
        "velocity_norm_m_s": diff("velocity_norm_m_s"),
    }
    if a.get("angular_rate_xyz_rad_s") and b.get("angular_rate_xyz_rad_s"):
        residual["angular_rate_xyz_abs_rad_s"] = [
            abs(float(av) - float(bv))
            for av, bv in zip(a["angular_rate_xyz_rad_s"], b["angular_rate_xyz_rad_s"])
        ]
    if a.get("velocity_ned_m_s") and b.get("velocity_ned_m_s"):
        residual["velocity_ned_abs_m_s"] = [
            abs(float(av) - float(bv)) for av, bv in zip(a["velocity_ned_m_s"], b["velocity_ned_m_s"])
        ]
    residual["within_method_a_tolerance"] = (
        residual["roll_pitch_abs_deg"] is not None
        and residual["roll_pitch_abs_deg"] <= 8.0
        and residual["angular_rate_norm_rad_s"] is not None
        and residual["angular_rate_norm_rad_s"] <= 0.45
    )
    return residual


def classify_locked_pair(mcnn_record: dict[str, Any], classical_record: dict[str, Any]) -> dict[str, Any]:
    base = fuzz1.classify_pair(mcnn_record, classical_record)
    residual = state_residual(
        mcnn_record.get("exact_switch_state", {}),
        classical_record.get("exact_switch_state", {}),
    )
    both_triggered = bool(mcnn_record.get("state_trigger", {}).get("fired")) and bool(
        classical_record.get("state_trigger", {}).get("fired")
    )
    locked = bool(base["mcnn_hit"]) and not bool(base["classical_hit"]) and both_triggered and bool(
        residual["within_method_a_tolerance"]
    )
    too_hard = bool(base["mcnn_hit"]) and bool(base["classical_hit"]) and both_triggered
    return {
        **base,
        "both_triggered": both_triggered,
        "state_residual": residual,
        "locked_differential": locked,
        "too_hard": too_hard,
    }


def append_jsonl(path: Path, payload: Any) -> None:
    fuzz1.append_jsonl(path, payload)


def compact_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "controller": record.get("controller"),
        "tag": record.get("tag"),
        "seed": record.get("seed"),
        "case": record.get("case", {}).get("tag"),
        "stage": record.get("case", {}).get("stage"),
        "run_error": record.get("run_error"),
        "detector": record.get("detector"),
        "switch_context": record.get("switch_context"),
        "state_trigger": record.get("state_trigger"),
        "trigger_ulog_match": record.get("trigger_ulog_match"),
        "exact_switch_state": record.get("exact_switch_state"),
        "outputs": record.get("outputs"),
    }


def summarize_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pair_count": len(pairs),
        "locked_count": sum(1 for pair in pairs if pair["classification"].get("locked_differential")),
        "too_hard_count": sum(1 for pair in pairs if pair["classification"].get("too_hard")),
        "both_triggered_count": sum(1 for pair in pairs if pair["classification"].get("both_triggered")),
        "rate_residual_mean_rad_s": mean(
            [
                pair["classification"]["state_residual"]["angular_rate_norm_rad_s"]
                for pair in pairs
                if pair["classification"]["state_residual"].get("angular_rate_norm_rad_s") is not None
            ]
        )
        if any(
            pair["classification"]["state_residual"].get("angular_rate_norm_rad_s") is not None for pair in pairs
        )
        else None,
    }


def write_summary(docs: Path, payload: dict[str, Any]) -> None:
    decision = payload["decision"]
    lines = [
        f"decision: {decision['status']}",
        "",
        "# FUZZ-1b Locked Differential",
        "",
        f"run_id: `{payload['run_id']}`",
        "state_control_method: Method A, SIH groundtruth state-triggered switch",
        "sih_snapshot_restore_probe: no built-in simulator_sih snapshot/restore/direct-state API found; residuals are quantified.",
        "",
        "## Decision",
        "",
        decision.get("rationale", ""),
        "",
        "## Pairs",
        "",
        "| idx | case | seed | both triggered | locked | too hard | mc_nn hit | classical hit | mc_nn rp/rate | classical rp/rate | rate residual | reasons |",
        "|---:|---|---:|---|---|---|---|---|---:|---:|---:|---|",
    ]
    for idx, pair in enumerate(payload.get("pairs", []), start=1):
        cls = pair["classification"]
        m_state = pair["mcnn"].get("exact_switch_state", {})
        c_state = pair["classical"].get("exact_switch_state", {})
        lines.append(
            "| {idx} | {case} | {seed} | {both} | {locked} | {too_hard} | {mhit} | {chit} | {mrp}/{mrate} | {crp}/{crate} | {resid} | {reasons} |".format(
                idx=idx,
                case=pair["mcnn"].get("case"),
                seed=pair["mcnn"].get("seed"),
                both=str(cls.get("both_triggered")).lower(),
                locked=str(cls.get("locked_differential")).lower(),
                too_hard=str(cls.get("too_hard")).lower(),
                mhit=str(cls.get("mcnn_hit")).lower(),
                chit=str(cls.get("classical_hit")).lower(),
                mrp=m_state.get("roll_pitch_abs_deg"),
                mrate=m_state.get("angular_rate_norm_rad_s"),
                crp=c_state.get("roll_pitch_abs_deg"),
                crate=c_state.get("angular_rate_norm_rad_s"),
                resid=cls.get("state_residual", {}).get("angular_rate_norm_rad_s"),
                reasons=";".join(cls.get("mcnn_reasons") or []),
            )
        )
    lines.extend(
        [
            "",
            "## Reachability",
            "",
            payload.get("reachability", ""),
            "",
            "## Artifacts",
            "",
            f"results_json: `{docs / 'results.json'}`",
            f"eval_dir: `{docs / 'evals'}`",
        ]
    )
    text = "\n".join(lines) + "\n"
    (docs / "summary.md").write_text(text, encoding="utf-8")
    (docs.parent / f"{payload['run_id']}.md").write_text(text, encoding="utf-8")


def build_if_needed(repo: Path, docs: Path, env: dict[str, str], rebuild: bool) -> None:
    fuzz1.build_if_needed(repo, docs, env, skip_build=not rebuild)


def run_pair(
    repo: Path,
    docs: Path,
    run_id: str,
    case: LockedCase,
    seed: int,
    env: dict[str, str],
    run_timeout: int,
    safety_config: Path,
) -> dict[str, Any]:
    mcnn_record = run_controller_eval(repo, docs, run_id, case, seed, "mcnn", env, run_timeout, safety_config)
    classical_record = run_controller_eval(repo, docs, run_id, case, seed, "classical", env, run_timeout, safety_config)
    pair = {
        "mcnn": compact_record(mcnn_record),
        "classical": compact_record(classical_record),
        "classification": classify_locked_pair(mcnn_record, classical_record),
    }
    append_jsonl(docs / "results.jsonl", {"type": "pair", "pair": pair})
    return pair


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--docs-root", type=Path, default=m1.repo_root() / "docs")
    parser.add_argument("--run-timeout", type=int, default=180)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--confirm-runs", type=int, default=3)
    parser.add_argument("--seed-base", type=int, default=20261700)
    parser.add_argument("--max-scan-cases", type=int, default=len(SCAN_CASES))
    parser.add_argument("--safety-config", type=Path, default=m1.repo_root() / "config/m2_safety_envelope.json")
    args = parser.parse_args()

    repo = m1.repo_root()
    docs = (args.docs_root / args.run_id).resolve()
    docs.mkdir(parents=True, exist_ok=True)
    env = m1.agent_env(repo)
    build_if_needed(repo, docs, env, args.rebuild)

    payload: dict[str, Any] = {
        "run_id": args.run_id,
        "decision": {
            "status": "DOWNGRADED",
            "rationale": "No locked differential has been found yet.",
        },
        "pairs": [],
        "pair_summary": {},
        "reachability": (
            "The tested switch states are reached by classical Offboard circle approach with SIH wind. "
            "For the FUZZ-1 lead and this FUZZ-1b run the approach uses relaxed position-controller limits "
            "as initial-condition setup (`MPC_TILTMAX_AIR=89`, high accel/jerk/rate limits); this is not a "
            "claim that default position control reaches the same envelope. The operational framing is dynamic "
            "handoff/upset recovery: if the aircraft is already at this attitude/rate state, the recovery "
            "controller is compared from a matched trigger state."
        ),
    }

    locked_case: LockedCase | None = None
    for idx, case in enumerate(SCAN_CASES[: max(1, args.max_scan_cases)]):
        pair = run_pair(repo, docs, args.run_id, case, args.seed_base + idx, env, args.run_timeout, args.safety_config)
        payload["pairs"].append(pair)
        payload["pair_summary"] = summarize_pairs(payload["pairs"])
        write_json(docs / "results.json", payload)
        write_summary(docs, payload)

        if pair["classification"].get("locked_differential"):
            locked_case = case
            break

    if locked_case is not None:
        confirm_pairs = [pair for pair in payload["pairs"] if pair["mcnn"]["case"] == locked_case.tag]
        for offset in range(1, max(1, args.confirm_runs)):
            confirm_case = replace(locked_case, tag=f"{locked_case.tag}_confirm{offset}")
            confirm_pair = run_pair(
                repo,
                docs,
                args.run_id,
                confirm_case,
                args.seed_base + 100 + offset,
                env,
                args.run_timeout,
                args.safety_config,
            )
            payload["pairs"].append(confirm_pair)
            confirm_pairs.append(confirm_pair)
            payload["pair_summary"] = summarize_pairs(payload["pairs"])
            write_json(docs / "results.json", payload)
            write_summary(docs, payload)

        locked_count = sum(1 for item in confirm_pairs if item["classification"].get("locked_differential"))
        if locked_count >= min(2, len(confirm_pairs)):
            payload["decision"] = {
                "status": "LOCKED",
                "rationale": (
                    f"Found a confirmed Method-A locked differential at `{locked_case.tag}`: "
                    f"{locked_count}/{len(confirm_pairs)} repeated pairs had matched trigger states, "
                    "classical stayed detector-clean, and mc_nn hit the wide flight-unsafe detector."
                ),
            }
        else:
            payload["decision"] = {
                "status": "DOWNGRADED",
                "rationale": (
                    f"The initial locked candidate `{locked_case.tag}` did not reproduce strongly enough "
                    f"({locked_count}/{len(confirm_pairs)} locked pairs)."
                ),
            }
    else:
        payload["decision"] = {
            "status": "DOWNGRADED",
            "rationale": (
                "The bounded state-triggered severity scan did not find a case with matched trigger states where "
                "classical survived and mc_nn failed. Cases that were too hard or failed to trigger are recorded."
            ),
        }

    payload["pair_summary"] = summarize_pairs(payload["pairs"])
    write_json(docs / "results.json", payload)
    write_summary(docs, payload)
    print(f"DECISION={payload['decision']['status']}")
    print(f"SUMMARY={docs / 'summary.md'}")
    print(f"MAIN_DOC={docs.parent / f'{args.run_id}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
