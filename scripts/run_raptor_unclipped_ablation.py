#!/usr/bin/env python3
"""Run the locked 8-theta raptor_unclipped ablation plan."""

from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import m2_map_elites as m2  # noqa: E402
import theta_genome  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[1]
ANCHOR_RUN = REPO_ROOT / "runs/campaigns/raptor_gate0_anchor_recheck_20260705"
DENSE_RUN = REPO_ROOT / "runs/campaigns/raptor_switch_severity_dense_sweep_20260705"
SEEDS = [2026062940, 2026062941, 2026062942]
ANCHOR_IDS = ["pair1", "pair2", "pair4", "pair5"]
ATTITUDE_VALUES = [40.0, 42.0, 45.0, 48.0]


@dataclass(frozen=True)
class ThetaPoint:
    theta_id: str
    kind: str
    base_theta: dict[str, Any]
    source_artifact: str
    source_theta_path: str | None
    clipped_records: tuple[dict[str, Any], ...]
    plan_metadata: dict[str, Any]


@dataclass(frozen=True)
class PlannedEval:
    index: int
    point: ThetaPoint
    seed: int
    tag: str

    @property
    def theta_id(self) -> str:
        return self.point.theta_id


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_value(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".").replace("-", "m").replace(".", "p")


def attitude_point_id(value: float) -> str:
    return f"attitude_deg_{format_value(value)}"


def severity_from_record(record: dict[str, Any], controller: str) -> int | None:
    key = "classical_severity" if controller == "classical" else "neural_severity"
    value = record.get(key)
    if value is None and isinstance(record.get("fitness"), dict):
        value = record["fitness"].get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def severity_counts(records: list[dict[str, Any]] | tuple[dict[str, Any], ...], controller: str) -> dict[str, int]:
    values = [severity_from_record(record, controller) for record in records]
    return dict(Counter(str(value) for value in values if value is not None))


def stable_severity(records: list[dict[str, Any]] | tuple[dict[str, Any], ...], controller: str) -> int | None:
    counts = severity_counts(records, controller)
    if len(counts) == 1:
        return int(next(iter(counts)))
    return None


def find_anchor_theta(anchor_run: Path, anchor: str, case: str, seed: int) -> Path:
    theta_dir = anchor_run / "theta"
    matches = sorted(theta_dir.glob(f"*_{anchor}_{case}_s{seed}.json"))
    if matches:
        return matches[0]
    for path in sorted(theta_dir.glob("*.json")):
        theta = read_json(path)
        env_case = theta.get("environment", {}).get("case", {})
        if theta.get("seed") == seed and env_case.get("tag") == case:
            return path
    raise FileNotFoundError(f"missing anchor theta for {anchor} {case} seed {seed}")


def anchor_points(anchor_run: Path = ANCHOR_RUN) -> list[ThetaPoint]:
    plan = read_json(anchor_run / "anchor_plan.json")
    records = read_jsonl(anchor_run / "anchor_results.jsonl")
    records_by_anchor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        records_by_anchor[str(record.get("anchor"))].append(record)

    points: list[ThetaPoint] = []
    seen: set[str] = set()
    for item in plan.get("anchors", []):
        anchor = str(item["anchor"])
        if anchor in seen or anchor not in ANCHOR_IDS:
            continue
        theta_path = find_anchor_theta(anchor_run, anchor, str(item["case"]), int(item["seed"]))
        points.append(
            ThetaPoint(
                theta_id=anchor,
                kind="route_a_anchor",
                base_theta=read_json(theta_path),
                source_artifact=str((anchor_run / "anchor_plan.json").relative_to(REPO_ROOT)),
                source_theta_path=str(theta_path.relative_to(REPO_ROOT)),
                clipped_records=tuple(records_by_anchor.get(anchor, [])),
                plan_metadata={"anchor": anchor, "case": item["case"], "source_seed": int(item["seed"])},
            )
        )
        seen.add(anchor)
        if len(points) == len(ANCHOR_IDS):
            break

    missing = [anchor for anchor in ANCHOR_IDS if anchor not in seen]
    if missing:
        raise RuntimeError(f"anchor_plan missing required anchors: {missing}")
    return points


