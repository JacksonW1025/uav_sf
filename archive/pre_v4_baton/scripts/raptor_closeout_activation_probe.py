#!/usr/bin/env python3
"""Adversarial activation transient probe for RAPTOR closeout."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from pyulog import ULog

import m1_diff_runner as m1
from m1_metrics import quaternion, quat_to_roll_pitch, vector3


@dataclass(frozen=True)
class Case:
    tag: str
    radius_m: float
    frequency_hz: float
    wind_n: float = 0.0
    wind_e: float = 0.0
    approach: bool = True


DEFAULT_CASES = [
    Case("hover_activation", 0.0, 0.0, approach=False),
    Case("circle_30deg", 1.8, 0.25),
    Case("circle_45deg", 2.5, 0.32),
    Case("circle_60deg", 4.0, 0.38),
    Case("circle_75deg", 6.0, 0.45),
    Case("circle_45deg_wind", 2.5, 0.32, wind_n=3.0, wind_e=0.0),
]

B_FLIGHT_UNSAFE_REASONS = {
    "missing_required_topics",
    "controller_mode_not_confirmed",
    "unexpected_disarm",
    "failsafe",
    "ground_contact",
    "attitude_quaternion_nonfinite",
    "attitude_diverged",
    "angular_rate_diverged",
    "active_motor_nan",
    "motor_saturation",
    "missing_position_or_setpoint_window",
}


def parse_cases(case_text: str | None) -> list[Case]:
    if not case_text:
        return DEFAULT_CASES
    selected = {part.strip() for part in case_text.split(",") if part.strip()}
    known = {case.tag: case for case in DEFAULT_CASES}
    missing = sorted(selected - set(known))
    if missing:
        raise ValueError(f"unknown case(s): {', '.join(missing)}")
    return [known[tag] for tag in selected]


def expected_tilt_deg(case: Case) -> float:
    if case.frequency_hz <= 0.0 or case.radius_m <= 0.0:
        return 0.0
    lateral_accel = case.radius_m * (2.0 * math.pi * case.frequency_hz) ** 2
    return math.degrees(math.atan2(lateral_accel, 9.80665))


def theta_for_case(run_id: str, case: Case) -> dict[str, Any]:
    tag = f"{run_id}_{case.tag}"
    timing: dict[str, Any] = {
        "controller_switch_s": 18.0 if not case.approach else 30.0,
        "trajectory_start_s": 24.0 if not case.approach else 18.0,
        "mission_end_s": 42.0 if not case.approach else 46.0,
        "mode_command_repeat_s": 0.5,
        "mode_command_timeout_s": 7.0,
        "px4_shutdown_margin_s": 5.0,
        "px4_shutdown_wall_slack_s": 16.0,
    }
    if case.approach:
        timing["approach_start_s"] = 14.0
    px4_params = {
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
    boot_px4_params: dict[str, float] = {}
    if case.wind_n or case.wind_e:
        boot_px4_params["SIH_WIND_N"] = case.wind_n
        boot_px4_params["SIH_WIND_E"] = case.wind_e
    return {
        "tag": tag,
        "description": (
            "RAPTOR closeout activation transient probe. RAPTOR cases with approach_start_s first fly "
            "classical Offboard, then switch to RAPTOR at controller_switch_s."
        ),
        "seed": 20260625,
        "airframe": {"sim": "sih", "model": "sihsim_x500_v2", "sys_autostart": 10046},
        "timing": timing,
        "setpoint": {
            "rate_hz": 50.0,
            "hover_ned": [0.0, 0.0, -2.5],
            "yaw_rad": 0.0,
            "type": "circle" if case.approach else "step",
            "step": {"delta_ned": [0.0, 0.0, 0.0]},
            "sine": {"axis": "x", "amplitude_m": 0.0, "frequency_hz": 0.0},
            "circle": {
                "radius_m": case.radius_m,
                "frequency_hz": case.frequency_hz,
                "phase_rad": 0.0,
                "z_amplitude_m": 0.0,
            },
        },
        "px4_params": px4_params,
        "boot_px4_params": boot_px4_params,
        "environment": {
            "activation_case": case.__dict__,
            "expected_lateral_accel_m_s2": case.radius_m * (2.0 * math.pi * case.frequency_hz) ** 2
            if case.approach
            else 0.0,
            "expected_tilt_deg": expected_tilt_deg(case),
        },
        "faults": [],
        "sensor_perturbations": [],
        "safe_thresholds": {
            "tracking_error_max_m": 4.0,
            "tracking_error_rms_m": 2.0,
            "final_error_m": 1.5,
            "roll_pitch_max_deg": 75.0,
            "angular_rate_max_rad_s": 8.0,
            "motor_saturation_ratio_max": 0.99,
            "min_altitude_agl_m": 0.25,
        },
        "divergence_thresholds": {"position_divergence_m": 2.0},
    }


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def flight_safe(metrics: dict[str, Any]) -> bool:
    reasons = set(metrics.get("safe_reasons") or [])
    return not bool(reasons & B_FLIGHT_UNSAFE_REASONS)


def flight_quadrant(classical_ok: bool, raptor_ok: bool) -> str:
    if classical_ok and raptor_ok:
        return "boring_both_flight_safe"
    if not classical_ok and raptor_ok:
        return "interesting_not_bug"
    if classical_ok and not raptor_ok:
        return "activation_primary_bug"
    return "too_hard_not_bug"


def first_dataset(ulog: ULog, name: str):
    matches = [dataset for dataset in ulog.data_list if dataset.name == name]
    return matches[0] if matches else None


def window_mask(ts: np.ndarray, start_us: int, end_us: int) -> np.ndarray:
    return (ts >= start_us) & (ts <= end_us)


def switch_context(
    ulog_path: Path,
    task_path: Path,
    metrics_path: Path,
    theta: dict[str, Any],
    pre_s: float = 0.5,
) -> dict[str, Any]:
    task = load_json(task_path)
    metrics = load_json(metrics_path)
    origin_us = int(metrics["task_to_ulog_origin_us"])
    switch_us = int(origin_us + float(theta["timing"]["controller_switch_s"]) * 1e6)
    start_us = int(switch_us - pre_s * 1e6)
    ulog = ULog(str(ulog_path))
    att = first_dataset(ulog, "vehicle_attitude")
    rates = first_dataset(ulog, "vehicle_angular_velocity")
    result: dict[str, Any] = {
        "switch_us": switch_us,
        "window_start_us": start_us,
        "window_end_us": switch_us,
        "pre_window_s": pre_s,
        "task_origin_us": int(task["origin_us"]),
        "ulog_origin_us": origin_us,
    }
    if att is not None:
        ts = att.data["timestamp"].astype(np.int64)
        mask = window_mask(ts, start_us, switch_us)
        result["attitude_samples"] = int(np.count_nonzero(mask))
        if np.any(mask):
            q = quaternion(att.data)[mask]
            roll, pitch = quat_to_roll_pitch(q)
            roll_pitch = np.maximum(np.abs(roll), np.abs(pitch))
            result["pre_switch_roll_pitch_max_deg"] = float(np.rad2deg(np.nanmax(roll_pitch)))
            result["pre_switch_roll_pitch_mean_deg"] = float(np.rad2deg(np.nanmean(roll_pitch)))
    if rates is not None:
        ts = rates.data["timestamp"].astype(np.int64)
        mask = window_mask(ts, start_us, switch_us)
        result["angular_rate_samples"] = int(np.count_nonzero(mask))
        if np.any(mask):
            omega = vector3(rates.data, "xyz")[mask]
            norm = np.linalg.norm(omega, axis=1)
            result["pre_switch_angular_rate_max_rad_s"] = float(np.nanmax(norm))
            result["pre_switch_angular_rate_mean_rad_s"] = float(np.nanmean(norm))
            for axis, field in enumerate(["x", "y", "z"]):
                result[f"pre_switch_angular_rate_{field}_max_abs_rad_s"] = float(np.nanmax(np.abs(omega[:, axis])))
    return result


def run_case(
    repo: Path,
    run_id: str,
    case: Case,
    docs: Path,
    env: dict[str, str],
    run_timeout: int,
    safety_config: Path,
) -> dict[str, Any]:
    case_dir = docs / case.tag
    case_dir.mkdir(parents=True, exist_ok=True)
    theta = theta_for_case(run_id, case)
    theta_path = case_dir / f"{theta['tag']}.json"
    theta_path.write_text(json.dumps(theta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    outputs: dict[str, Any] = {}
    for controller in ["classical", "raptor"]:
        print(f"RUN_CONTROLLER={controller} CASE={case.tag}", flush=True)
        outputs[controller] = m1.run_one(repo, theta_path, theta, controller, case_dir, env, run_timeout, safety_config)

    compare_json = case_dir / f"activation_diff_{theta['tag']}.json"
    m1.run_checked(
        [
            sys.executable,
            str(repo / "scripts/m1_compare.py"),
            "--theta",
            str(theta_path),
            "--classical",
            str(outputs["classical"]["metrics"]),
            "--raptor",
            str(outputs["raptor"]["metrics"]),
            "--output",
            str(compare_json),
        ],
        cwd=repo,
        log=case_dir / f"activation_diff_{theta['tag']}.log",
        env=env,
    )
    m1.write_summary(compare_json, case_dir / f"activation_diff_{theta['tag']}_summary.md")
    compare = load_json(compare_json)
    classical_flight_safe = flight_safe(compare["classical"])
    raptor_flight_safe = flight_safe(compare["raptor"])
    contexts = {
        controller: switch_context(
            Path(outputs[controller]["ulog"]),
            Path(outputs[controller]["task"]),
            Path(outputs[controller]["metrics"]),
            theta,
        )
        for controller in ["classical", "raptor"]
    }
    record = {
        "case": case.__dict__,
        "tag": theta["tag"],
        "expected_tilt_deg": theta["environment"]["expected_tilt_deg"],
        "quadrant": compare["quadrant"],
        "primary_bug": compare["primary_bug"],
        "activation_flight_quadrant": flight_quadrant(classical_flight_safe, raptor_flight_safe),
        "activation_primary_bug": classical_flight_safe and not raptor_flight_safe,
        "classical_flight_safe": classical_flight_safe,
        "raptor_flight_safe": raptor_flight_safe,
        "classical_safe": compare["classical"].get("safe"),
        "classical_safe_reasons": compare["classical"].get("safe_reasons"),
        "raptor_safe": compare["raptor"].get("safe"),
        "raptor_safe_reasons": compare["raptor"].get("safe_reasons"),
        "classical_tracking_error_max_m": compare["classical"].get("tracking_error_max_m"),
        "raptor_tracking_error_max_m": compare["raptor"].get("tracking_error_max_m"),
        "classical_roll_pitch_max_deg": compare["classical"].get("roll_pitch_max_deg"),
        "raptor_roll_pitch_max_deg": compare["raptor"].get("roll_pitch_max_deg"),
        "classical_angular_rate_max_rad_s": compare["classical"].get("angular_rate_max_rad_s"),
        "raptor_angular_rate_max_rad_s": compare["raptor"].get("angular_rate_max_rad_s"),
        "switch_context": contexts,
        "outputs": {
            controller: {key: str(value) for key, value in paths.items()}
            for controller, paths in outputs.items()
        },
    }
    (case_dir / "record.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def write_summary(docs: Path, records: list[dict[str, Any]]) -> None:
    lines = [
        "# RAPTOR closeout activation transient",
        "",
        "Classical and RAPTOR fly the same finite setpoint; approach cases enter classical Offboard before RAPTOR activation.",
        "",
        "| case | compare quadrant | flight quadrant | activation bug | pre-switch roll C/R | pre-switch rate C/R | safe C/R | track max C/R | reasons C/R |",
        "|---|---|---|---:|---:|---:|---|---:|---|",
    ]
    for record in records:
        cctx = record["switch_context"]["classical"]
        rctx = record["switch_context"]["raptor"]
        creasons = ",".join(record.get("classical_safe_reasons") or []) or "-"
        rreasons = ",".join(record.get("raptor_safe_reasons") or []) or "-"
        lines.append(
            "| {case} | {quadrant} | {flight_quadrant} | {primary} | {croll:.3g}/{rroll:.3g} | {crate:.3g}/{rrate:.3g} | {csafe}/{rsafe} | {ctrack:.3g}/{rtrack:.3g} | {creasons}/{rreasons} |".format(
                case=record["case"]["tag"],
                quadrant=record["quadrant"],
                flight_quadrant=record["activation_flight_quadrant"],
                primary=str(record["activation_primary_bug"]).lower(),
                croll=cctx.get("pre_switch_roll_pitch_max_deg") or float("nan"),
                rroll=rctx.get("pre_switch_roll_pitch_max_deg") or float("nan"),
                crate=cctx.get("pre_switch_angular_rate_max_rad_s") or float("nan"),
                rrate=rctx.get("pre_switch_angular_rate_max_rad_s") or float("nan"),
                csafe=str(record["classical_safe"]).lower(),
                rsafe=str(record["raptor_safe"]).lower(),
                ctrack=record["classical_tracking_error_max_m"] or float("nan"),
                rtrack=record["raptor_tracking_error_max_m"] or float("nan"),
                creasons=creasons,
                rreasons=rreasons,
            )
        )
    (docs / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="raptor_closeout_activation_20260625")
    parser.add_argument("--docs-root", type=Path, default=m1.repo_root() / "docs")
    parser.add_argument("--cases")
    parser.add_argument("--run-timeout", type=int, default=140)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--safety-config", type=Path, default=m1.repo_root() / "config/m2_safety_envelope.json")
    args = parser.parse_args()

    repo = m1.repo_root()
    docs = (args.docs_root / args.run_id).resolve()
    docs.mkdir(parents=True, exist_ok=True)
    env = m1.agent_env(repo)
    if not args.skip_build:
        build_env = env.copy()
        build_env["PX4_RAPTOR_SIH_BUILD_LOG"] = str(docs / "px4_sih_build.log")
        m1.run_checked([str(repo / "scripts/build_px4_raptor_sih.sh")], cwd=repo, log=docs / "build.log", env=build_env)
    else:
        m1.run_checked([str(repo / "scripts/install_raptor_sih_board.sh")], cwd=repo, log=docs / "build.log", env=env)
        m1.run_checked([str(repo / "scripts/install_m1_sih_x500.sh")], cwd=repo, log=docs / "build.log", env=env)
        m1.run_checked([str(repo / "scripts/install_m2b_state_shim.sh")], cwd=repo, log=docs / "build.log", env=env)

    records: list[dict[str, Any]] = []
    results_jsonl = docs / "results.jsonl"
    for case in parse_cases(args.cases):
        print(f"RUN_CASE={case.tag}", flush=True)
        record = run_case(repo, args.run_id, case, docs, env, args.run_timeout, args.safety_config)
        records.append(record)
        with results_jsonl.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        (docs / "results.json").write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_summary(docs, records)

    print(f"RESULTS={docs / 'results.json'}")
    print(f"SUMMARY={docs / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
