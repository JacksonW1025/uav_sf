#!/usr/bin/env python3
"""Remeasure M2.6 1x run-to-run noise floor for attitude/rate-heavy probes."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import m2_6_unshielded_scan
import m2_map_elites


REPO_ROOT = Path(__file__).resolve().parents[1]
SAFETY_CONFIG = REPO_ROOT / "config/m2_safety_envelope.json"
DEFAULT_CONFIG = REPO_ROOT / "config/m2_6_noise_floor_nominal_sine.json"
DEFAULT_SEEDS = [202661, 202662, 202663, 202664, 202665]
COMPARE_METRICS = [
    "tracking_error_max_m",
    "tracking_error_rms_m",
    "final_error_m",
    "roll_pitch_max_deg",
    "roll_pitch_std_deg",
    "angular_rate_max_rad_s",
    "angular_rate_std_rad_s",
    "motor_saturation_ratio",
]
CHANNEL_METRICS = [
    "attitude_quaternion_error_rms_deg",
    "attitude_quaternion_error_max_deg",
    "angular_velocity_error_rms_rad_s",
    "angular_velocity_error_max_rad_s",
]


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


def finite_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def value_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
        "mean": statistics.fmean(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def metric_stats(records: list[dict[str, Any]], controller: str, key: str) -> dict[str, Any]:
    values: list[float] = []
    for record in records:
        metrics_path = record.get(f"{controller}_metrics_path")
        if not metrics_path:
            continue
        metrics = load_json(Path(metrics_path))
        value = finite_number(metrics.get(key))
        if value is not None:
            values.append(value)
    return value_stats(values)


def channel_stats(records: list[dict[str, Any]], controller: str, key: str) -> dict[str, Any]:
    values: list[float] = []
    for record in records:
        fairness_path = record.get("fairness_path")
        if not fairness_path:
            continue
        fairness = load_json(Path(fairness_path))
        summary = fairness.get(controller, {})
        if key.startswith("attitude_"):
            source = summary.get("attitude_vs_groundtruth", {})
            source_key = key.removeprefix("attitude_")
        else:
            source = summary.get("angular_velocity_vs_groundtruth", {})
            source_key = key.removeprefix("angular_velocity_")
        value = finite_number(source.get(source_key))
        if value is not None:
            values.append(value)
    return value_stats(values)


def read_existing_noise_floor() -> dict[str, float]:
    config = load_json(SAFETY_CONFIG)
    floor = config.get("noise_floor", {})
    return {str(k): float(v) for k, v in floor.items() if isinstance(v, (int, float))}


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    compare_stats: dict[str, Any] = {controller: {} for controller in ["classical", "raptor"]}
    channel_metric_stats: dict[str, Any] = {controller: {} for controller in ["classical", "raptor"]}
    for controller in ["classical", "raptor"]:
        for key in COMPARE_METRICS:
            compare_stats[controller][key] = metric_stats(records, controller, key)
        for key in CHANNEL_METRICS:
            channel_metric_stats[controller][key] = channel_stats(records, controller, key)

    observed_floor: dict[str, float] = {}
    for key in COMPARE_METRICS:
        observed_floor[key] = max(
            float(compare_stats[controller][key].get("range") or 0.0)
            for controller in ["classical", "raptor"]
        )
    existing = read_existing_noise_floor()
    recommended = {
        key: max(float(existing.get(key, 0.0)), float(value))
        for key, value in observed_floor.items()
    }
    return {
        "observed_noise_floor": observed_floor,
        "existing_noise_floor": existing,
        "recommended_noise_floor_for_compare": recommended,
        "compare_metric_stats": compare_stats,
        "channel_metric_stats": channel_metric_stats,
    }


def run_noise_floor(args: argparse.Namespace) -> Path:
    cfg = load_json(args.config)
    seeds = args.seeds if args.seeds is not None else cfg.get("seeds", DEFAULT_SEEDS)
    cutoff_hz = float(args.cutoff_hz if args.cutoff_hz is not None else cfg.get("cutoff_hz", 30.0))
    twr = float(args.twr if args.twr is not None else cfg.get("thrust_to_weight_ratio", 1.743))
    sine_amplitude = float(args.sine_amplitude_m if args.sine_amplitude_m is not None else cfg.get("sine_amplitude_m", 0.45))
    sine_frequency = float(args.sine_frequency_hz if args.sine_frequency_hz is not None else cfg.get("sine_frequency_hz", 6.0))
    axis = str(args.axis or cfg.get("axis", "x"))
    run_id = args.run_id or datetime.now(timezone.utc).strftime("m2_6_noise_floor_1x_%Y%m%dT%H%M%SZ")
    run_dir = (REPO_ROOT / "docs" / run_id).resolve()
    theta_dir = run_dir / "theta"
    evals_dir = run_dir / "evals"
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope_note": "M2.6 1x same-theta run-to-run noise-floor remeasurement; not M3.",
        "px4_commit": "3042f906abaab7ab59ae838ad5a530a9ef3df9a6",
        "seeds": seeds,
        "sim_speed_factor": args.sim_speed_factor,
        "cutoff_hz": cutoff_hz,
        "thrust_to_weight_ratio": twr,
        "sine_amplitude_m": sine_amplitude,
        "sine_frequency_hz": sine_frequency,
        "safety_config": str(SAFETY_CONFIG.relative_to(REPO_ROOT)),
    }
    write_json(run_dir / "metadata.json", metadata)
    records: list[dict[str, Any]] = []
    for index, seed in enumerate(seeds):
        tag = f"{run_id}_s{int(seed)}"
        theta = m2_6_unshielded_scan.theta_for_gyro_cutoff(
            run_id,
            cutoff_hz,
            twr,
            int(seed),
            tag=tag,
            sine_amplitude_m=sine_amplitude,
            sine_frequency_hz=sine_frequency,
            axis=axis,
            noise_floor=None,
        )
        theta.setdefault("m2_6", {})["noise_floor_repeat"] = True
        theta_path = theta_dir / f"{tag}.json"
        docs_dir = evals_dir / tag
        record: dict[str, Any] = {
            "index": index,
            "seed": int(seed),
            "tag": tag,
            "theta_path": str(theta_path),
            "docs_dir": str(docs_dir),
            "ran": False,
        }
        if args.run:
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
            record.update(result.as_dict())
            record["elapsed_wall_s_outer"] = time.monotonic() - start
            fairness_path = m2_6_unshielded_scan.run_fairness(theta_path, docs_dir) if result.returncode == 0 else None
            record["fairness_path"] = str(fairness_path) if fairness_path else None
            record["classical_metrics_path"] = str(docs_dir / f"m1_{tag}_classical_metrics.json")
            record["raptor_metrics_path"] = str(docs_dir / f"m1_{tag}_raptor_metrics.json")
            record["ran"] = True
        else:
            write_json(theta_path, theta)
        records.append(record)
        append_jsonl(run_dir / "repeats.jsonl", record)
        print(json.dumps(record, sort_keys=True), flush=True)

    write_json(run_dir / "results.json", records)
    summary = aggregate(records) if args.run else {}
    summary.update({"records": records, "metadata": metadata})
    write_json(run_dir / "noise_floor_summary.json", summary)
    write_summary(run_dir, summary)
    return run_dir


def write_summary(run_dir: Path, summary: dict[str, Any]) -> None:
    records = summary.get("records", [])
    recommended = summary.get("recommended_noise_floor_for_compare", {})
    observed = summary.get("observed_noise_floor", {})
    lines = [
        "# M2.6 Noise Floor Remeasurement",
        "",
        f"run_dir: `{run_dir.relative_to(REPO_ROOT)}`",
        f"repeats: {sum(1 for item in records if item.get('ran'))}",
        "",
        "## observed compare floors",
    ]
    if observed:
        for key in COMPARE_METRICS:
            lines.append(f"- {key}: observed_range={observed.get(key)} recommended={recommended.get(key)}")
    else:
        lines.append("- not run; theta files only")
    lines.extend(["", "## repeats"])
    for item in records:
        lines.append(
            f"- seed={item.get('seed')} quadrant={item.get('quadrant')} primary={item.get('primary_bug')} "
            f"returncode={item.get('returncode')} fairness=`{item.get('fairness_path')}`"
        )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--run-id")
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--cutoff-hz", type=float)
    parser.add_argument("--twr", type=float)
    parser.add_argument("--sine-amplitude-m", type=float)
    parser.add_argument("--sine-frequency-hz", type=float)
    parser.add_argument("--axis", choices=["x", "y"], default=None)
    parser.add_argument("--sim-speed-factor", type=float, default=1.0)
    parser.add_argument("--run-timeout", type=int, default=180)
    parser.add_argument("--eval-timeout", type=int, default=480)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    run_dir = run_noise_floor(args)
    print(f"M2_6_NOISE_FLOOR_DIR={run_dir}")
    print(f"M2_6_NOISE_FLOOR_SUMMARY={run_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