def genome_for_attitude(value: float, base: dict[str, Any]) -> dict[str, Any]:
    genome = theta_genome.default_genome("switching")
    genome.update(
        {
            **m2.route_a_profile_for(float(value), float(base["requested_rate_rad_s"])),
            "approach_phase_rad": float(base["approach_phase_rad"]),
            "wind_direction_rad": 0.0,
            "wind_speed_m_s": float(base["wind_speed_m_s"]),
            "setpoint_rate_hz": 80.0,
            "switch_delay_s": float(base["switch_delay_s"]),
        }
    )
    return m2.project_genome_to_subspace(genome, "route-a-switching", random.Random(0))


def attitude_points(dense_run: Path = DENSE_RUN) -> list[ThetaPoint]:
    config = read_json(dense_run / "sweep_config.json")
    base = config["base"]
    records = read_jsonl(dense_run / "sweep_results.jsonl")
    records_by_point: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        records_by_point[str(record.get("point_id"))].append(record)

    points: list[ThetaPoint] = []
    for value in ATTITUDE_VALUES:
        point_id = attitude_point_id(value)
        genome = genome_for_attitude(value, base)
        theta = theta_genome.theta_from_genome(genome, f"template_{point_id}", SEEDS[0])
        points.append(
            ThetaPoint(
                theta_id=point_id,
                kind="attitude_band",
                base_theta=theta,
                source_artifact=str((dense_run / "sweep_config.json").relative_to(REPO_ROOT)),
                source_theta_path=None,
                clipped_records=tuple(records_by_point.get(point_id, [])),
                plan_metadata={"axis": "attitude_deg", "value": value, "base": base},
            )
        )
    return points


def planned_theta_points() -> list[ThetaPoint]:
    return anchor_points() + attitude_points()


def planned_evals(
    points: list[ThetaPoint],
    *,
    run_id: str = "raptor_unclipped_ablation_plan",
    seeds: list[int] | tuple[int, ...] = SEEDS,
) -> list[PlannedEval]:
    plan: list[PlannedEval] = []
    for point in points:
        for seed in seeds:
            plan.append(
                PlannedEval(
                    index=len(plan),
                    point=point,
                    seed=int(seed),
                    tag=f"{run_id}_{point.theta_id}_s{seed}",
                )
            )
    return plan


def theta_for_eval(item: PlannedEval, run_id: str) -> dict[str, Any]:
    theta = copy.deepcopy(item.point.base_theta)
    theta["tag"] = f"{run_id}_{item.point.theta_id}_s{item.seed}"
    theta["seed"] = int(item.seed)
    theta.setdefault("raptor_unclipped_ablation", {}).update(
        {
            "run_id": run_id,
            "theta_id": item.point.theta_id,
            "kind": item.point.kind,
            "sut": "raptor_unclipped",
            "input_clipping": False,
            "source_artifact": item.point.source_artifact,
            "source_theta_path": item.point.source_theta_path,
            "plan_metadata": item.point.plan_metadata,
        }
    )
    return theta


