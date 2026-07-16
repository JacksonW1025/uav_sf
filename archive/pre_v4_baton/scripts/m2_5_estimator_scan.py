#!/usr/bin/env python3
"""Generate and optionally run the M2.5 EKF/GPS delay pollution gradient."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import m2_map_elites


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIRM_SEEDS = [202651, 202652, 202653, 202654, 202655]


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


def theta_for_delay(run_id: str, delay_ms: float, seed: int) -> dict[str, Any]:
    genome = m2_map_elites.nominal_genome()
    genome.update(
        {
            "family_hint": "A_estimator",
            "gps_delay_ms": float(delay_ms),
            "gps_position_noise_m": 0.1,
            "gps_velocity_noise_m_s": 0.05,
            "gps_position_gate_sd": 8.0,
            "gps_velocity_gate_sd": 8.0,
            "ekf_tau_vel_s": 0.25,
            "ekf_tau_pos_s": 0.25,
            "imu_pos_x_m": 0.0,
            "imu_pos_y_m": 0.0,
            "imu_pos_z_m": 0.0,
            "switch_s": 18.0,
            "setpoint_rate_hz": 100.0,
            "setpoint_type": "sine",
            "setpoint_axis": "x",
            "sine_amplitude_m": 0.35,
            "sine_frequency_hz": 4.0,
            "step_m": 0.35,
        }
    )
    genome = m2_map_elites.normalize_genome(genome)
    tag = f"{run_id}_gpsdelay_{int(round(delay_ms)):03d}ms"
    theta = m2_map_elites.theta_from_genome(genome, tag, seed)
    theta["description"] = (
        "M2.5 targeted shared EKF estimate pollution probe: GNSS timestamp delay mismatch "
        "with low GPS noise and a finite sine setpoint to excite velocity-estimate phase error."
    )
    theta.setdefault("timing", {})["px4_shutdown_wall_slack_s"] = 22.0
    theta["m2_5"] = {
        "purpose": "targeted EKF/GPS delay gradient, not a full M2 rerun",
        "pollution_path": "SENS_GPS0_DELAY/SENS_GPS1_DELAY -> vehicle_gps_position timestamp_sample -> EKF2 -> vehicle_local_position",
        "fairness": "boot_px4_params and px4_params are identical for classical and RAPTOR runs",
    }
    return theta


def run_fairness(theta_path: Path, docs_dir: Path) -> Path | None:
    theta = json.loads(theta_path.read_text(encoding="utf-8"))
    tag = theta["tag"]
    classical_ulog = docs_dir / f"m1_{tag}_classical.ulg"
    raptor_ulog = docs_dir / f"m1_{tag}_raptor.ulg"
    if not classical_ulog.exists() or not raptor_ulog.exists():
        return None
    output = docs_dir / f"m2_5_fairness_{tag}.json"
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
    with (docs_dir / f"m2_5_fairness_{tag}.log").open("w", encoding="utf-8") as handle:
        handle.write("$ " + " ".join(cmd) + "\n")
        handle.flush()
        subprocess.run(cmd, cwd=str(REPO_ROOT), stdout=handle, stderr=subprocess.STDOUT, check=True)
    return output


def run_scan(args: argparse.Namespace) -> Path:
    run_id = args.run_id or datetime.now(timezone.utc).strftime("m2_5_estimator_scan_%Y%m%dT%H%M%SZ")
    run_dir = (REPO_ROOT / "docs" / run_id).resolve()
    theta_dir = run_dir / "theta"
    evals_dir = run_dir / "evals"
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "delays_ms": args.delays_ms,
        "run": bool(args.run),
        "confirm_repeats": args.confirm_repeats,
        "sim_speed_factor": args.sim_speed_factor,
        "run_timeout_s": args.run_timeout,
        "eval_timeout_s": args.eval_timeout,
        "scope_note": "M2.5 targeted gradient only; not a full M2b MAP-Elites rerun.",
    }
    write_json(run_dir / "metadata.json", metadata)
    env = m2_map_elites.os_environ_with_speed(args.sim_speed_factor)
    results: list[dict[str, Any]] = []

    for index, delay_ms in enumerate(args.delays_ms):
        theta = theta_for_delay(run_id, delay_ms, args.seed + index)
        theta_path = theta_dir / f"{theta['tag']}.json"
        docs_dir = evals_dir / theta["tag"]
        write_json(theta_path, theta)
        record: dict[str, Any] = {
            "index": index,
            "delay_ms": delay_ms,
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
                env,
            )
            record.update(result.as_dict())
            record["elapsed_wall_s_outer"] = time.monotonic() - start
            fairness_path = run_fairness(theta_path, docs_dir) if result.returncode == 0 else None
            record["fairness_path"] = str(fairness_path) if fairness_path else None
            record["ran"] = True
        results.append(record)
        append_jsonl(run_dir / "scan.jsonl", record)
        print(json.dumps(record, sort_keys=True), flush=True)

    primary = [item for item in results if item.get("primary_bug")]
    confirmations: list[dict[str, Any]] = []
    if args.run and primary and args.confirm_repeats > 0:
        candidate = primary[0]
        base_theta = json.loads(Path(candidate["theta_path"]).read_text(encoding="utf-8"))
        for ridx in range(args.confirm_repeats):
            seed = CONFIRM_SEEDS[ridx]
            theta = json.loads(json.dumps(base_theta))
            original_tag = theta["tag"]
            theta["tag"] = f"{original_tag}_confirm_s{seed}"
            theta["seed"] = seed
            theta.setdefault("m2_5", {})["confirmation_of"] = original_tag
            theta.setdefault("m2_5", {})["confirmation_seed"] = seed
            theta_path = run_dir / "confirm" / "theta" / f"{theta['tag']}.json"
            docs_dir = run_dir / "confirm" / "evals" / theta["tag"]
            result = m2_map_elites.evaluate_theta(
                theta,
                theta_path,
                docs_dir,
                1000 + ridx,
                args.run_timeout,
                args.eval_timeout,
                env,
            )
            fairness_path = run_fairness(theta_path, docs_dir) if result.returncode == 0 else None
            item = result.as_dict()
            item["fairness_path"] = str(fairness_path) if fairness_path else None
            confirmations.append(item)
            append_jsonl(run_dir / "confirmations.jsonl", item)
            print(json.dumps({"confirm": ridx, **item}, sort_keys=True), flush=True)

    write_json(run_dir / "results.json", results)
    write_json(run_dir / "confirmations.json", confirmations)
    write_summary(run_dir, results, confirmations)
    return run_dir


def write_summary(run_dir: Path, results: list[dict[str, Any]], confirmations: list[dict[str, Any]]) -> None:
    lines = [
        "# M2.5 Estimator Delay Scan",
        "",
        f"run_dir: `{run_dir.relative_to(REPO_ROOT)}`",
        f"evals: {sum(1 for item in results if item.get('ran'))}",
        f"primary_candidates: {sum(1 for item in results if item.get('primary_bug'))}",
        f"confirmation_repeats: {len(confirmations)}",
        f"confirmed_primary_bug: {bool(confirmations) and all(item.get('primary_bug') for item in confirmations)}",
        "",
        "## gradient",
    ]
    for item in results:
        lines.append(
            f"- delay={item['delay_ms']}ms quadrant={item.get('quadrant')} primary={item.get('primary_bug')} "
            f"returncode={item.get('returncode')} fairness=`{item.get('fairness_path')}`"
        )
    if confirmations:
        lines.extend(["", "## confirmations"])
        for item in confirmations:
            lines.append(f"- {item['tag']}: quadrant={item.get('quadrant')} primary={item.get('primary_bug')}")
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    parser.add_argument("--delays-ms", type=float, nargs="+", default=[0.0, 60.0, 120.0, 180.0, 240.0, 300.0])
    parser.add_argument("--seed", type=int, default=202625)
    parser.add_argument("--sim-speed-factor", type=float, default=1.0)
    parser.add_argument("--run-timeout", type=int, default=150)
    parser.add_argument("--eval-timeout", type=int, default=360)
    parser.add_argument("--confirm-repeats", type=int, default=3)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    run_dir = run_scan(args)
    print(f"M2_5_ESTIMATOR_SCAN_DIR={run_dir}")
    print(f"M2_5_ESTIMATOR_SCAN_SUMMARY={run_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
