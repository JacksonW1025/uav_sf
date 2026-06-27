#!/usr/bin/env python3
"""N=1 campaign runner with checkpoint/resume for Tier 1 wave runs.

This runner deliberately reuses the M2 evaluator/oracle path. Its job is the
campaign-scale orchestration that the original smoke-search CLI did not have:
sequential evals, per-eval atomic checkpoints, resume, and comparable guided /
random / grid strategies under one harness.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import m1_diff_runner as m1
import m2_map_elites
import theta_genome
from property_fitness import FITNESS_FLOOR
from validity_automation import reproduction_margins


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ROOT = REPO_ROOT / "runs" / "campaigns"
CHECKPOINT_SCHEMA_VERSION = 1
STRATEGIES = ["guided", "map-elites", "random", "grid"]
CANONICAL_STRATEGIES = {"guided": "guided", "map-elites": "guided", "random": "random", "grid": "grid"}
CONFIRM_SEEDS = m2_map_elites.CONFIRM_SEEDS

Evaluator = Callable[..., m2_map_elites.EvalResult]


@dataclass(frozen=True)
class CampaignConfig:
    run_id: str
    run_root: Path = DEFAULT_RUN_ROOT
    budget: int = 18
    bootstrap: int = 8
    seed: int = 20260624
    strategy: str = "guided"
    subspace: str = "full"
    target_properties: str = "auto"
    resolved_target_properties: list[str] | None = None
    run_timeout: int = 130
    eval_timeout: int = 260
    max_wall_clock_s: float = 0.0
    max_evals_this_run: int = 0
    sim_speed_factor: float = 1.25
    skip_build: bool = False
    thresholds_json: Path | None = None
    mock_evaluator: bool = False
    no_confirm: bool = False
    confirm_repeats: int = 3
    max_confirm_candidates: int = 3
    crossover: bool = False
    crossover_rate: float = 0.25

    @property
    def canonical_strategy(self) -> str:
        return CANONICAL_STRATEGIES[self.strategy]

    @property
    def run_dir(self) -> Path:
        return (self.run_root / self.run_id).resolve()


def config_to_json(config: CampaignConfig) -> dict[str, Any]:
    data = asdict(config)
    data["run_root"] = str(config.run_root)
    data["thresholds_json"] = str(config.thresholds_json) if config.thresholds_json is not None else None
    data["strategy"] = config.canonical_strategy
    return data


def config_from_json(data: dict[str, Any]) -> CampaignConfig:
    values = dict(data)
    values["run_root"] = Path(values.get("run_root") or DEFAULT_RUN_ROOT)
    thresholds = values.get("thresholds_json")
    values["thresholds_json"] = Path(thresholds) if thresholds else None
    values["strategy"] = CANONICAL_STRATEGIES[str(values.get("strategy", "guided"))]
    values.setdefault("resolved_target_properties", m2_map_elites.parse_target_properties(values.get("target_properties")))
    return CampaignConfig(**values)


def checkpoint_path_for(run_dir_or_checkpoint: Path) -> Path:
    path = run_dir_or_checkpoint
    if path.is_dir():
        return path / "checkpoint.json"
    return path


def _jsonify_rng_state(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonify_rng_state(item) for item in value]
    if isinstance(value, list):
        return [_jsonify_rng_state(item) for item in value]
    return value


def _tuple_rng_state(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tuple_rng_state(item) for item in value)
    return value


def rng_state_json(rng: random.Random) -> Any:
    return _jsonify_rng_state(rng.getstate())


def rng_from_json(state: Any) -> random.Random:
    rng = random.Random()
    rng.setstate(_tuple_rng_state(state))
    return rng


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def write_jsonl_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for record in records:
            json.dump(record, handle, sort_keys=True, allow_nan=False)
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(record, handle, sort_keys=True, allow_nan=False)
        handle.write("\n")


def make_metadata(config: CampaignConfig) -> dict[str, Any]:
    return {
        "run_id": config.run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_runner": "scripts/campaign_runner.py",
        "parallelism": 1,
        "seed": config.seed,
        "budget": config.budget,
        "strategy": config.canonical_strategy,
        "subspace": config.subspace,
        "bootstrap": config.bootstrap,
        "run_timeout_s": config.run_timeout,
        "eval_timeout_s": config.eval_timeout,
        "sim_speed_factor": config.sim_speed_factor,
        "px4_commit": "3042f906abaab7ab59ae838ad5a530a9ef3df9a6",
        "evaluator": "m2_map_elites.evaluate_theta",
        "oracle": "property_oracle via m2_map_elites.evaluate_theta",
        "validity_automation": {
            "symmetric_decontamination": True,
            "mode_23_identity_required": True,
            "rho_jitter_reproduction_margins": reproduction_margins(),
            "theta_seed_ulog_mapping": "theta_ulog_map.json and progress.theta_ulog_map",
        },
        "checkpoint": {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "path": str(config.run_dir / "checkpoint.json"),
            "atomic_replace": True,
            "contains_search_rng_state": True,
            "written_after_each_eval": True,
        },
        "single_eval_failure_policy": "record returncode/error and continue to the next eval",
        "baseline_comparability": "guided, random, and grid share budget, theta generator, evaluator, oracle, and validity gate",
        "target_property_override": config.target_properties,
        "resolved_target_properties": config.resolved_target_properties,
        "mock_evaluator": config.mock_evaluator,
    }


def new_state(config: CampaignConfig, rng: random.Random) -> dict[str, Any]:
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "run_id": config.run_id,
        "run_dir": str(config.run_dir),
        "config": config_to_json(config),
        "metadata": make_metadata(config),
        "eval_count": 0,
        "archive": {},
        "results": [],
        "progress_records": [],
        "primary_candidates": [],
        "theta_ulog_map": [],
        "validity_records": [],
        "confirmed": [],
        "rng_state": rng_state_json(rng),
        "completed": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "checkpoint_utc": None,
    }


def load_checkpoint(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    if int(state.get("schema_version", -1)) != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError(f"unsupported checkpoint schema in {path}")
    if "rng_state" not in state:
        raise ValueError(f"checkpoint missing rng_state: {path}")
    return state


def save_checkpoint(path: Path, state: dict[str, Any], rng: random.Random) -> None:
    state["rng_state"] = rng_state_json(rng)
    state["checkpoint_utc"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(path, state)


def materialize_state_files(run_dir: Path, state: dict[str, Any]) -> None:
    atomic_write_json(run_dir / "metadata.json", state["metadata"])
    write_jsonl_records(run_dir / "evals.jsonl", state["results"])
    write_jsonl_records(run_dir / "progress.jsonl", state["progress_records"])
    m2_map_elites.write_archive(run_dir / "archive.json", state["archive"])
    atomic_write_json(run_dir / "primary_candidates.json", state["primary_candidates"])
    atomic_write_json(run_dir / "theta_ulog_map.json", state["theta_ulog_map"])
    atomic_write_json(run_dir / "validity_records.json", state["validity_records"])
    atomic_write_json(run_dir / "confirmed_primary_bugs.json", state.get("confirmed", []))


def refresh_state_config(state: dict[str, Any], config: CampaignConfig) -> None:
    created_utc = state.get("metadata", {}).get("created_utc")
    state["config"] = config_to_json(config)
    state["metadata"] = make_metadata(config)
    if created_utc:
        state["metadata"]["created_utc"] = created_utc


def linspace(lo: float, hi: float, count: int) -> list[float]:
    if count <= 1:
        return [lo]
    return [lo + (hi - lo) * idx / float(count - 1) for idx in range(count)]


def steady_grid_genomes() -> list[dict[str, Any]]:
    wind: list[dict[str, Any]] = []
    for speed in linspace(0.5, 8.0, 5):
        for direction in [0.0, 0.5 * math.pi, math.pi, 1.5 * math.pi]:
            genome = theta_genome.default_genome("wind")
            genome.update(
                {
                    "wind_speed_m_s": speed,
                    "wind_direction_rad": direction,
                    "mission_end_s": 54.0,
                    "setpoint_rate_hz": 80.0,
                }
            )
            wind.append(theta_genome.normalize_genome(genome))

    physics: list[dict[str, Any]] = []
    for mass in [0.88, 1.0, 1.23]:
        for inertia in [0.75, 1.15, 1.55]:
            for twr in [0.92, 1.0, 1.13]:
                genome = theta_genome.default_genome("physics_mismatch")
                genome.update(
                    {
                        "mass_scale": mass,
                        "inertia_roll_scale": inertia,
                        "inertia_pitch_scale": inertia,
                        "inertia_yaw_scale": min(1.75, inertia + 0.10),
                        "twr_scale": twr,
                        "mission_end_s": 54.0,
                        "setpoint_rate_hz": 80.0,
                    }
                )
                physics.append(theta_genome.normalize_genome(genome))

    interleaved: list[dict[str, Any]] = []
    for idx in range(max(len(wind), len(physics))):
        if idx < len(wind):
            interleaved.append(wind[idx])
        if idx < len(physics):
            interleaved.append(physics[idx])
    return interleaved


def route_a_grid_genomes() -> list[dict[str, Any]]:
    genomes: list[dict[str, Any]] = []
    for roll_pitch in [38.0, 42.0, 46.0]:
        for rate in [1.10, 1.45, 1.80]:
            for delay in [0.0, 0.09, 0.18]:
                genome = theta_genome.default_genome("switching")
                genome.update(
                    {
                        "approach_radius_m": 2.30,
                        "approach_frequency_hz": 0.33,
                        "approach_phase_rad": 0.0,
                        "wind_speed_m_s": 6.0,
                        "wind_direction_rad": 0.0,
                        "setpoint_rate_hz": 80.0,
                        "switch_roll_pitch_deg": roll_pitch,
                        "switch_rate_rad_s": rate,
                        "switch_delay_s": delay,
                    }
                )
                genomes.append(theta_genome.normalize_genome(genome))
    return genomes


def step_grid_genomes() -> list[dict[str, Any]]:
    genomes: list[dict[str, Any]] = []
    for magnitude in [0.50, 1.00, 1.50]:
        for axis in ["x", "y", "z"]:
            for sign in [-1, 1]:
                genome = theta_genome.default_genome("step")
                genome.update(
                    {
                        "step_magnitude_m": magnitude,
                        "step_axis": axis,
                        "step_sign": sign,
                        "step_time_s": 32.0,
                        "mission_end_s": 54.0,
                        "setpoint_rate_hz": 80.0,
                    }
                )
                genomes.append(theta_genome.normalize_genome(genome))
    return genomes


def grid_genomes_for_subspace(subspace: str) -> list[dict[str, Any]]:
    if subspace == "steady-wind-physics":
        return steady_grid_genomes()
    if subspace == "route-a-switching":
        return route_a_grid_genomes()
    if subspace == "full":
        return steady_grid_genomes() + route_a_grid_genomes() + step_grid_genomes()
    raise ValueError(f"unknown subspace {subspace!r}")


def grid_candidate_genome(subspace: str, index: int) -> dict[str, Any]:
    genomes = grid_genomes_for_subspace(subspace)
    if not genomes:
        raise ValueError(f"grid strategy has no genomes for subspace {subspace!r}")
    return dict(genomes[index % len(genomes)])


def select_candidate(
    config: CampaignConfig,
    state: dict[str, Any],
    rng: random.Random,
    index: int,
) -> tuple[dict[str, Any], str, str | None, float | None]:
    selected_parent_tag = None
    selected_parent_quality = None
    strategy = config.canonical_strategy
    if strategy == "random":
        return m2_map_elites.random_candidate_genome(config.subspace, rng), "random_baseline", None, None
    if strategy == "grid":
        return grid_candidate_genome(config.subspace, index), "grid_baseline", None, None

    parent = m2_map_elites.select_parent(state["archive"], rng)
    if parent is None or index < config.bootstrap:
        return m2_map_elites.random_candidate_genome(config.subspace, rng), "bootstrap_random", None, None

    selected_parent_tag = parent["result"].get("tag")
    selected_parent_quality = float(parent["result"]["quality"])
    parent_genome = parent["genome"]
    if config.crossover and len(state["archive"]) > 1 and rng.random() < config.crossover_rate:
        mate = m2_map_elites.select_parent(state["archive"], rng)
        mate_genome = mate["genome"] if mate is not None else parent_genome
        genome = m2_map_elites.crossover_candidate_genome(parent_genome, mate_genome, config.subspace, rng)
        genome = m2_map_elites.mutate_candidate_genome(genome, config.subspace, rng)
        return genome, "elite_crossover_mutation", selected_parent_tag, selected_parent_quality

    genome = m2_map_elites.mutate_candidate_genome(parent_genome, config.subspace, rng)
    return genome, "elite_mutation", selected_parent_tag, selected_parent_quality


def feature_from_theta(theta: dict[str, Any]) -> tuple[str, float]:
    feature = theta.get("theta_genome", {}).get("map_elites", {})
    kind = str(feature.get("disturbance_type", "unknown"))
    bucket = str(feature.get("amplitude_bucket", "unknown"))
    severity = float(feature.get("severity", 0.0) or 0.0)
    return f"{kind}:{bucket}", severity


def failure_result(
    theta: dict[str, Any],
    theta_path: Path,
    docs_dir: Path,
    index: int,
    error: str,
    target_properties: list[str] | None,
    selected_parent_tag: str | None,
    selected_parent_quality: float | None,
) -> m2_map_elites.EvalResult:
    m2_map_elites.write_json(theta_path, theta)
    docs_dir.mkdir(parents=True, exist_ok=True)
    feature_bin, severity = feature_from_theta(theta)
    seed = int(theta["seed"]) if isinstance(theta.get("seed"), int) else None
    evidence = {
        "tag": theta.get("tag"),
        "seed": seed,
        "theta_path": str(theta_path),
        "docs_dir": str(docs_dir),
        "ulog_paths": {},
        "task_paths": {},
        "property_paths": {},
        "compare_path": None,
        "validity": {},
    }
    return m2_map_elites.EvalResult(
        index=index,
        tag=str(theta["tag"]),
        theta_path=str(theta_path),
        docs_dir=str(docs_dir),
        returncode=1,
        elapsed_wall_s=0.0,
        compare_path=None,
        quadrant=None,
        primary_bug=False,
        classical_usable=False,
        classical_safe=None,
        raptor_safe=None,
        infrastructure_limited=None,
        quality=FITNESS_FLOOR,
        fitness=m2_map_elites.empty_fitness(target_properties),
        feature_bin=feature_bin,
        severity=severity,
        selected_parent_tag=selected_parent_tag,
        selected_parent_quality=selected_parent_quality,
        mcnn_confirmed=None,
        error=error,
        seed=seed,
        evidence=evidence,
    )


def evaluate_one(
    config: CampaignConfig,
    state: dict[str, Any],
    rng: random.Random,
    env: dict[str, str],
    thresholds: dict[str, float],
    evaluator: Evaluator,
) -> tuple[m2_map_elites.EvalResult, dict[str, Any], str]:
    index = int(state["eval_count"])
    genome, selection_source, selected_parent_tag, selected_parent_quality = select_candidate(config, state, rng, index)
    tag = f"{config.run_id}_e{index:04d}"
    theta = theta_genome.theta_from_genome(genome, tag, config.seed + index)
    theta.setdefault("campaign_runner", {})["selection"] = {
        "strategy": config.canonical_strategy,
        "source": selection_source,
        "selected_parent_tag": selected_parent_tag,
        "selected_parent_quality": selected_parent_quality,
    }
    theta_path = config.run_dir / "theta" / f"{tag}.json"
    docs_dir = config.run_dir / "evals" / tag
    try:
        result = evaluator(
            theta,
            theta_path,
            docs_dir,
            index,
            config.run_timeout,
            env,
            thresholds,
            selected_parent_tag=selected_parent_tag,
            selected_parent_quality=selected_parent_quality,
            mock_evaluator=config.mock_evaluator,
            target_properties=config.resolved_target_properties,
        )
    except Exception as exc:  # keep a single bad eval from killing the campaign
        result = failure_result(
            theta,
            theta_path,
            docs_dir,
            index,
            f"{type(exc).__name__}: {exc}",
            config.resolved_target_properties,
            selected_parent_tag,
            selected_parent_quality,
        )
    return result, genome, selection_source


def best_result_record(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results:
        return None
    return max(results, key=lambda item: float(item.get("quality", FITNESS_FLOOR)))


def qd_score(archive: dict[str, dict[str, Any]]) -> float:
    return float(sum(max(0.0, float(value["result"]["quality"])) for value in archive.values()))


def progress_record(
    result: dict[str, Any],
    results: list[dict[str, Any]],
    archive: dict[str, dict[str, Any]],
    selection_source: str,
) -> dict[str, Any]:
    best = best_result_record(results)
    archive_best = None
    if archive:
        archive_best = max(archive.values(), key=lambda item: float(item["result"]["quality"]))["result"]
    evidence = result.get("evidence", {}) if isinstance(result.get("evidence"), dict) else {}
    return {
        "eval": result["index"],
        "tag": result["tag"],
        "seed": result.get("seed"),
        "selection_source": selection_source,
        "selected_parent_tag": result.get("selected_parent_tag"),
        "selected_parent_quality": result.get("selected_parent_quality"),
        "quality": result.get("quality", FITNESS_FLOOR),
        "best_so_far_tag": best.get("tag") if best else None,
        "best_so_far_quality": best.get("quality", FITNESS_FLOOR) if best else FITNESS_FLOOR,
        "archive_bins": len(archive),
        "archive_best_tag": archive_best.get("tag") if archive_best else None,
        "archive_best_quality": archive_best.get("quality") if archive_best else FITNESS_FLOOR,
        "qd_score": qd_score(archive),
        "feature_bin": result.get("feature_bin"),
        "best_property": result.get("fitness", {}).get("best_property"),
        "primary_bug": result.get("primary_bug", False),
        "returncode": result.get("returncode"),
        "error": result.get("error"),
        "mcnn_confirmed": result.get("mcnn_confirmed"),
        "theta_ulog_map": {
            "theta_path": result.get("theta_path"),
            "seed": result.get("seed"),
            "ulog_paths": evidence.get("ulog_paths", {}),
        },
    }


def update_state_after_eval(
    config: CampaignConfig,
    state: dict[str, Any],
    result: m2_map_elites.EvalResult,
    genome: dict[str, Any],
    selection_source: str,
) -> dict[str, Any]:
    result_record = result.as_dict()
    state["results"].append(result_record)
    append_jsonl(config.run_dir / "evals.jsonl", result_record)

    bin_name = result.feature_bin
    if result.classical_usable and (
        bin_name not in state["archive"] or result.quality > state["archive"][bin_name]["result"]["quality"]
    ):
        state["archive"][bin_name] = {
            "genome": genome,
            "theta_path": str(result.theta_path),
            "compare_path": result.compare_path,
            "result": result_record,
        }
        m2_map_elites.write_archive(config.run_dir / "archive.json", state["archive"])

    if result.primary_bug:
        candidate = {
            "genome": genome,
            "theta_path": result.theta_path,
            "compare_path": result.compare_path,
            "result": result_record,
        }
        state["primary_candidates"].append(candidate)
        atomic_write_json(config.run_dir / "primary_candidates.json", state["primary_candidates"])

    progress = progress_record(result_record, state["results"], state["archive"], selection_source)
    state["progress_records"].append(progress)
    append_jsonl(config.run_dir / "progress.jsonl", progress)

    evidence = result_record.get("evidence", {}) if isinstance(result_record.get("evidence"), dict) else {}
    theta_ulog = progress["theta_ulog_map"]
    state["theta_ulog_map"].append({"eval": result.index, "tag": result.tag, **theta_ulog})
    state["validity_records"].append(
        {
            "eval": result.index,
            "tag": result.tag,
            "seed": result.seed,
            "returncode": result.returncode,
            "error": result.error,
            "validity": evidence.get("validity", {}),
        }
    )
    atomic_write_json(config.run_dir / "theta_ulog_map.json", state["theta_ulog_map"])
    atomic_write_json(config.run_dir / "validity_records.json", state["validity_records"])

    state["eval_count"] = int(state["eval_count"]) + 1
    return progress


def prepare_environment(config: CampaignConfig) -> tuple[dict[str, str], dict[str, float]]:
    env = m2_map_elites.os_environ_with_speed(config.sim_speed_factor)
    thresholds = m2_map_elites.load_thresholds(config.thresholds_json)
    if config.mock_evaluator:
        return env, thresholds

    config.run_dir.mkdir(parents=True, exist_ok=True)
    if config.skip_build:
        m1.run_checked(
            [str(REPO_ROOT / "scripts/install_mcnn_sih_board.sh")],
            cwd=REPO_ROOT,
            log=config.run_dir / "build.log",
            env=env,
        )
        m1.run_checked(
            [str(REPO_ROOT / "scripts/install_m1_sih_x500.sh")],
            cwd=REPO_ROOT,
            log=config.run_dir / "build.log",
            env=env,
        )
    else:
        build_env = env.copy()
        build_env["PX4_MCNN_SIH_BUILD_LOG"] = str(config.run_dir / "px4_mcnn_sih_build.log")
        m1.run_checked(
            [str(REPO_ROOT / "scripts/build_px4_mcnn_sih.sh")],
            cwd=REPO_ROOT,
            log=config.run_dir / "build.log",
            env=build_env,
        )
    return env, thresholds


def print_eval_progress(progress: dict[str, Any]) -> None:
    print(
        json.dumps(
            {
                "eval": progress["eval"],
                "tag": progress["tag"],
                "strategy_source": progress["selection_source"],
                "feature_bin": progress["feature_bin"],
                "quality": progress["quality"],
                "best_so_far_quality": progress["best_so_far_quality"],
                "archive_bins": progress["archive_bins"],
                "qd_score": progress["qd_score"],
                "best_property": progress["best_property"],
                "primary_bug": progress["primary_bug"],
                "returncode": progress["returncode"],
                "error": progress["error"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


def write_summary(run_dir: Path, state: dict[str, Any]) -> None:
    def display_path(path: Path) -> str:
        try:
            return str(path.resolve().relative_to(REPO_ROOT))
        except ValueError:
            return str(path.resolve())

    results = state["results"]
    total = len(results)
    errors = sum(1 for result in results if result.get("error"))
    usable = sum(1 for result in results if result.get("classical_usable"))
    primary = sum(1 for result in results if result.get("primary_bug"))
    lines = [
        "# Campaign runner summary",
        "",
        f"run_dir: `{display_path(run_dir)}`",
        f"strategy: {state['metadata']['strategy']}",
        f"evals: {total}",
        f"budget: {state['metadata']['budget']}",
        f"completed: {state.get('completed', False)}",
        f"runner_errors: {errors}",
        f"classical_usable: {usable}",
        f"archive_bins: {len(state['archive'])}",
        f"primary_candidates: {primary}",
        f"confirmed_primary_bugs: {len(state.get('confirmed', []))}",
        f"checkpoint: `{display_path(Path(state['metadata']['checkpoint']['path']))}`",
        "",
        "## progress",
    ]
    progress = state["progress_records"]
    if not progress:
        lines.append("- none")
    else:
        wanted = {0, len(progress) // 2, len(progress) - 1}
        lines.append("| eval | best quality | archive bins | QD-score | source | error |")
        lines.append("|---:|---:|---:|---:|---|---|")
        for idx, record in enumerate(progress):
            if idx not in wanted:
                continue
            error = record.get("error") or ""
            lines.append(
                f"| {record['eval']} | {float(record['best_so_far_quality']):.6g} | "
                f"{record['archive_bins']} | {float(record['qd_score']):.6g} | "
                f"{record['selection_source']} | {error} |"
            )
    lines.extend(["", "## best elites"])
    if not state["archive"]:
        lines.append("- none")
    for key, elite in sorted(state["archive"].items(), key=lambda item: float(item[1]["result"]["quality"]), reverse=True)[
        :10
    ]:
        result = elite["result"]
        lines.append(
            f"- {key}: quality={float(result['quality']):.6g} theta="
            f"`{display_path(Path(elite['theta_path']))}`"
        )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def confirm_args(config: CampaignConfig) -> argparse.Namespace:
    return argparse.Namespace(
        max_confirm_candidates=config.max_confirm_candidates,
        confirm_repeats=config.confirm_repeats,
        run_timeout=config.run_timeout,
        mock_evaluator=config.mock_evaluator,
        resolved_target_properties=config.resolved_target_properties,
        sim_speed_factor=config.sim_speed_factor,
        thresholds_json=config.thresholds_json,
    )


def run_confirmations(config: CampaignConfig, state: dict[str, Any], rng: random.Random) -> None:
    if config.no_confirm or not state.get("completed") or not state["primary_candidates"]:
        return
    confirmed = m2_map_elites.confirm_candidates(config.run_dir, state["primary_candidates"], confirm_args(config))
    state["confirmed"] = confirmed
    save_checkpoint(config.run_dir / "checkpoint.json", state, rng)


def run_campaign(
    config: CampaignConfig,
    *,
    checkpoint: Path | None = None,
    evaluator: Evaluator = m2_map_elites.evaluate_theta,
) -> dict[str, Any]:
    checkpoint_path = checkpoint or (config.run_dir / "checkpoint.json")
    if checkpoint_path.exists():
        state = load_checkpoint(checkpoint_path)
        saved_config = config_from_json(state["config"])
        config = merge_resume_config(saved_config, config, state)
        refresh_state_config(state, config)
        rng = rng_from_json(state["rng_state"])
        materialize_state_files(config.run_dir, state)
    else:
        rng = random.Random(config.seed)
        state = new_state(config, rng)
        config.run_dir.mkdir(parents=True, exist_ok=True)
        materialize_state_files(config.run_dir, state)
        save_checkpoint(checkpoint_path, state, rng)

    env, thresholds = prepare_environment(config)
    start_wall = time.monotonic()
    evals_this_run = 0
    deadline = start_wall + config.max_wall_clock_s if config.max_wall_clock_s else None

    while int(state["eval_count"]) < config.budget:
        if config.max_evals_this_run and evals_this_run >= config.max_evals_this_run:
            break
        if deadline is not None and time.monotonic() >= deadline:
            break
        result, genome, selection_source = evaluate_one(config, state, rng, env, thresholds, evaluator)
        progress = update_state_after_eval(config, state, result, genome, selection_source)
        save_checkpoint(checkpoint_path, state, rng)
        print_eval_progress(progress)
        evals_this_run += 1

    state["completed"] = int(state["eval_count"]) >= config.budget
    save_checkpoint(checkpoint_path, state, rng)
    run_confirmations(config, state, rng)
    write_summary(config.run_dir, state)
    return state


def merge_resume_config(saved: CampaignConfig, requested: CampaignConfig, state: dict[str, Any]) -> CampaignConfig:
    invariant_fields = [
        "bootstrap",
        "seed",
        "strategy",
        "subspace",
        "target_properties",
        "resolved_target_properties",
        "sim_speed_factor",
        "thresholds_json",
        "mock_evaluator",
        "crossover",
        "crossover_rate",
    ]
    for field in invariant_fields:
        if getattr(saved, field) != getattr(requested, field):
            raise ValueError(f"resume config mismatch for {field}: checkpoint={getattr(saved, field)!r}, requested={getattr(requested, field)!r}")
    if requested.budget < int(state.get("eval_count", 0)):
        raise ValueError("requested budget is below checkpoint eval_count")
    return CampaignConfig(
        run_id=saved.run_id,
        run_root=saved.run_root,
        budget=requested.budget,
        bootstrap=saved.bootstrap,
        seed=saved.seed,
        strategy=saved.strategy,
        subspace=saved.subspace,
        target_properties=saved.target_properties,
        resolved_target_properties=saved.resolved_target_properties,
        run_timeout=requested.run_timeout,
        eval_timeout=requested.eval_timeout,
        max_wall_clock_s=requested.max_wall_clock_s,
        max_evals_this_run=requested.max_evals_this_run,
        sim_speed_factor=saved.sim_speed_factor,
        skip_build=requested.skip_build,
        thresholds_json=saved.thresholds_json,
        mock_evaluator=saved.mock_evaluator,
        no_confirm=requested.no_confirm,
        confirm_repeats=requested.confirm_repeats,
        max_confirm_candidates=requested.max_confirm_candidates,
        crossover=saved.crossover,
        crossover_rate=saved.crossover_rate,
    )


def resolve_new_config(args: argparse.Namespace) -> CampaignConfig:
    run_id = args.run_id or datetime.now(timezone.utc).strftime("campaign_%Y%m%dT%H%M%SZ")
    strategy = CANONICAL_STRATEGIES[args.strategy or "guided"]
    target_properties = args.target_properties or "auto"
    return CampaignConfig(
        run_id=run_id,
        run_root=(args.run_root or DEFAULT_RUN_ROOT).resolve(),
        budget=args.budget if args.budget is not None else 18,
        bootstrap=args.bootstrap if args.bootstrap is not None else 8,
        seed=args.seed if args.seed is not None else 20260624,
        strategy=strategy,
        subspace=args.subspace or "full",
        target_properties=target_properties,
        resolved_target_properties=m2_map_elites.parse_target_properties(target_properties),
        run_timeout=args.run_timeout if args.run_timeout is not None else 130,
        eval_timeout=args.eval_timeout if args.eval_timeout is not None else 260,
        max_wall_clock_s=args.max_wall_clock_s or 0.0,
        max_evals_this_run=args.max_evals_this_run or 0,
        sim_speed_factor=args.sim_speed_factor if args.sim_speed_factor is not None else 1.25,
        skip_build=bool(args.skip_build),
        thresholds_json=args.thresholds_json,
        mock_evaluator=bool(args.mock_evaluator),
        no_confirm=bool(args.no_confirm),
        confirm_repeats=args.confirm_repeats if args.confirm_repeats is not None else 3,
        max_confirm_candidates=args.max_confirm_candidates if args.max_confirm_candidates is not None else 3,
        crossover=bool(args.crossover),
        crossover_rate=args.crossover_rate if args.crossover_rate is not None else 0.25,
    )


def resolve_resume_config(args: argparse.Namespace, state: dict[str, Any]) -> CampaignConfig:
    saved = config_from_json(state["config"])
    return CampaignConfig(
        run_id=saved.run_id,
        run_root=saved.run_root,
        budget=args.budget if args.budget is not None else saved.budget,
        bootstrap=args.bootstrap if args.bootstrap is not None else saved.bootstrap,
        seed=args.seed if args.seed is not None else saved.seed,
        strategy=CANONICAL_STRATEGIES[args.strategy] if args.strategy is not None else saved.strategy,
        subspace=args.subspace if args.subspace is not None else saved.subspace,
        target_properties=args.target_properties if args.target_properties is not None else saved.target_properties,
        resolved_target_properties=m2_map_elites.parse_target_properties(
            args.target_properties if args.target_properties is not None else saved.target_properties
        ),
        run_timeout=args.run_timeout if args.run_timeout is not None else saved.run_timeout,
        eval_timeout=args.eval_timeout if args.eval_timeout is not None else saved.eval_timeout,
        max_wall_clock_s=args.max_wall_clock_s or 0.0,
        max_evals_this_run=args.max_evals_this_run or 0,
        sim_speed_factor=args.sim_speed_factor if args.sim_speed_factor is not None else saved.sim_speed_factor,
        skip_build=bool(args.skip_build),
        thresholds_json=args.thresholds_json if args.thresholds_json is not None else saved.thresholds_json,
        mock_evaluator=args.mock_evaluator if args.mock_evaluator is not None else saved.mock_evaluator,
        no_confirm=args.no_confirm if args.no_confirm is not None else saved.no_confirm,
        confirm_repeats=args.confirm_repeats if args.confirm_repeats is not None else saved.confirm_repeats,
        max_confirm_candidates=args.max_confirm_candidates
        if args.max_confirm_candidates is not None
        else saved.max_confirm_candidates,
        crossover=args.crossover if args.crossover is not None else saved.crossover,
        crossover_rate=args.crossover_rate if args.crossover_rate is not None else saved.crossover_rate,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--budget", type=int)
    parser.add_argument("--bootstrap", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--strategy", choices=STRATEGIES)
    parser.add_argument("--subspace", choices=m2_map_elites.SUBSPACES)
    parser.add_argument("--target-properties")
    parser.add_argument("--run-timeout", type=int)
    parser.add_argument("--eval-timeout", type=int)
    parser.add_argument("--max-wall-clock-s", type=float, default=0.0)
    parser.add_argument("--max-evals-this-run", type=int, default=0)
    parser.add_argument("--sim-speed-factor", type=float)
    parser.add_argument("--skip-build", action="store_true", default=False)
    parser.add_argument("--thresholds-json", type=Path)
    parser.add_argument("--mock-evaluator", action="store_true", default=None)
    parser.add_argument("--no-confirm", action="store_true", default=None)
    parser.add_argument("--confirm-repeats", type=int)
    parser.add_argument("--max-confirm-candidates", type=int)
    parser.add_argument("--crossover", action="store_true", default=None)
    parser.add_argument("--crossover-rate", type=float)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.resume_from is not None:
        checkpoint = checkpoint_path_for(args.resume_from.resolve())
        state = load_checkpoint(checkpoint)
        config = resolve_resume_config(args, state)
    else:
        config = resolve_new_config(args)
        checkpoint = config.run_dir / "checkpoint.json"
        if checkpoint.exists():
            print(f"checkpoint already exists; use --resume-from {config.run_dir}", file=sys.stderr)
            return 2
    state = run_campaign(config, checkpoint=checkpoint)
    print(f"CAMPAIGN_RUN_DIR={config.run_dir}")
    print(f"CAMPAIGN_CHECKPOINT={checkpoint}")
    print(f"CAMPAIGN_EVAL_COUNT={state['eval_count']}")
    print(f"CAMPAIGN_COMPLETED={state.get('completed', False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