def theta_summary(theta: dict[str, Any]) -> dict[str, Any]:
    """Expose the locked comparison axes without forcing reviewers to open theta JSON."""
    env = theta.get("environment", {})
    case = env.get("case", {})
    setpoint = theta.get("setpoint", {})
    trigger = setpoint.get("activation_trigger", {})
    circle = setpoint.get("circle", {})

    wind_n = case.get("wind_n", env.get("sih_wind_n", theta.get("px4_params", {}).get("SIH_WIND_N")))
    wind_e = case.get("wind_e", env.get("sih_wind_e", theta.get("px4_params", {}).get("SIH_WIND_E")))
    wind_speed = None
    if wind_n is not None or wind_e is not None:
        wind_speed = ((float(wind_n or 0.0) ** 2) + (float(wind_e or 0.0) ** 2)) ** 0.5

    return {
        "wind_n_m_s": wind_n,
        "wind_e_m_s": wind_e,
        "wind_speed_m_s": wind_speed,
        "requested_rate_min_rad_s": case.get("rate_min_rad_s", trigger.get("angular_rate_norm_min_rad_s")),
        "requested_rate_max_rad_s": case.get("rate_max_rad_s", trigger.get("angular_rate_norm_max_rad_s")),
        "attitude_min_deg": case.get("roll_pitch_min_deg", trigger.get("roll_pitch_abs_min_deg")),
        "attitude_max_deg": case.get("roll_pitch_max_deg", trigger.get("roll_pitch_abs_max_deg")),
        "expected_tilt_deg": env.get("expected_tilt_deg", env.get("switching", {}).get("expected_tilt_deg")),
        "switch_delay_s": case.get("switch_delay_s", trigger.get("switch_delay_s")),
        "approach_phase_rad": case.get("phase_rad", circle.get("phase_rad")),
        "circle_frequency_hz": case.get("frequency_hz", circle.get("frequency_hz")),
        "circle_radius_m": case.get("radius_m", circle.get("radius_m")),
    }


def cached_classical_severity(point: ThetaPoint) -> int | None:
    return stable_severity(point.clipped_records, "classical")


def cached_clipped_raptor_severity(point: ThetaPoint) -> int | None:
    return stable_severity(point.clipped_records, "raptor")


def evaluate_with_cached_classical(
    *,
    item: PlannedEval,
    theta: dict[str, Any],
    theta_path: Path,
    eval_dir: Path,
    env: dict[str, str],
    thresholds: dict[str, float],
    run_timeout_s: int,
    sut: str,
) -> dict[str, Any]:
    selected_sut = m2.sut_config(sut)
    if selected_sut.controller != "raptor":
        raise ValueError("raptor_unclipped ablation requires a RAPTOR-controller SUT")

    m2.write_json(theta_path, theta)
    eval_dir.mkdir(parents=True, exist_ok=True)
    output = m2.run_one_for_sut(
        selected_sut,
        theta_path,
        theta,
        selected_sut.controller,
        eval_dir,
        env,
        run_timeout_s,
        m2.SAFETY_CONFIG,
    )
    neural_property = m2.evaluate_ulog(
        output["ulog"],
        controller=selected_sut.controller,
        theta=theta,
        task=m2.load_json(output["task"]),
        thresholds=thresholds,
    )
    identity = neural_property.setdefault("controller_identity", {})
    policy_path = output.get("policy_tar")
    identity["policy_tar_staged"] = bool(policy_path is not None and policy_path.exists())
    identity_gate = m2.raptor_identity_gate(identity)
    identity["identity_gate"] = identity_gate
    identity["raptor_confirmed"] = bool(identity_gate.get("passed"))
    decontam_gate = m2.decontamination_gate(neural_property.get("window", {}).get("decontamination", {}))
    validity = {
        "decontamination": {selected_sut.controller: decontam_gate},
        selected_sut.identity_key: identity_gate,
        "rho_jitter_reproduction_margins": m2.reproduction_margins(),
    }
    property_path = eval_dir / f"{theta['tag']}_{selected_sut.controller}_property.json"
    validity_path = eval_dir / f"{theta['tag']}_validity.json"
    write_json(property_path, neural_property)
    write_json(validity_path, validity)

    classical_sev = cached_classical_severity(item.point)
    neural_sev = int(neural_property.get("severity", {}).get("severity"))
    valid = bool(decontam_gate.get("passed")) and bool(identity_gate.get("passed"))
    strict = bool(valid and classical_sev == 0 and neural_sev == 3)
    return {
        "index": item.index,
        "theta_id": item.point.theta_id,
        "kind": item.point.kind,
        "seed": item.seed,
        "tag": theta["tag"],
        "theta": theta_summary(theta),
        "sut": selected_sut.key,
        "neural_controller": selected_sut.controller,
        "input_clipping": selected_sut.input_clipping,
        "returncode": 0 if valid else 2,
        "valid": valid,
        "error": None if valid else "validity_gate_failed",
        "classical_source": "cached",
        "classical_severity": classical_sev,
        "clipped_raptor_severity": cached_clipped_raptor_severity(item.point),
        "neural_severity": neural_sev,
        "unclipped_raptor_severity": neural_sev,
        "strict_s0_vs_s3": strict,
        "strict_s0_vs_s3_hit": strict,
        "theta_path": str(theta_path),
        "evidence": {
            "ulog_paths": {selected_sut.controller: str(output["ulog"])},
            "task_paths": {selected_sut.controller: str(output["task"])},
            "property_paths": {selected_sut.controller: str(property_path)},
            "validity_path": str(validity_path),
            "validity": validity,
        },
    }


