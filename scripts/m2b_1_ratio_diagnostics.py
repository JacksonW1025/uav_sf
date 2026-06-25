#!/usr/bin/env python3
"""D3 low-noise ratio degradation diagnostics."""

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
SAFETY_CONFIG = REPO_ROOT / "config/m2b_safety_envelope_1x_high_twr.json"
DEFAULT_SEEDS = [20261201, 20261202, 20261203, 20261204, 20261205]
METRICS = [
    "tracking_error_max_m",
    "tracking_error_rms_m",
    "final_error_m",
    "roll_pitch_max_deg",
    "roll_pitch_std_deg",
    "angular_rate_max_rad_s",
    "angular_rate_std_rad_s",
    "motor_saturation_ratio",
]
SCENARIOS = {
    "baseline": {"channel": "velocity", "profile": "off", "delay_ms": 0, "values": (0.0, 0.0, 0.0)},
    "velocity_noise_y0308": {"channel": "velocity", "profile": "noise", "delay_ms": 0, "values": (0.0, 0.30826648, 0.0)},
    "gyro_bias_x0153": {"channel": "angular_velocity", "profile": "bias", "delay_ms": 0, "values": (0.15268399, 0.0, 0.0)},
    "velocity_delay_030ms": {"channel": "velocity", "profile": "delay", "delay_ms": 30, "values": (0.0, 0.0, 0.0)},
}


def finite_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def load_metrics(record: dict[str, Any], controller: str) -> dict[str, Any]:
    path = record.get(f"{controller}_metrics_path")
    if not path:
        return {}
    p = Path(path)
    if not p.exists() and str(p).startswith("/workspace/"):
        p = REPO_ROOT / str(p).removeprefix("/workspace/")
    if not p.exists():
        return {}
    return profiles.load_json(p)


def value_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def metric_values(records: list[dict[str, Any]], scenario: str, controller: str, metric: str) -> list[float]:
    values: list[float] = []
    for record in records:
        if record.get("scenario") != scenario or not record.get("ran"):
            continue
        value = finite_number(load_metrics(record, controller).get(metric))
        if value is not None:
            values.append(value)
    return values


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    baseline_mean: dict[str, dict[str, float | None]] = {controller: {} for controller in ["classical", "raptor"]}
    baseline_stats: dict[str, dict[str, Any]] = {controller: {} for controller in ["classical", "raptor"]}
    for controller in ["classical", "raptor"]:
        for metric in METRICS:
            values = metric_values(records, "baseline", controller, metric)
            stats = value_stats(values)
            baseline_stats[controller][metric] = stats
            baseline_mean[controller][metric] = float(stats["mean"]) if stats.get("count") else None

    scenarios: dict[str, Any] = {}
    for scenario in SCENARIOS:
        scenario_records = [
            record for record in records if record.get("scenario") == scenario and record.get("ran")
        ]
        scenario_summary: dict[str, Any] = {
            "metrics": {},
            "runs": len(scenario_records),
        }
        if scenario == "baseline":
            scenario_summary["fairness_all_true"] = None
        else:
            scenario_summary["fairness_all_true"] = bool(scenario_records) and all(
                record.get("fair_shared_state_shim_pollution") is True
                and all(
                    check.get("classical_topic_polluted") is True
                    and check.get("raptor_topic_polluted") is True
                    and check.get("raptor_input_touch_verified") is True
                    for check in (record.get("state_shim_topic_checks") or [])
                )
                for record in scenario_records
            )
        for metric in METRICS:
            metric_summary: dict[str, Any] = {}
            for controller in ["classical", "raptor"]:
                values = metric_values(records, scenario, controller, metric)
                denom = baseline_mean[controller].get(metric)
                ratios = [value / denom for value in values if denom and denom > 0]
                metric_summary[controller] = {
                    "values": value_stats(values),
                    "ratios_to_own_baseline_mean": value_stats(ratios),
                }
            c_med = metric_summary["classical"]["ratios_to_own_baseline_mean"].get("median")
            r_med = metric_summary["raptor"]["ratios_to_own_baseline_mean"].get("median")
            if isinstance(c_med, (int, float)) and isinstance(r_med, (int, float)):
                metric_summary["raptor_minus_classical_ratio_median"] = float(r_med) - float(c_med)
                metric_summary["raptor_over_classical_ratio_median"] = float(r_med) / max(float(c_med), 1e-9)
            scenario_summary["metrics"][metric] = metric_summary
        scenarios[scenario] = scenario_summary

    return {
        "baseline_mean": baseline_mean,
        "baseline_stats": baseline_stats,
        "scenarios": scenarios,
        "records": records,
    }


def build_theta(args: argparse.Namespace, run_id: str, scenario: str, seed: int) -> dict[str, Any]:
    spec = SCENARIOS[scenario]
    tag = f"{run_id}_{scenario}_s{seed}"
    theta = profiles.base_state_theta(
        tag=tag,
        seed=seed,
        channel=str(spec["channel"]),
        profile=str(spec["profile"]),
        delay_ms=int(spec["delay_ms"]),
        values=spec["values"],
        twr=args.twr,
        sine_axis=args.axis,
        sine_amplitude_m=args.sine_amplitude_m,
        sine_frequency_hz=args.sine_frequency_hz,
        start_s=args.start_s,
        end_s=args.mission_end_s,
        controller_switch_s=args.controller_switch_s,
        trajectory_start_s=args.start_s,
        mission_end_s=args.mission_end_s,
        mitigation="d3_ratio_low_noise_diagnostic",
    )
    theta.setdefault("m2b_1", {})["ratio_degradation_diagnostic"] = True
    theta["m2b_1"]["scenario"] = scenario
    theta["m2b_1"]["low_noise_regime"] = {
        "nominal_twr": args.twr,
        "sim_speed_factor": args.sim_speed_factor,
        "hover_window_start_s": args.start_s,
        "mission_end_s": args.mission_end_s,
        "sine_amplitude_m": args.sine_amplitude_m,
    }
    theta["setpoint"]["sine"]["amplitude_m"] = round(float(args.sine_amplitude_m), 4)
    theta["setpoint"]["sine"]["frequency_hz"] = round(float(args.sine_frequency_hz), 4)
    theta["m2b_1"]["safety_config"] = str(SAFETY_CONFIG.relative_to(REPO_ROOT))
    return theta


