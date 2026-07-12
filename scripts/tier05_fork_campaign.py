#!/usr/bin/env python3
"""Serial Tier-0.5 fork campaign on frozen same-theta, same-seed cases."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import px4_race_r4_experiment as r4


REPO = Path(__file__).resolve().parents[1]
CLASSIFIER = REPO / "scripts/fuzz1c_decontam_analyze.py"
CLASSIFIER_SHA256 = "11568fe11729751fa6952a90e472d91ccf8d76e5765e22802c237dbe051adc4a"
DENSE_THETA = (
    REPO
    / "runs/campaigns/switch_severity_dense_sweep_20260630/theta/"
    / "switch_severity_dense_sweep_20260630_wind_m_s_0_s2026062942.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def theta_for(case: str) -> dict:
    if case == "dense_low_modal":
        return r4.load_json(DENSE_THETA)
    if case in {"pair4", "pair1"}:
        return r4.gate_theta(case)[0]
    raise KeyError(case)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--docs-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--rep-start", type=int, default=1)
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=["dense_low_modal", "pair4", "pair1"],
        default=["dense_low_modal", "pair4", "pair1"],
    )
    parser.add_argument("--run-timeout", type=int, default=190)
    parser.add_argument("--safety-config", type=Path, default=REPO / "config/m2_safety_envelope.json")
    args = parser.parse_args()

    if sha256(CLASSIFIER) != CLASSIFIER_SHA256:
        raise RuntimeError("frozen classifier hash mismatch")
    if os.environ.get("M1_TIMING_MODE") != "hardened":
        raise RuntimeError("Stage 3 requires M1_TIMING_MODE=hardened")
    if os.environ.get("PX4_SIM_SPEED_FACTOR") != "1.25":
        raise RuntimeError("Stage 3 requires PX4_SIM_SPEED_FACTOR=1.25")

    docs = args.docs_dir.resolve()
    docs.mkdir(parents=True, exist_ok=True)
    run_root_base = docs / "px4_roots"
    env = r4.m1.agent_env(REPO)
    records: list[dict] = []
    partial = docs / "campaign_partial.json"
    if partial.exists():
        previous = r4.load_json(partial)
        records.extend(previous.get("records", []))

    for case in args.cases:
        theta = theta_for(case)
        for rep in range(args.rep_start, args.rep_start + args.repetitions):
            run_dir = docs / "evals" / f"{case}_H_rep{rep:02d}_{theta['tag']}"
            if run_dir.exists():
                raise FileExistsError(f"refusing to overwrite existing run: {run_dir}")
            print(f"TIER05_STAGE3 case={case} rep={rep}", flush=True)
            record = r4.run_mcnn(
                repo=REPO,
                build_dir=args.build_dir.resolve(),
                docs=docs,
                run_root_base=run_root_base,
                theta=theta,
                case_label=case,
                rep=rep,
                arm="H",
                extra_params={},
                env=env,
                run_timeout_s=args.run_timeout,
                safety_config=args.safety_config.resolve(),
            )
            records.append(record)
            r4.write_json(partial, {"records": records})

    payload = {
        "phase": "tier05_stage3",
        "timing_mode": "hardened",
        "speed_factor": 1.25,
        "classifier_sha256": CLASSIFIER_SHA256,
        "cases": args.cases,
        "rep_start": args.rep_start,
        "repetitions": args.repetitions,
        "records": records,
    }
    r4.write_json(docs / "campaign_results.json", payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