def evaluate_with_paired_classical(
    *,
    item: PlannedEval,
    theta: dict[str, Any],
    theta_path: Path,
    eval_dir: Path,
    env: dict[str, str],
    thresholds: dict[str, float],
    run_timeout_s: int,
    sut: str,
) -> dict[str, Any]:
    result = m2.evaluate_theta(
        theta,
        theta_path,
        eval_dir,
        item.index,
        run_timeout_s,
        env,
        thresholds,
        selected_parent_tag=f"raptor_unclipped_ablation:{item.point.theta_id}",
        selected_parent_quality=None,
        mock_evaluator=False,
        target_properties=m2.parse_target_properties("route-a-catastrophic"),
        fitness_mode="diff",
        sut=sut,
    )
    payload = result.as_dict()
    fitness = payload.get("fitness", {})
    valid = payload["returncode"] == 0
    return {
        "index": item.index,
        "theta_id": item.point.theta_id,
        "kind": item.point.kind,
        "seed": item.seed,
        "tag": theta["tag"],
        "theta": theta_summary(theta),
        "sut": payload.get("sut"),
        "neural_controller": payload.get("neural_controller"),
        "input_clipping": m2.sut_config(sut).input_clipping,
        "returncode": payload["returncode"],
        "valid": valid,
        "error": payload.get("error"),
        "classical_source": "paired_rerun",
        "classical_severity": fitness.get("classical_severity"),
        "clipped_raptor_severity": cached_clipped_raptor_severity(item.point),
        "neural_severity": fitness.get("neural_severity"),
        "unclipped_raptor_severity": fitness.get("neural_severity"),
        "strict_s0_vs_s3": bool(fitness.get("strict_s0_vs_s3")),
        "strict_s0_vs_s3_hit": bool(fitness.get("strict_s0_vs_s3")),
        "theta_path": payload.get("theta_path"),
        "compare_path": payload.get("compare_path"),
        "evidence": payload.get("evidence", {}),
    }


