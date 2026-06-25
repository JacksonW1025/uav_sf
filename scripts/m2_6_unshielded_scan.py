#!/usr/bin/env python3
"""Targeted M2.6 scan for RAPTOR's unshielded gyro/rate observation channel."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import m2_map_elites


REPO_ROOT = Path(__file__).resolve().parents[1]
SAFETY_CONFIG = REPO_ROOT / "config/m2_safety_envelope.json"
DEFAULT_CONFIG = REPO_ROOT / "config/m2_6_unshielded_scan.json"
NOMINAL_GYRO_CUTOFF_HZ = 30.0
CONFIRM_SEEDS = [202671, 202672, 202673, 202674, 202675]


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
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


def noise_floor_from(path: Path | None) -> dict[str, float]:
    if path is None:
        return {}
    data = load_json(path)
    for key in ["recommended_noise_floor_for_compare", "recommended_noise_floor", "noise_floor"]:
        value = data.get(key)
        if isinstance(value, dict):
            return {str(k): float(v) for k, v in value.items() if isinstance(v, (int, float))}
    return {}


def physical_params_for_twr(twr: float) -> dict[str, float]:
    mass = m2_map_elites.NOMINAL["mass"]
    t_max = float(twr) * mass * 9.80665 / 4.0
    thrust_scale = t_max / m2_map_elites.NOMINAL["t_max"]
    return {
        "SIH_MASS": mass,
        "SIH_T_MAX": t_max,
        "SIH_Q_MAX": m2_map_elites.NOMINAL["q_max"] * thrust_scale,
        "MPC_THR_HOVER": clamp(1.0 / float(twr), 0.25, 0.9),
    }


def theta_for_gyro_cutoff(
    run_id: str,
    cutoff_hz: float,
    twr: float,
    seed: int,
    *,
    tag: str,
    sine_amplitude_m: float,
    sine_frequency_hz: float,
    axis: str,
    noise_floor: dict[str, float] | None = None,
) -> dict[str, Any]:
    gyro_params = {
        "IMU_GYRO_CUTOFF": round(float(cutoff_hz), 4),
        "IMU_GYRO_RATEMAX": 400,
    }
    physical = physical_params_for_twr(float(twr))
    params = dict(m2_map_elites.BASE_PX4_PARAMS)
    params.update({key: round(value, 8) for key, value in physical.items()})
    params.update(gyro_params)
    boot_params = dict(physical)
    boot_params.update(gyro_params)
    cutoff_delay_proxy_ms = 1000.0 / (2.0 * math.pi * float(cutoff_hz)) if cutoff_hz > 0 else 0.0
    theta: dict[str, Any] = {
        "tag": tag,
        "description": (
            "M2.6 targeted probe: shared vehicle_angular_velocity gyro low-pass phase lag "
            "combined with high thrust-to-weight ratio. This is not a full M2b search."
        ),
        "seed": int(seed),
        "airframe": {
            "sim": "sih",
            "model": "sihsim_x500_v2",
            "sys_autostart": 10046,
        },
        "timing": {
            "controller_switch_s": 18.0,
            "trajectory_start_s": 22.0,
            "mission_end_s": 38.0,
            "mode_command_repeat_s": 0.5,
            "mode_command_timeout_s": 6.0,
            "px4_shutdown_margin_s": 6.0,
            "px4_shutdown_wall_slack_s": 22.0,
        },
        "setpoint": {
            "rate_hz": 100.0,
            "max_wall_timer_hz": 100.0,
            "hover_ned": [0.0, 0.0, -2.5],
            "yaw_rad": 0.0,
            "type": "sine",
            "step": {
                "delta_ned": [0.45, 0.0, 0.0],
            },
            "sine": {
                "axis": axis,
                "amplitude_m": round(float(sine_amplitude_m), 4),
                "frequency_hz": round(float(sine_frequency_hz), 4),
            },
        },
        "boot_px4_params": {key: round(value, 8) for key, value in boot_params.items()},
        "px4_params": params,
        "environment": {
            "sih_wind_n": 0.0,
            "sih_wind_e": 0.0,
            "mass_kg": round(physical["SIH_MASS"], 4),
            "t_max_n": round(physical["SIH_T_MAX"], 4),
            "thrust_to_weight_ratio": round(float(twr), 4),
            "mpc_thr_hover": round(physical["MPC_THR_HOVER"], 4),
            "gyro_filter_cutoff_hz": round(float(cutoff_hz), 4),
            "gyro_filter_delay_proxy_ms": round(cutoff_delay_proxy_ms, 3),
        },
        "faults": [],
        "sensor_perturbations": [
            {
                "type": "shared_vehicle_angular_velocity_filter_lag",
                "simulator": "sih",
                "mechanism": "PX4 IMU_GYRO_CUTOFF low-pass on vehicle_angular_velocity",
                "shared_quantity": "vehicle_angular_velocity",
                "params": gyro_params,
                "physical_credibility": (
                    "Low gyro cutoff emulates abnormal but realistic sensor/filter phase lag; "
                    "it is applied before both classical rate control and RAPTOR consume the shared topic."
                ),
            }
        ],
        "divergence_thresholds": {
            "position_divergence_m": 1.0,
        },
        "m2_6": {
            "generator": "scripts/m2_6_unshielded_scan.py",
            "run_id": run_id,
            "scope": "targeted M2.6 only; not MAP-Elites, not M2b, not M3",
            "unshielded_channel": "angular_velocity",
            "nominal_gyro_cutoff_hz": NOMINAL_GYRO_CUTOFF_HZ,
            "gyro_cutoff_hz": round(float(cutoff_hz), 4),
            "thrust_to_weight_ratio": round(float(twr), 4),
            "safety_config": str(SAFETY_CONFIG.relative_to(REPO_ROOT)),
        },
    }
    if noise_floor:
        theta["noise_floor"] = noise_floor
    return theta


def run_fairness(theta_path: Path, docs_dir: Path) -> Path | None:
    theta = load_json(theta_path)
    tag = theta["tag"]
    classical_ulog = docs_dir / f"m1_{tag}_classical.ulg"
    raptor_ulog = docs_dir / f"m1_{tag}_raptor.ulg"
    if not classical_ulog.exists() or not raptor_ulog.exists():
        return None
    output = docs_dir / f"m2_6_fairness_{tag}.json"
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/m2_5_estimator_fairness.py"),
        "--theta",
        str(theta_path),
        "--classical-ulog",
        str(classical_ulog),
        "--raptor-ulog",
        str(raptor_ulog),
        "--classical-task-json",
        str(docs_dir / f"m1_{tag}_classical_task.json"),
        "--raptor-task-json",
        str(docs_dir / f"m1_{tag}_raptor_task.json"),
        "--output",
        str(output),
    ]
    with (docs_dir / f"m2_6_fairness_{tag}.log").open("w", encoding="utf-8") as handle:
        handle.write("$ " + " ".join(cmd) + "\n")
        handle.flush()
        subprocess.run(cmd, cwd=str(REPO_ROOT), stdout=handle, stderr=subprocess.STDOUT, check=True)
    return output


def summarize_compare(compare_path: str | None, quality_threshold: float) -> dict[str, Any]:
    if not compare_path:
        return {}
    path = Path(compare_path)
    if not path.exists():
        return {}
    compare = load_json(path)
    quality = float(compare.get("divergence", {}).get("quality") or 0.0)
    return {
        "quadrant": compare.get("quadrant"),
        "primary_bug": bool(compare.get("primary_bug")),
        "classical_usable": bool(compare.get("classical_usable_for_primary")),
        "classical_safe": bool(compare.get("classical", {}).get("safe")),
        "raptor_safe": bool(compare.get("raptor", {}).get("safe")),
        "quality": quality,
        "continuous_divergence_above_floor": bool(
            compare.get("quadrant") == "boring_both_safe"
            and bool(compare.get("classical_usable_for_primary"))
            and quality >= quality_threshold
        ),
        "effective_deltas": compare.get("divergence", {}).get("effective_deltas_above_noise_floor", {}),
        "classical_tracking_rms_m": compare.get("classical", {}).get("tracking_error_rms_m"),
        "raptor_tracking_rms_m": compare.get("raptor", {}).get("tracking_error_rms_m"),
        "classical_rate_max_rad_s": compare.get("classical", {}).get("angular_rate_max_rad_s"),
        "raptor_rate_max_rad_s": compare.get("raptor", {}).get("angular_rate_max_rad_s"),
    }


def run_eval(theta: dict[str, Any], theta_path: Path, docs_dir: Path, index: int, args: argparse.Namespace) -> dict[str, Any]:
    start = time.monotonic()
    result = m2_map_elites.evaluate_theta(
        theta,
        theta_path,
        docs_dir,
        index,
        args.run_timeout,
        args.eval_timeout,
        m2_map_elites.os_environ_with_speed(args.sim_speed_factor),
    )
    record = result.as_dict()
    record["elapsed_wall_s_outer"] = time.monotonic() - start
    fairness_path = run_fairness(theta_path, docs_dir) if result.returncode == 0 else None
    record["fairness_path"] = str(fairness_path) if fairness_path else None
    record.update(summarize_compare(result.compare_path, args.continuous_quality_threshold))
    return record


def run_scan(args: argparse.Namespace) -> Path:
    cfg = load_json(args.config)
    cutoffs = args.cutoffs_hz if args.cutoffs_hz is not None else cfg.get("cutoffs_hz", [30.0, 12.0, 8.0, 5.0])
    twrs = args.twrs if args.twrs is not None else cfg.get("thrust_to_weight_ratios", [1.743, 2.1, 2.3])
    sine_amplitude = float(args.sine_amplitude_m if args.sine_amplitude_m is not None else cfg.get("sine_amplitude_m", 0.45))
    sine_frequency = float(args.sine_frequency_hz if args.sine_frequency_hz is not None else cfg.get("sine_frequency_hz", 6.0))
    axis = str(args.axis or cfg.get("axis", "x"))
    noise_floor = noise_floor_from(args.noise_floor_json)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("m2_6_unshielded_scan_%Y%m%dT%H%M%SZ")
    run_dir = (REPO_ROOT / "docs" / run_id).resolve()
    theta_dir = run_dir / "theta"
    evals_dir = run_dir / "evals"
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope_note": "M2.6 targeted unshielded angular-rate channel scan only; not full M2b or M3.",
        "px4_commit": "3042f906abaab7ab59ae838ad5a530a9ef3df9a6",
        "sim_speed_factor": args.sim_speed_factor,
        "run_timeout_s": args.run_timeout,
        "eval_timeout_s": args.eval_timeout,
        "cutoffs_hz": cutoffs,
        "thrust_to_weight_ratios": twrs,
        "sine_amplitude_m": sine_amplitude,
        "sine_frequency_hz": sine_frequency,
        "noise_floor_json": str(args.noise_floor_json) if args.noise_floor_json else None,
        "noise_floor_applied": noise_floor,
    }
    write_json(run_dir / "metadata.json", metadata)
    results: list[dict[str, Any]] = []
    index = 0
    for twr in twrs:
        for cutoff in cutoffs:
            tag = f"{run_id}_gyro{int(round(float(cutoff) * 10)):03d}_twr{int(round(float(twr) * 100)):03d}"
            theta = theta_for_gyro_cutoff(
                run_id,
                float(cutoff),
                float(twr),
                args.seed + index,
                tag=tag,
                sine_amplitude_m=sine_amplitude,
                sine_frequency_hz=sine_frequency,
                axis=axis,
                noise_floor=noise_floor,
            )
            theta_path = theta_dir / f"{tag}.json"
            docs_dir = evals_dir / tag
            record: dict[str, Any] = {
                "index": index,
                "tag": tag,
                "cutoff_hz": float(cutoff),
                "thrust_to_weight_ratio": float(twr),
                "theta_path": str(theta_path),
                "docs_dir": str(docs_dir),
                "ran": False,
            }
            if args.run:
                record.update(run_eval(theta, theta_path, docs_dir, index, args))
                record["ran"] = True
            else:
                write_json(theta_path, theta)
            results.append(record)
            append_jsonl(run_dir / "scan.jsonl", record)
            print(json.dumps(record, sort_keys=True), flush=True)
            index += 1

    confirmations: list[dict[str, Any]] = []
    primary = [item for item in results if item.get("primary_bug")]
    if args.run and primary and args.confirm_repeats > 0:
        candidate = sorted(primary, key=lambda item: float(item.get("quality") or 0.0), reverse=True)[0]
        base_theta = load_json(Path(candidate["theta_path"]))
        for ridx in range(args.confirm_repeats):
            seed = CONFIRM_SEEDS[ridx]
            theta = json.loads(json.dumps(base_theta))
            original_tag = theta["tag"]
            theta["tag"] = f"{original_tag}_confirm_s{seed}"
            theta["seed"] = seed
            theta.setdefault("m2_6", {})["confirmation_of"] = original_tag
            theta.setdefault("m2_6", {})["confirmation_seed"] = seed
            theta_path = run_dir / "confirm" / "theta" / f"{theta['tag']}.json"
            docs_dir = run_dir / "confirm" / "evals" / theta["tag"]
            item = run_eval(theta, theta_path, docs_dir, 1000 + ridx, args)
            confirmations.append(item)
            append_jsonl(run_dir / "confirmations.jsonl", item)
            print(json.dumps({"confirm": ridx, **item}, sort_keys=True), flush=True)

    write_json(run_dir / "results.json", results)
    write_json(run_dir / "confirmations.json", confirmations)
    write_summary(run_dir, results, confirmations)
    return run_dir


def write_summary(run_dir: Path, results: list[dict[str, Any]], confirmations: list[dict[str, Any]]) -> None:
    confirmed = bool(confirmations) and all(item.get("primary_bug") for item in confirmations)
    lines = [
        "# M2.6 Unshielded Gyro/Rate Scan",
        "",
        f"run_dir: `{run_dir.relative_to(REPO_ROOT)}`",
        f"evals: {sum(1 for item in results if item.get('ran'))}",
        f"primary_candidates: {sum(1 for item in results if item.get('primary_bug'))}",
        f"continuous_divergence_above_floor: {sum(1 for item in results if item.get('continuous_divergence_above_floor'))}",
        f"confirmation_repeats: {len(confirmations)}",
        f"confirmed_primary_bug: {str(confirmed).lower()}",
        "",
        "## gradient",
    ]
    for item in results:
        lines.append(
            f"- cutoff={item['cutoff_hz']}Hz twr={item['thrust_to_weight_ratio']} "
            f"quadrant={item.get('quadrant')} primary={item.get('primary_bug')} "
            f"quality={item.get('quality')} fairness=`{item.get('fairness_path')}`"
        )
    if confirmations:
        lines.extend(["", "## confirmations"])
        for item in confirmations:
            lines.append(f"- {item['tag']}: quadrant={item.get('quadrant')} primary={item.get('primary_bug')}")
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--run-id")
    parser.add_argument("--cutoffs-hz", type=float, nargs="+")
    parser.add_argument("--twrs", type=float, nargs="+")
    parser.add_argument("--sine-amplitude-m", type=float)
    parser.add_argument("--sine-frequency-hz", type=float)
    parser.add_argument("--axis", choices=["x", "y"], default=None)
    parser.add_argument("--seed", type=int, default=202660)
    parser.add_argument("--sim-speed-factor", type=float, default=1.0)
    parser.add_argument("--run-timeout", type=int, default=180)
    parser.add_argument("--eval-timeout", type=int, default=480)
    parser.add_argument("--confirm-repeats", type=int, default=3)
    parser.add_argument("--continuous-quality-threshold", type=float, default=0.25)
    parser.add_argument("--noise-floor-json", type=Path)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    run_dir = run_scan(args)
    print(f"M2_6_UNSHIELDED_SCAN_DIR={run_dir}")
    print(f"M2_6_UNSHIELDED_SCAN_SUMMARY={run_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
