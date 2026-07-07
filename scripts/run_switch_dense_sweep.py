#!/usr/bin/env python3
"""Run the route-A switch severity dense sweep for a selectable SUT."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, "scripts")

import m2_map_elites as m2
import theta_genome


SEEDS = [2026062940, 2026062941, 2026062942]

BASE = {
    "roll_pitch_deg": 38.5,
    "requested_rate_rad_s": 1.15,
    "wind_speed_m_s": 0.0,
    "switch_delay_s": 0.09,
    "approach_phase_rad": 0.0,
}

AXES = {
    "attitude_deg": [28.0, 31.0, 34.0, 36.0, 38.0, 40.0, 42.0, 45.0, 48.0],
    "requested_rate_rad_s": [0.55, 0.75, 0.95, 1.15, 1.35, 1.55, 1.75, 2.05, 2.35],
    "wind_m_s": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
    "switch_delay_s": [0.0, 0.03, 0.06, 0.09, 0.12, 0.15, 0.18],
    "approach_phase_rad": [
        0.0,
        math.pi / 4.0,
        math.pi / 2.0,
        3.0 * math.pi / 4.0,
        math.pi,
        5.0 * math.pi / 4.0,
        3.0 * math.pi / 2.0,
        7.0 * math.pi / 4.0,
    ],
}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def genome_for(axis: str, value: float) -> dict[str, Any]:
    rp = BASE["roll_pitch_deg"]
    requested_rate = BASE["requested_rate_rad_s"]
    wind = BASE["wind_speed_m_s"]
    delay = BASE["switch_delay_s"]
    phase = BASE["approach_phase_rad"]
    if axis == "attitude_deg":
        rp = value
    elif axis == "requested_rate_rad_s":
        requested_rate = value
    elif axis == "wind_m_s":
        wind = value
    elif axis == "switch_delay_s":
        delay = value
    elif axis == "approach_phase_rad":
        phase = value
    else:
        raise ValueError(axis)

    genome = theta_genome.default_genome("switching")
    genome.update(
        {
            **m2.route_a_profile_for(rp, requested_rate),
            "approach_phase_rad": phase,
            "wind_direction_rad": 0.0,
            "wind_speed_m_s": wind,
            "setpoint_rate_hz": 80.0,
            "switch_delay_s": delay,
        }
    )
    return m2.project_genome_to_subspace(genome, "route-a-switching", random.Random(0))


def point_id(axis: str, value: float) -> str:
    safe = f"{value:.4f}".rstrip("0").rstrip(".").replace("-", "m").replace(".", "p")
    return f"{axis}_{safe}"


def planned_points() -> list[tuple[int, str, float, str, int]]:
    planned: list[tuple[int, str, float, str, int]] = []
    index = 0
    for axis, values in AXES.items():
        for value in values:
            pid = point_id(axis, float(value))
            for seed in SEEDS:
                planned.append((index, axis, float(value), pid, seed))
                index += 1
    return planned


def summarize(run_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    by_point: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_point[record["point_id"]].append(record)

    points = []
    for pid, items in sorted(by_point.items()):
        first = items[0]
        valid = [item for item in items if item["returncode"] == 0]
        hits = [item for item in valid if item["primary_bug"]]
        points.append(
            {
                "point_id": pid,
                "axis": first["axis"],
                "value": first["value"],
                "actual_genome": first["actual_genome"],
                "evals": len(items),
                "valid": len(valid),
                "invalid": len(items) - len(valid),
                "strict_s0_vs_s3_hits": len(hits),
                "hit_rate_valid": (len(hits) / len(valid)) if valid else None,
                "hit_rate_all": len(hits) / len(items),
                "classical_severity_counts": dict(Counter(str(item.get("classical_severity")) for item in valid)),
                "neural_severity_counts": dict(Counter(str(item.get("neural_severity")) for item in valid)),
                "seeds": [item["seed"] for item in items],
            }
        )

    by_axis: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        by_axis.setdefault(point["axis"], []).append(point)
    return {
        "run_id": run_id,
        "base": BASE,
        "seeds": SEEDS,
        "axis_points": {axis: len(values) for axis, values in AXES.items()},
        "total_points": len(points),
        "total_evals": len(records),
        "total_valid": sum(1 for record in records if record["returncode"] == 0),
        "total_invalid": sum(1 for record in records if record["returncode"] != 0),
        "total_strict_s0_vs_s3": sum(1 for record in records if record["primary_bug"]),
        "points": points,
        "axes": by_axis,
    }


def append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sut", choices=m2.SUTS, default="mcnn")
    parser.add_argument("--sim-speed-factor", type=float, default=1.25)
    parser.add_argument("--run-timeout", type=int, default=230)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    planned = planned_points()
    if args.list_only:
        print(
            json.dumps(
                {
                    "run_id": args.run_id,
                    "sut": args.sut,
                    "points": sum(len(values) for values in AXES.values()),
                    "evals": len(planned),
                    "seeds": SEEDS,
                    "axis_points": {axis: len(values) for axis, values in AXES.items()},
                },
                sort_keys=True,
            )
        )
        return 0

    run_dir = Path("runs/campaigns") / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run_dir / "sweep_config.json",
        {"base": BASE, "axes": AXES, "seeds": SEEDS, "sut": args.sut, "sim_speed_factor": args.sim_speed_factor},
    )

    env = m2.os_environ_with_speed(args.sim_speed_factor)
    thresholds = m2.load_thresholds(None)
    target_properties = m2.parse_target_properties("route-a-catastrophic")
    results_path = run_dir / "sweep_results.jsonl"
    records: list[dict[str, Any]] = [] if args.no_resume else read_jsonl(results_path)
    seen_tags = {str(record.get("tag")) for record in records}
    start = time.monotonic()

    for index, axis, value, pid, seed in planned:
        tag = f"{args.run_id}_{pid}_s{seed}"
        if tag in seen_tags:
            continue
        genome = genome_for(axis, value)
        theta = theta_genome.theta_from_genome(genome, tag, seed)
        theta.setdefault("dense_sweep", {}).update(
            {
                "run_id": args.run_id,
                "axis": axis,
                "value": value,
                "base": BASE,
                "point_id": pid,
                "sut": args.sut,
            }
        )
        result = m2.evaluate_theta(
            theta,
            run_dir / "theta" / f"{tag}.json",
            run_dir / "evals" / tag,
            index,
            args.run_timeout,
            env,
            thresholds,
            selected_parent_tag=f"dense_sweep:{pid}",
            selected_parent_quality=None,
            mock_evaluator=False,
            target_properties=target_properties,
            fitness_mode="diff",
            sut=args.sut,
        )
        result_record = result.as_dict()
        fitness = result_record.get("fitness", {})
        record = {
            "index": index,
            "axis": axis,
            "value": value,
            "point_id": pid,
            "seed": seed,
            "tag": tag,
            "sut": result_record.get("sut"),
            "neural_controller": result_record.get("neural_controller"),
            "returncode": result_record["returncode"],
            "error": result_record.get("error"),
            "primary_bug": bool(result_record.get("primary_bug")),
            "quality": result_record.get("quality"),
            "feature_bin": result_record.get("feature_bin"),
            "classical_severity": fitness.get("classical_severity"),
            "neural_severity": fitness.get("neural_severity"),
            "strict_s0_vs_s3": bool(fitness.get("strict_s0_vs_s3")),
            "actual_genome": {
                "switch_roll_pitch_deg": genome["switch_roll_pitch_deg"],
                "switch_rate_rad_s": genome["switch_rate_rad_s"],
                "approach_radius_m": genome["approach_radius_m"],
                "approach_frequency_hz": genome["approach_frequency_hz"],
                "approach_phase_rad": genome["approach_phase_rad"],
                "wind_speed_m_s": genome["wind_speed_m_s"],
                "switch_delay_s": genome["switch_delay_s"],
            },
            "theta_path": result_record["theta_path"],
            "compare_path": result_record.get("compare_path"),
            "evidence": result_record.get("evidence", {}),
        }
        records.append(record)
        seen_tags.add(tag)
        append_record(results_path, record)
        summary = summarize(args.run_id, records)
        summary["elapsed_wall_s"] = time.monotonic() - start
        write_json(run_dir / "summary.json", summary)
        print(
            json.dumps(
                {
                    "eval": index,
                    "axis": axis,
                    "value": value,
                    "seed": seed,
                    "returncode": result_record["returncode"],
                    "primary": bool(result_record.get("primary_bug")),
                    "csev": fitness.get("classical_severity"),
                    "nsev": fitness.get("neural_severity"),
                    "quality": result_record.get("quality"),
                    "sut": result_record.get("sut"),
                },
                sort_keys=True,
            ),
            flush=True,
        )

    summary = summarize(args.run_id, records)
    summary["elapsed_wall_s"] = time.monotonic() - start
    write_json(run_dir / "summary.json", summary)
    print(
        "SWEEP_COMPLETE",
        json.dumps(
            {
                key: summary[key]
                for key in ["total_evals", "total_valid", "total_invalid", "total_strict_s0_vs_s3"]
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