def value_counts(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    values = [item.get(key) for item in items if item.get(key) is not None]
    return dict(Counter(str(value) for value in values))


def stable_value(items: list[dict[str, Any]], key: str) -> int | None:
    counts = value_counts(items, key)
    if len(counts) == 1:
        return int(next(iter(counts)))
    return None


def summarize(run_id: str, sut: str, points: list[ThetaPoint], records: list[dict[str, Any]], elapsed: float) -> dict[str, Any]:
    records_by_theta: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        records_by_theta[str(record["theta_id"])].append(record)

    point_summaries: list[dict[str, Any]] = []
    for point in points:
        items = records_by_theta.get(point.theta_id, [])
        valid_items = [item for item in items if item.get("valid")]
        point_summaries.append(
            {
                "theta_id": point.theta_id,
                "kind": point.kind,
                "source_artifact": point.source_artifact,
                "source_theta_path": point.source_theta_path,
                "plan_metadata": point.plan_metadata,
                "theta": theta_summary(point.base_theta),
                "evals": len(items),
                "valid": len(valid_items),
                "invalid": len(items) - len(valid_items),
                "seeds": [item["seed"] for item in items],
                "classical_sev": cached_classical_severity(point) if cached_classical_severity(point) is not None else stable_value(valid_items, "classical_severity"),
                "classical_severity_counts": severity_counts(point.clipped_records, "classical") or value_counts(valid_items, "classical_severity"),
                "clipped_raptor_sev": cached_clipped_raptor_severity(point),
                "clipped_raptor_severity_counts": severity_counts(point.clipped_records, "raptor"),
                "unclipped_raptor_sev": stable_value(valid_items, "unclipped_raptor_severity"),
                "unclipped_raptor_severity_counts": value_counts(valid_items, "unclipped_raptor_severity"),
                "strict_s0_vs_s3_hits": sum(1 for item in valid_items if item.get("strict_s0_vs_s3_hit")),
                "strict_s0_vs_s3": sum(1 for item in valid_items if item.get("strict_s0_vs_s3_hit")) >= 2,
            }
        )

    return {
        "run_id": run_id,
        "sut": sut,
        "input_clipping": m2.sut_config(sut).input_clipping,
        "seeds": SEEDS,
        "theta_count": len(points),
        "planned_evals": len(points) * len(SEEDS),
        "total_evals": len(records),
        "total_valid": sum(1 for record in records if record.get("valid")),
        "total_invalid": sum(1 for record in records if not record.get("valid")),
        "total_strict_s0_vs_s3": sum(1 for record in records if record.get("strict_s0_vs_s3_hit")),
        "classical_reruns": sum(1 for record in records if record.get("classical_source") == "paired_rerun"),
        "elapsed_wall_s": elapsed,
        "points": point_summaries,
    }


def list_plan(run_id: str, sut: str, points: list[ThetaPoint]) -> dict[str, Any]:
    plan = planned_evals(points, run_id=run_id)
    return {
        "run_id": run_id,
        "sut": sut,
        "input_clipping": m2.sut_config(sut).input_clipping,
        "theta_count": len(points),
        "eval_count": len(plan),
        "seeds": SEEDS,
        "theta_ids": [point.theta_id for point in points],
        "evals": [
            {
                "index": item.index,
                "theta_id": item.theta_id,
                "kind": item.point.kind,
                "seed": item.seed,
                "tag": item.tag,
                "theta": theta_summary(item.point.base_theta),
                "classical_cache_severity": cached_classical_severity(item.point),
                "clipped_raptor_severity": cached_clipped_raptor_severity(item.point),
                "source_artifact": item.point.source_artifact,
                "source_theta_path": item.point.source_theta_path,
            }
            for item in plan
        ],
    }


def main() -> int:
    default_run_id = f"raptor_unclipped_ablation_{datetime.now().strftime('%Y%m%d')}"
    parser = argparse.ArgumentParser()
    parser.add_argument("--sut", choices=m2.SUTS, default="raptor_unclipped")
    parser.add_argument("--run-id", default=default_run_id)
    parser.add_argument("--sim-speed-factor", type=float, default=1.25)
    parser.add_argument("--run-timeout", type=int, default=230)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--max-evals", type=int, default=None, help="optional smoke cap; omit for the full 24-eval plan")
    args = parser.parse_args()

    selected_sut = m2.sut_config(args.sut)
    if selected_sut.controller != "raptor":
        raise SystemExit("run_raptor_unclipped_ablation.py requires a RAPTOR-controller SUT")

    points = planned_theta_points()
    if args.list_only:
        print(json.dumps(list_plan(args.run_id, args.sut, points), indent=2, sort_keys=True))
        return 0

    run_dir = REPO_ROOT / "runs/campaigns" / args.run_id
    theta_dir = run_dir / "theta"
    evals_dir = run_dir / "evals"
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run_dir / "ablation_config.json",
        {
            "run_id": args.run_id,
            "sut": args.sut,
            "input_clipping": selected_sut.input_clipping,
            "seeds": SEEDS,
            "theta_ids": [point.theta_id for point in points],
            "sim_speed_factor": args.sim_speed_factor,
            "run_timeout_s": args.run_timeout,
            "source_artifacts": {
                "anchors": str((ANCHOR_RUN / "anchor_plan.json").relative_to(REPO_ROOT)),
                "dense_sweep": str((DENSE_RUN / "sweep_config.json").relative_to(REPO_ROOT)),
            },
        },
    )

    results_path = run_dir / "ablation_results.jsonl"
    records: list[dict[str, Any]] = [] if args.no_resume else read_jsonl(results_path)
    seen_tags = {str(record.get("tag")) for record in records}
    plan = planned_evals(points, run_id=args.run_id)
    env = m2.os_environ_with_speed(args.sim_speed_factor)
    thresholds = m2.load_thresholds(None)
    start = time.monotonic()
    completed_this_run = 0

    for item in plan:
        if item.tag in seen_tags:
            continue
        if args.max_evals is not None and completed_this_run >= args.max_evals:
            break

        theta = theta_for_eval(item, args.run_id)
        theta_path = theta_dir / f"{item.tag}.json"
        eval_dir = evals_dir / item.tag
        try:
            if cached_classical_severity(item.point) is None:
                record = evaluate_with_paired_classical(
                    item=item,
                    theta=theta,
                    theta_path=theta_path,
                    eval_dir=eval_dir,
                    env=env,
                    thresholds=thresholds,
                    run_timeout_s=args.run_timeout,
                    sut=args.sut,
                )
            else:
                record = evaluate_with_cached_classical(
                    item=item,
                    theta=theta,
                    theta_path=theta_path,
                    eval_dir=eval_dir,
                    env=env,
                    thresholds=thresholds,
                    run_timeout_s=args.run_timeout,
                    sut=args.sut,
                )
        except Exception as exc:  # keep smoke/campaign failure structured
            write_json(theta_path, theta)
            record = {
                "index": item.index,
                "theta_id": item.theta_id,
                "kind": item.point.kind,
                "seed": item.seed,
                "tag": item.tag,
                "sut": args.sut,
                "neural_controller": selected_sut.controller,
                "input_clipping": selected_sut.input_clipping,
                "returncode": 1,
                "valid": False,
                "error": f"{type(exc).__name__}: {exc}",
                "classical_source": "cached" if cached_classical_severity(item.point) is not None else "paired_rerun",
                "classical_severity": cached_classical_severity(item.point),
                "clipped_raptor_severity": cached_clipped_raptor_severity(item.point),
                "neural_severity": None,
                "unclipped_raptor_severity": None,
                "strict_s0_vs_s3": False,
                "strict_s0_vs_s3_hit": False,
                "theta_path": str(theta_path),
                "evidence": {},
            }

        records.append(record)
        seen_tags.add(item.tag)
        completed_this_run += 1
        append_jsonl(results_path, record)
        summary = summarize(args.run_id, args.sut, points, records, time.monotonic() - start)
        write_json(run_dir / "summary.json", summary)
        print(
            json.dumps(
                {
                    "eval": item.index,
                    "theta_id": item.theta_id,
                    "seed": item.seed,
                    "returncode": record["returncode"],
                    "valid": record["valid"],
                    "classical_sev": record.get("classical_severity"),
                    "clipped_raptor_sev": record.get("clipped_raptor_severity"),
                    "unclipped_raptor_sev": record.get("unclipped_raptor_severity"),
                    "strict_s0_vs_s3": record.get("strict_s0_vs_s3_hit"),
                    "sut": args.sut,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    summary = summarize(args.run_id, args.sut, points, records, time.monotonic() - start)
    write_json(run_dir / "summary.json", summary)
    print(
        "ABLATION_COMPLETE",
        json.dumps(
            {
                "total_evals": summary["total_evals"],
                "total_valid": summary["total_valid"],
                "total_strict_s0_vs_s3": summary["total_strict_s0_vs_s3"],
                "classical_reruns": summary["classical_reruns"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
