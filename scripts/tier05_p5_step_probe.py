#!/usr/bin/env python3
"""Run the Tier 0.5 pure-step P5 probe for mc_nn versus classical.

This is a bounded validation helper, not a search loop. It generates one
moderate P5 step theta per seed, runs both controllers through the existing
mc_nn SIH runner, evaluates property_oracle.py, and writes structured summaries
outside the ignored eval artifact tree.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from pyulog import ULog

import m1_diff_runner as m1
import mcnn_gate3_position_error_probe as gate3
import property_oracle
import theta_genome


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "tier05_p5_step_20260626"
DEFAULT_SEEDS = [20262601, 20262602, 20262603]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def local_path(value: str | Path) -> Path:
    path = Path(value)
    if path.exists():
        return path
    text = str(path)
    if text.startswith("/workspace/"):
        candidate = REPO_ROOT / text.removeprefix("/workspace/")
        if candidate.exists() or candidate.parent.exists():
            return candidate
    return path


def pure_step_theta(run_id: str, seed: int) -> tuple[dict[str, Any], dict[str, Any]]:
    genome = theta_genome.default_genome("step")
    genome.update(
        {
            "step_magnitude_m": 0.75,
            "step_axis": "x",
            "step_sign": 1,
            "step_time_s": 32.0,
            "mission_end_s": 54.0,
            "setpoint_rate_hz": 80.0,
        }
    )
    genome = theta_genome.normalize_genome(genome)
    tag = f"{run_id}_pure_step_s{seed}"
    theta = theta_genome.theta_from_genome(genome, tag, seed)
    theta["description"] += " P5 calibration probe: no wind, no physics mismatch, no shim."
    return genome, theta


def evaluate_property(
    ulog_path: Path,
    task_path: Path,
    theta: dict[str, Any],
    controller: str,
    thresholds: dict[str, float],
    output: Path,
) -> dict[str, Any]:
    result = property_oracle.evaluate_ulog(
        ulog_path,
        controller=controller,
        theta=theta,
        task=read_json(task_path),
        thresholds=thresholds,
    )
    write_json(output, result)
    return result


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    repo = REPO_ROOT
    root = (args.docs_root / args.run_id).resolve()
    evals = root / "evals"
    evals.mkdir(parents=True, exist_ok=True)
    env = m1.agent_env(repo)
    safety = args.safety_config.resolve()
    thresholds = dict(property_oracle.DEFAULT_THRESHOLDS)
    summary: dict[str, Any] = {"run_id": args.run_id, "seeds": args.seeds, "records": []}

    for seed in args.seeds:
        genome, theta = pure_step_theta(args.run_id, seed)
        tag = theta["tag"]
        run_dir = evals / f"s{seed}"
        run_dir.mkdir(parents=True, exist_ok=True)
        theta_path = run_dir / f"{tag}.json"
        write_json(theta_path, theta)
        record: dict[str, Any] = {
            "seed": seed,
            "tag": tag,
            "genome": genome,
            "theta_path": str(theta_path),
            "controllers": {},
        }
        prop_paths: dict[str, Path] = {}
        for controller in ["classical", "mcnn"]:
            print(f"RUN seed={seed} controller={controller}", flush=True)
            outputs = gate3.run_one(repo, theta_path, theta, controller, run_dir, env, args.run_timeout, safety)
            prop_path = run_dir / f"{tag}_{controller}_property_default.json"
            prop = evaluate_property(
                outputs["ulog"],
                outputs["task"],
                theta,
                controller,
                thresholds,
                prop_path,
            )
            prop_paths[controller] = prop_path
            record["controllers"][controller] = {
                "ulog": str(outputs["ulog"]),
                "task": str(outputs["task"]),
                "metrics": str(outputs["metrics"]),
                "property_default": str(prop_path),
                "rho": prop["rho"],
                "severity": prop["severity"],
                "p5_detail": prop["details"]["P5"],
                "controller_identity": prop["controller_identity"],
            }

        compare_path = run_dir / f"{tag}_property_compare_default.json"
        m1.run_checked(
            [
                sys.executable,
                str(repo / "scripts/m1_compare.py"),
                "--theta",
                str(theta_path),
                "--classical-property",
                str(prop_paths["classical"]),
                "--neural-property",
                str(prop_paths["mcnn"]),
                "--neural-controller",
                "mcnn",
                "--output",
                str(compare_path),
            ],
            cwd=repo,
            log=run_dir / f"{tag}_property_compare_default.log",
            env=env,
        )
        compare = read_json(compare_path)
        record["compare_default"] = {
            "path": str(compare_path),
            "primary_bug": compare["primary_bug"],
            "differential": compare["property_oracle"]["differential"],
        }
        summary["records"].append(record)
        write_json(root / "p5_step_default_summary.json", summary)
    return summary


def reconstruct_summary(args: argparse.Namespace) -> dict[str, Any]:
    repo = REPO_ROOT
    root = (args.docs_root / args.run_id).resolve()
    evals = root / "evals"
    env = m1.agent_env(repo)
    thresholds = dict(property_oracle.DEFAULT_THRESHOLDS)
    summary: dict[str, Any] = {"run_id": args.run_id, "seeds": args.seeds, "records": []}
    for seed in args.seeds:
        run_dir = evals / f"s{seed}"
        theta_path = next(run_dir.glob(f"{args.run_id}_pure_step_s{seed}.json"))
        theta = read_json(theta_path)
        tag = theta["tag"]
        record: dict[str, Any] = {
            "seed": seed,
            "tag": tag,
            "genome": theta.get("theta_genome", {}).get("genome"),
            "theta_path": str(theta_path),
            "controllers": {},
        }
        prop_paths: dict[str, Path] = {}
        for controller in ["classical", "mcnn"]:
            ulog = next(run_dir.glob(f"mcnn_gate3_*_{controller}.ulg"))
            task = next(run_dir.glob(f"mcnn_gate3_*_{controller}_task.json"))
            metrics = next(run_dir.glob(f"mcnn_gate3_*_{controller}_metrics.json"))
            prop_path = run_dir / f"{tag}_{controller}_property_default.json"
            prop = evaluate_property(ulog, task, theta, controller, thresholds, prop_path)
            prop_paths[controller] = prop_path
            record["controllers"][controller] = {
                "ulog": str(ulog),
                "task": str(task),
                "metrics": str(metrics),
                "property_default": str(prop_path),
                "rho": prop["rho"],
                "severity": prop["severity"],
                "p5_detail": prop["details"]["P5"],
                "controller_identity": prop["controller_identity"],
            }
        compare_path = run_dir / f"{tag}_property_compare_default.json"
        m1.run_checked(
            [
                sys.executable,
                str(repo / "scripts/m1_compare.py"),
                "--theta",
                str(theta_path),
                "--classical-property",
                str(prop_paths["classical"]),
                "--neural-property",
                str(prop_paths["mcnn"]),
                "--neural-controller",
                "mcnn",
                "--output",
                str(compare_path),
            ],
            cwd=repo,
            log=run_dir / f"{tag}_property_compare_default.log",
            env=env,
        )
        compare = read_json(compare_path)
        record["compare_default"] = {
            "path": str(compare_path),
            "primary_bug": compare["primary_bug"],
            "differential": compare["property_oracle"]["differential"],
        }
        summary["records"].append(record)
    write_json(root / "p5_step_default_summary.json", summary)
    return summary


def first_existing_dataset(ulog: ULog, names: list[str]):
    for name in names:
        dataset = property_oracle.first_dataset(ulog, name)
        if dataset is not None:
            return dataset
    return None


def position_for_record(record: dict[str, Any], controller: str, thresholds: dict[str, float]) -> dict[str, np.ndarray]:
    theta = read_json(local_path(record["theta_path"]))
    item = record["controllers"][controller]
    task = read_json(local_path(item["task"]))
    ulog = ULog(str(local_path(item["ulog"])))
    setpoint = property_oracle.first_dataset(ulog, "trajectory_setpoint")
    window = property_oracle.choose_window(ulog, theta, task, controller, setpoint, None, None)
    lpos = first_existing_dataset(ulog, ["vehicle_local_position_groundtruth", "vehicle_local_position"])
    return property_oracle.extract_position_reference(
        lpos,
        setpoint,
        int(window["analysis_start_us"]),
        int(window["control_end_us"]),
        thresholds,
    )


def round_up(value: float, quantum: float) -> float:
    return math.ceil(value / quantum) * quantum


def settling_time_s(position: dict[str, np.ndarray], step_us: int, epsilon_set_m: float, w_hold_s: float) -> float | None:
    ts = position["timestamp_us"]
    err = position["error_norm_m"]
    margin = epsilon_set_m - err
    hold_min = property_oracle.future_window_extreme(ts, margin, w_hold_s, want_max=False)
    latest_start = int(ts[-1] - int(round(w_hold_s * 1e6)))
    candidates = np.where((ts >= step_us) & (ts <= latest_start) & np.isfinite(hold_min) & (hold_min >= 0.0))[0]
    if len(candidates) == 0:
        return None
    return (int(ts[int(candidates[0])]) - int(step_us)) / 1e6


def calibrate_from_summary(summary: dict[str, Any], output_root: Path) -> dict[str, Any]:
    base_thresholds = dict(property_oracle.DEFAULT_THRESHOLDS)
    w_hold_s = 2.0
    samples: list[dict[str, Any]] = []
    floor_values: list[float] = []
    for record in summary["records"]:
        for controller in ["classical", "mcnn"]:
            position = position_for_record(record, controller, base_thresholds)
            ts = position["timestamp_us"]
            step_times = property_oracle.significant_setpoint_change_times(
                position["setpoint_logged_timestamp_us"],
                position["setpoint_logged_ned_m"],
                base_thresholds["s_min_m"],
                int(ts[0]),
                int(ts[-1]),
            )
            if len(step_times) != 1:
                raise ValueError(f"expected one P5 step for {record['tag']} {controller}, got {step_times}")
            step_us = int(step_times[0])
            hold_max = property_oracle.future_window_extreme(ts, position["error_norm_m"], w_hold_s, want_max=True)
            latest_start = int(ts[-1] - int(round(w_hold_s * 1e6)))
            candidates = (ts >= step_us) & (ts <= latest_start) & np.isfinite(hold_max)
            if not np.any(candidates):
                raise ValueError(f"no W_hold candidates for {record['tag']} {controller}")
            best_hold_max_error = float(np.nanmin(hold_max[candidates]))
            floor_values.append(best_hold_max_error)
            samples.append(
                {
                    "tag": record["tag"],
                    "controller": controller,
                    "step_us": step_us,
                    "best_W_hold_max_error_m": best_hold_max_error,
                    "post_step_error_max_m": float(np.nanmax(position["error_norm_m"][ts >= step_us])),
                }
            )

    epsilon_set_m = round_up(max(0.25, max(floor_values) * 3.0), 0.05)
    settle_times = []
    for sample in samples:
        record = next(item for item in summary["records"] if item["tag"] == sample["tag"])
        position = position_for_record(record, sample["controller"], base_thresholds)
        settle = settling_time_s(position, int(sample["step_us"]), epsilon_set_m, w_hold_s)
        sample["settling_time_s_at_epsilon"] = settle
        if settle is None:
            raise ValueError(f"no settling time found for {sample['tag']} {sample['controller']}")
        settle_times.append(float(settle))

    t_set_s = max(1.0, round_up(max(settle_times) + 1.0, 0.5))
    calibrated = dict(base_thresholds)
    calibrated["epsilon_set_m"] = epsilon_set_m
    calibrated["T_set_s"] = t_set_s
    calibrated["W_hold_s"] = w_hold_s

    calibration = {
        "epsilon_set_m": epsilon_set_m,
        "T_set_s": t_set_s,
        "W_hold_s": w_hold_s,
        "s_min_m": base_thresholds["s_min_m"],
        "basis": {
            "controllers": ["classical", "mcnn"],
            "seeds": summary["seeds"],
            "epsilon_rule": "ceil_0.05(max(0.25, max best-W_hold max error * 3.0))",
            "T_set_rule": "ceil_0.5(max measured settling time + 1.0 s)",
        },
        "samples": samples,
    }
    write_json(output_root / "p5_calibration_candidate.json", calibration)
    write_json(output_root / "p5_calibrated_thresholds.json", calibrated)
    return calibrated


def evaluate_calibrated(summary: dict[str, Any], thresholds: dict[str, float], output_root: Path) -> dict[str, Any]:
    env = m1.agent_env(REPO_ROOT)
    out: dict[str, Any] = {"run_id": summary["run_id"], "thresholds": thresholds, "records": []}
    for record in summary["records"]:
        theta = read_json(local_path(record["theta_path"]))
        prop_paths: dict[str, Path] = {}
        calibrated_record: dict[str, Any] = {"tag": record["tag"], "seed": record["seed"], "controllers": {}}
        run_dir = local_path(record["theta_path"]).parent
        for controller in ["classical", "mcnn"]:
            item = record["controllers"][controller]
            prop_path = run_dir / f"{record['tag']}_{controller}_property_calibrated.json"
            prop = evaluate_property(
                local_path(item["ulog"]),
                local_path(item["task"]),
                theta,
                controller,
                thresholds,
                prop_path,
            )
            prop_paths[controller] = prop_path
            calibrated_record["controllers"][controller] = {
                "property_calibrated": str(prop_path),
                "rho": prop["rho"],
                "severity": prop["severity"],
                "p5_detail": prop["details"]["P5"],
                "controller_identity": prop["controller_identity"],
            }
        compare_path = run_dir / f"{record['tag']}_property_compare_calibrated.json"
        m1.run_checked(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/m1_compare.py"),
                "--theta",
                str(local_path(record["theta_path"])),
                "--classical-property",
                str(prop_paths["classical"]),
                "--neural-property",
                str(prop_paths["mcnn"]),
                "--neural-controller",
                "mcnn",
                "--output",
                str(compare_path),
            ],
            cwd=REPO_ROOT,
            log=run_dir / f"{record['tag']}_property_compare_calibrated.log",
            env=env,
        )
        compare = read_json(compare_path)
        calibrated_record["compare_calibrated"] = {
            "path": str(compare_path),
            "primary_bug": compare["primary_bug"],
            "differential": compare["property_oracle"]["differential"],
        }
        out["records"].append(calibrated_record)
    write_json(output_root / "p5_step_calibrated_summary.json", out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--docs-root", type=Path, default=REPO_ROOT / "docs")
    parser.add_argument("--seeds", type=int, nargs="+", default=DEFAULT_SEEDS)
    parser.add_argument("--run-timeout", type=int, default=170)
    parser.add_argument("--safety-config", type=Path, default=REPO_ROOT / "config/m2_safety_envelope.json")
    parser.add_argument("--skip-run", action="store_true")
    args = parser.parse_args()

    root = (args.docs_root / args.run_id).resolve()
    if args.skip_run:
        summary_path = root / "p5_step_default_summary.json"
        summary = read_json(summary_path) if summary_path.exists() else reconstruct_summary(args)
    else:
        summary = run_probe(args)
    calibrated = calibrate_from_summary(summary, root)
    calibrated_summary = evaluate_calibrated(summary, calibrated, root)
    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "default_summary": str(root / "p5_step_default_summary.json"),
                "calibration": str(root / "p5_calibration_candidate.json"),
                "calibrated_summary": str(root / "p5_step_calibrated_summary.json"),
                "records": len(calibrated_summary["records"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
