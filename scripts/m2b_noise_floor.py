#!/usr/bin/env python3
"""M2b-1 same-theta noise-floor remeasurement for high-TWR state-shim search."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import m2b_state_profiles as profiles


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEEDS = [20260901, 20260902, 20260903, 20260904, 20260905]
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
        path = record.get(f"{controller}_metrics_path")
        if not path:
            continue
        metrics = profiles.load_json(Path(path))
        value = finite_number(metrics.get(key))
        if value is not None:
            values.append(value)
    return value_stats(values)


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    stats: dict[str, Any] = {controller: {} for controller in ["classical", "raptor"]}
    observed_floor: dict[str, float] = {}
    for controller in ["classical", "raptor"]:
        for key in COMPARE_METRICS:
            stats[controller][key] = metric_stats(records, controller, key)
    for key in COMPARE_METRICS:
        observed_floor[key] = max(float(stats[controller][key].get("range") or 0.0) for controller in ["classical", "raptor"])
    return {"observed_noise_floor": observed_floor, "compare_metric_stats": stats, "records": records}


def run(args: argparse.Namespace) -> Path:
    run_id = args.run_id or datetime.now(timezone.utc).strftime("m2b_noise_floor_%Y%m%dT%H%M%SZ")
    run_dir = (REPO_ROOT / "docs" / run_id).resolve()
    theta_dir = run_dir / "theta"
    evals_dir = run_dir / "evals"
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope_note": "M2b-1 high-TWR same-theta noise-floor remeasurement; not M3.",
        "seeds": args.seeds,
        "sim_speed_factor": args.sim_speed_factor,
        "thrust_to_weight_ratio": args.twr,
        "sine_axis": args.axis,
        "sine_amplitude_m": args.sine_amplitude_m,
        "sine_frequency_hz": args.sine_frequency_hz,
    }
    profiles.write_json(run_dir / "metadata.json", metadata)
    records: list[dict[str, Any]] = []
    for index, seed in enumerate(args.seeds):
        tag = f"{run_id}_s{int(seed)}"
        theta = profiles.base_state_theta(
            tag=tag,
            seed=int(seed),
            channel="velocity",
            profile="off",
            twr=args.twr,
            sine_axis=args.axis,
            sine_amplitude_m=args.sine_amplitude_m,
            sine_frequency_hz=args.sine_frequency_hz,
            mitigation="noise_floor_shim_disabled",
        )
        theta.setdefault("m2b_1", {})["noise_floor_repeat"] = True
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
            record.update(
                profiles.evaluate_theta_record(
                    theta,
                    theta_path,
                    docs_dir,
                    index,
                    run_timeout=args.run_timeout,
                    eval_timeout=args.eval_timeout,
                    sim_speed_factor=args.sim_speed_factor,
                )
            )
            record["classical_metrics_path"] = str(docs_dir / f"m1_{tag}_classical_metrics.json")
            record["raptor_metrics_path"] = str(docs_dir / f"m1_{tag}_raptor_metrics.json")
            record["ran"] = True
        else:
            profiles.write_json(theta_path, theta)
        records.append(record)
        profiles.append_jsonl(run_dir / "repeats.jsonl", record)
        print(json.dumps(record, sort_keys=True), flush=True)
    summary = aggregate(records) if args.run else {"records": records}
    summary["metadata"] = metadata
    profiles.write_json(run_dir / "noise_floor_summary.json", summary)
    write_summary(run_dir, summary)
    return run_dir


def write_summary(run_dir: Path, summary: dict[str, Any]) -> None:
    records = summary.get("records", [])
    observed = summary.get("observed_noise_floor", {})
    lines = [
        "# M2b-1 Noise Floor",
        "",
        f"run_dir: `{run_dir.relative_to(REPO_ROOT)}`",
        f"repeats: {sum(1 for item in records if item.get('ran'))}",
        "",
        "## observed compare floors",
    ]
    if observed:
        for key in COMPARE_METRICS:
            lines.append(f"- {key}: {observed.get(key)}")
    else:
        lines.append("- not run; theta files only")
    lines.extend(["", "## repeats"])
    for item in records:
        lines.append(
            f"- seed={item.get('seed')} quadrant={item.get('quadrant')} primary={item.get('primary_bug')} "
            f"returncode={item.get('returncode')} quality={item.get('quality')}"
        )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    parser.add_argument("--seeds", type=int, nargs="+", default=DEFAULT_SEEDS)
    parser.add_argument("--twr", type=float, default=2.3)
    parser.add_argument("--axis", choices=["x", "y", "z"], default="z")
    parser.add_argument("--sine-amplitude-m", type=float, default=0.22)
    parser.add_argument("--sine-frequency-hz", type=float, default=2.5)
    parser.add_argument("--sim-speed-factor", type=float, default=4.0)
    parser.add_argument("--run-timeout", type=int, default=180)
    parser.add_argument("--eval-timeout", type=int, default=480)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    run_dir = run(args)
    print(f"M2B_NOISE_FLOOR_DIR={run_dir}")
    print(f"M2B_NOISE_FLOOR_SUMMARY={run_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
