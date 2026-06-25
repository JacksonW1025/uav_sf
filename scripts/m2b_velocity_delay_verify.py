#!/usr/bin/env python3
"""M2b-1 targeted verification for adversarial velocity-delay state shim."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import m2b_state_profiles as profiles


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(args: argparse.Namespace) -> Path:
    run_id = args.run_id or datetime.now(timezone.utc).strftime("m2b_velocity_delay_%Y%m%dT%H%M%SZ")
    run_dir = (REPO_ROOT / "docs" / run_id).resolve()
    theta_dir = run_dir / "theta"
    evals_dir = run_dir / "evals"
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope_note": "M2b-1 targeted velocity-delay shim verification; not M2b full search and not M3.",
        "px4_commit": "3042f906abaab7ab59ae838ad5a530a9ef3df9a6",
        "delays_ms": args.delays_ms,
        "sim_speed_factor": args.sim_speed_factor,
        "thrust_to_weight_ratio": args.twr,
        "sine_axis": args.axis,
        "sine_amplitude_m": args.sine_amplitude_m,
        "sine_frequency_hz": args.sine_frequency_hz,
        "mitigation_switch_found": False,
        "mitigation_note": "PX4 mc_raptor at 3042f906 has no vehicle_acceleration/sensor_accel subscription and no S2 accelerometer-IIR parameter or code path; this run measures the default no-IIR module.",
        "shim_patch": "patches/px4/m2b_state_shim.patch",
    }
    profiles.write_json(run_dir / "metadata.json", metadata)
    records: list[dict[str, Any]] = []
    for index, delay_ms in enumerate(args.delays_ms):
        tag = f"{run_id}_vdelay_{int(delay_ms):03d}ms"
        theta = profiles.base_state_theta(
            tag=tag,
            seed=args.seed + index,
            channel="velocity",
            profile="delay" if delay_ms > 0 else "off",
            delay_ms=int(delay_ms),
            values=(0.0, 0.0, 0.0),
            twr=args.twr,
            sine_axis=args.axis,
            sine_amplitude_m=args.sine_amplitude_m,
            sine_frequency_hz=args.sine_frequency_hz,
            mitigation="not_present_in_px4_mc_raptor_3042f906",
        )
        theta.setdefault("m2b_1", {})["velocity_delay_verification"] = True
        theta_path = theta_dir / f"{tag}.json"
        docs_dir = evals_dir / tag
        record: dict[str, Any] = {
            "index": index,
            "tag": tag,
            "delay_ms": int(delay_ms),
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
            record["ran"] = True
        else:
            profiles.write_json(theta_path, theta)
        records.append(record)
        profiles.append_jsonl(run_dir / "results.jsonl", record)
        print(json.dumps(record, sort_keys=True), flush=True)
    profiles.write_json(run_dir / "results.json", records)
    write_summary(run_dir, metadata, records)
    return run_dir


def write_summary(run_dir: Path, metadata: dict[str, Any], records: list[dict[str, Any]]) -> None:
    lines = [
        "# M2b-1 Velocity Delay Verification",
        "",
        f"run_dir: `{run_dir.relative_to(REPO_ROOT)}`",
        f"mitigation_switch_found: {str(metadata['mitigation_switch_found']).lower()}",
        f"mitigation_note: {metadata['mitigation_note']}",
        "",
        "## results",
    ]
    if not records:
        lines.append("- none")
    for item in records:
        lines.append(
            f"- delay={item.get('delay_ms')}ms quadrant={item.get('quadrant')} primary={item.get('primary_bug')} "
            f"quality={item.get('quality')} fair_state={item.get('fair_shared_state_shim_pollution')} "
            f"classical_rms={item.get('classical_tracking_rms_m')} raptor_rms={item.get('raptor_tracking_rms_m')} "
            f"theta=`{Path(item['theta_path']).relative_to(REPO_ROOT)}` fairness=`{item.get('fairness_path')}`"
        )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    parser.add_argument("--delays-ms", type=int, nargs="+", default=[0, 10, 20, 30])
    parser.add_argument("--seed", type=int, default=20260710)
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
    print(f"M2B_VELOCITY_DELAY_DIR={run_dir}")
    print(f"M2B_VELOCITY_DELAY_SUMMARY={run_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
