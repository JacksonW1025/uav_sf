#!/usr/bin/env python3
"""M2b-1 NaN/Inf shared-state input-robustness probe."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import m2b_state_profiles as profiles


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(args: argparse.Namespace) -> Path:
    run_id = args.run_id or datetime.now(timezone.utc).strftime("m2b_nan_probe_%Y%m%dT%H%M%SZ")
    run_dir = (REPO_ROOT / "docs" / run_id).resolve()
    theta_dir = run_dir / "theta"
    evals_dir = run_dir / "evals"
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope_note": "M2b-1 input-robustness probe. NaN/Inf injection is not a realistic differential flight scenario by itself.",
        "px4_commit": "3042f906abaab7ab59ae838ad5a530a9ef3df9a6",
        "channels": args.channels,
        "profiles": args.profiles,
        "start_s": args.start_s,
        "end_s": args.end_s,
        "timebase_note": "M2B_START/M2B_END are PX4 boot-time seconds. Defaults target the observed RAPTOR-active window of the M1 runner, not task elapsed time.",
        "sim_speed_factor": args.sim_speed_factor,
        "shim_patch": "patches/px4/m2b_state_shim.patch",
    }
    profiles.write_json(run_dir / "metadata.json", metadata)
    records: list[dict[str, Any]] = []
    index = 0
    for channel in args.channels:
        for profile in args.profiles:
            tag = f"{run_id}_{channel}_{profile}"
            theta = profiles.base_state_theta(
                tag=tag,
                seed=args.seed + index,
                channel=channel,
                profile=profile,
                values=(0.0, 0.0, 0.0),
                twr=args.twr,
                sine_axis=args.axis,
                sine_amplitude_m=args.sine_amplitude_m,
                sine_frequency_hz=args.sine_frequency_hz,
                start_s=args.start_s,
                end_s=args.end_s,
                mitigation="not_relevant_nan_inf_input_robustness_probe",
            )
            theta.setdefault("m2b_1", {})["nan_inf_probe"] = True
            theta["sensor_perturbations"][0]["physical_credibility"] = (
                "NaN/Inf injection is an input-robustness probe for shared-state sanitation; "
                "a separate sensor-failure reachability path is required before calling it a realistic flight fault."
            )
            theta_path = theta_dir / f"{tag}.json"
            docs_dir = evals_dir / tag
            record: dict[str, Any] = {
                "index": index,
                "tag": tag,
                "channel": channel,
                "profile": profile,
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
                record["raptor_nan_rpm_defect"] = bool((record.get("raptor_active_motor_nan_count") or 0) > 0)
            else:
                profiles.write_json(theta_path, theta)
            records.append(record)
            profiles.append_jsonl(run_dir / "results.jsonl", record)
            print(json.dumps(record, sort_keys=True), flush=True)
            index += 1
    profiles.write_json(run_dir / "results.json", records)
    write_summary(run_dir, records)
    return run_dir


def write_summary(run_dir: Path, records: list[dict[str, Any]]) -> None:
    lines = [
        "# M2b-1 NaN/Inf State Probe",
        "",
        f"run_dir: `{run_dir.relative_to(REPO_ROOT)}`",
        "",
        "## results",
    ]
    if not records:
        lines.append("- none")
    for item in records:
        lines.append(
            f"- {item.get('channel')}/{item.get('profile')}: quadrant={item.get('quadrant')} "
            f"raptor_nan_rpm_defect={item.get('raptor_nan_rpm_defect')} "
            f"raptor_active_motor_nan_count={item.get('raptor_active_motor_nan_count')} "
            f"fair_state={item.get('fair_shared_state_shim_pollution')} "
            f"delivery_valid={item.get('state_shim_delivery_valid')} "
            f"theta=`{Path(item['theta_path']).relative_to(REPO_ROOT)}` fairness=`{item.get('fairness_path')}`"
        )
        if item.get("state_shim_delivery_failures"):
            lines.append(f"  delivery_failures={item.get('state_shim_delivery_failures')}")
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    parser.add_argument("--channels", nargs="+", choices=["velocity", "angular_velocity", "attitude"], default=["velocity", "angular_velocity", "attitude"])
    parser.add_argument("--profiles", nargs="+", choices=["nan", "inf"], default=["nan", "inf"])
    parser.add_argument("--seed", type=int, default=20260720)
    parser.add_argument("--twr", type=float, default=1.743)
    parser.add_argument("--axis", choices=["x", "y", "z"], default="x")
    parser.add_argument("--sine-amplitude-m", type=float, default=0.15)
    parser.add_argument("--sine-frequency-hz", type=float, default=1.0)
    parser.add_argument("--start-s", type=float, default=80.0)
    parser.add_argument("--end-s", type=float, default=80.5)
    parser.add_argument("--sim-speed-factor", type=float, default=4.0)
    parser.add_argument("--run-timeout", type=int, default=180)
    parser.add_argument("--eval-timeout", type=int, default=480)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    run_dir = run(args)
    print(f"M2B_NAN_PROBE_DIR={run_dir}")
    print(f"M2B_NAN_PROBE_SUMMARY={run_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