def write_summary(run_dir: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# M2b-1 D3 Low-Noise Ratio Diagnostic",
        "",
        f"run_dir: `{run_dir.relative_to(REPO_ROOT)}`",
        f"records: {sum(1 for item in summary.get('records', []) if item.get('ran'))}",
        "",
        "## baseline RMS",
    ]
    if "baseline_stats" not in summary:
        lines.append("- not run; theta files only")
        (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    for controller in ["classical", "raptor"]:
        stats = summary["baseline_stats"][controller]["tracking_error_rms_m"]
        lines.append(f"- {controller}: mean={stats.get('mean')} range={stats.get('range')} stdev={stats.get('stdev')}")
    lines.extend(["", "## scenario ratios, tracking_error_rms_m"])
    for scenario, item in summary["scenarios"].items():
        metric = item["metrics"]["tracking_error_rms_m"]
        c = metric["classical"]["ratios_to_own_baseline_mean"]
        r = metric["raptor"]["ratios_to_own_baseline_mean"]
        fairness = item.get("fairness_all_true")
        lines.append(
            f"- {scenario}: classical_median={c.get('median')} raptor_median={r.get('median')} "
            f"delta={metric.get('raptor_minus_classical_ratio_median')} fairness_all_true={fairness}"
        )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def aggregate_existing(run_dir: Path) -> Path:
    results_path = run_dir / "results.jsonl"
    records = [
        json.loads(line)
        for line in results_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    metadata_path = run_dir / "metadata.json"
    metadata = profiles.load_json(metadata_path) if metadata_path.exists() else {}
    summary = aggregate(records)
    summary["metadata"] = metadata
    profiles.write_json(run_dir / "ratio_summary.json", summary)
    write_summary(run_dir, summary)
    return run_dir


def run(args: argparse.Namespace) -> Path:
    run_id = args.run_id or datetime.now(timezone.utc).strftime("m2b_1_diag_d3_ratio_%Y%m%dT%H%M%SZ")
    run_dir = (REPO_ROOT / "docs" / run_id).resolve()
    theta_dir = run_dir / "theta"
    evals_dir = run_dir / "evals"
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope_note": "D3 only: low-noise multi-seed ratio degradation diagnostic; not campaign.",
        "seeds": args.seeds,
        "scenarios": SCENARIOS,
        "metrics": METRICS,
        "sim_speed_factor": args.sim_speed_factor,
        "thrust_to_weight_ratio": args.twr,
        "hover_window_start_s": args.start_s,
        "mission_end_s": args.mission_end_s,
    }
    profiles.write_json(run_dir / "metadata.json", metadata)
    records: list[dict[str, Any]] = []
    index = 0
    for scenario in args.scenarios:
        for seed in args.seeds:
            theta = build_theta(args, run_id, scenario, int(seed))
            theta_path = theta_dir / f"{theta['tag']}.json"
            docs_dir = evals_dir / theta["tag"]
            record: dict[str, Any] = {
                "index": index,
                "scenario": scenario,
                "seed": int(seed),
                "tag": theta["tag"],
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
                        safety_config=SAFETY_CONFIG,
                    )
                )
                record["classical_metrics_path"] = str(docs_dir / f"m1_{theta['tag']}_classical_metrics.json")
                record["raptor_metrics_path"] = str(docs_dir / f"m1_{theta['tag']}_raptor_metrics.json")
                record["ran"] = True
            else:
                profiles.write_json(theta_path, theta)
            records.append(record)
            profiles.append_jsonl(run_dir / "results.jsonl", record)
            print(json.dumps(record, sort_keys=True), flush=True)
            index += 1
    summary = aggregate(records) if args.run else {"records": records}
    summary["metadata"] = metadata
    profiles.write_json(run_dir / "ratio_summary.json", summary)
    write_summary(run_dir, summary)
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    parser.add_argument(
        "--aggregate-existing",
        type=Path,
        help="Rebuild ratio_summary.json/summary.md from an existing results.jsonl without running evals.",
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=DEFAULT_SEEDS)
    parser.add_argument("--scenarios", nargs="+", choices=sorted(SCENARIOS), default=list(SCENARIOS))
    parser.add_argument("--twr", type=float, default=1.743)
    parser.add_argument("--axis", choices=["x", "y", "z"], default="z")
    parser.add_argument("--sine-amplitude-m", type=float, default=0.0)
    parser.add_argument("--sine-frequency-hz", type=float, default=0.5)
    parser.add_argument("--controller-switch-s", type=float, default=18.0)
    parser.add_argument("--start-s", type=float, default=28.0)
    parser.add_argument("--mission-end-s", type=float, default=52.0)
    parser.add_argument("--sim-speed-factor", type=float, default=1.0)
    parser.add_argument("--run-timeout", type=int, default=170)
    parser.add_argument("--eval-timeout", type=int, default=420)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    run_dir = aggregate_existing(args.aggregate_existing.resolve()) if args.aggregate_existing else run(args)
    print(f"M2B_1_D3_RATIO_DIAG_DIR={run_dir}")
    print(f"M2B_1_D3_RATIO_DIAG_SUMMARY={run_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
