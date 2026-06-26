#!/usr/bin/env python3
"""Tier 1 one-shot parallel profiling harness for real M2 evaluations."""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATE = datetime.now().strftime("%Y%m%d")
RHO_PROPERTIES = ["P1", "P2", "P4", "P5", "P6", "P7"]
METRIC_KEYS = [
    "tracking_error_rms_m",
    "tracking_error_max_m",
    "final_error_m",
    "roll_pitch_max_deg",
    "angular_rate_max_rad_s",
    "motor_saturation_ratio",
    "min_altitude_agl_m",
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, allow_nan=False)
        handle.write("\n")


def parse_csv_ints(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def parse_csv_floats(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def parse_cpuset_groups(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def profile_genome(mission_end_s: float) -> dict[str, Any]:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import theta_genome

    genome = theta_genome.default_genome("physics_mismatch")
    genome.update(
        {
            "mass_scale": 1.0978,
            "inertia_roll_scale": 0.8140,
            "inertia_pitch_scale": 1.4403,
            "inertia_yaw_scale": 1.3517,
            "twr_scale": 0.9342,
            "mission_end_s": mission_end_s,
            "setpoint_rate_hz": 80.0,
        }
    )
    return theta_genome.normalize_genome(genome)


def compact_controller_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return {key: payload.get(key) for key in METRIC_KEYS if key in payload}


def worker_main(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import m2_map_elites
    import theta_genome

    docs_dir = args.docs_dir.resolve()
    theta_path = args.theta_path.resolve()
    result_path = args.result_json.resolve()
    docs_dir.mkdir(parents=True, exist_ok=True)

    genome = profile_genome(args.mission_end_s)
    theta = theta_genome.theta_from_genome(genome, args.tag, args.theta_seed)
    theta.setdefault("parallel_profile", {})["profile_case"] = {
        "fixed_theta_seed": args.theta_seed,
        "sim_speed_factor": args.sim_speed_factor,
        "worker_label": args.worker_label,
        "note": "tag differs per run; theta genome and seed stay fixed for crosstalk comparison",
    }

    env = m2_map_elites.os_environ_with_speed(args.sim_speed_factor)
    thresholds = m2_map_elites.load_thresholds(args.thresholds_json)
    result = m2_map_elites.evaluate_theta(
        theta,
        theta_path,
        docs_dir,
        0,
        args.run_timeout,
        env,
        thresholds,
        mock_evaluator=False,
        target_properties=m2_map_elites.parse_target_properties(args.target_properties),
    )

    classical_property_path = docs_dir / f"{args.tag}_classical_property.json"
    mcnn_property_path = docs_dir / f"{args.tag}_mcnn_property.json"
    classical_property = load_json(classical_property_path) if classical_property_path.exists() else {}
    mcnn_property = load_json(mcnn_property_path) if mcnn_property_path.exists() else {}
    compact = {
        "worker_label": args.worker_label,
        "tag": args.tag,
        "returncode": result.returncode,
        "elapsed_wall_s": result.elapsed_wall_s,
        "error": result.error,
        "quality": result.quality,
        "fitness": result.fitness,
        "compare_path": result.compare_path,
        "theta_path": str(theta_path),
        "docs_dir": str(docs_dir),
        "sim_speed_factor": args.sim_speed_factor,
        "cpuset_cpus": os.environ.get("PROFILE_CPUSET_CPUS"),
        "rho": {
            "classical": classical_property.get("rho", {}),
            "mcnn": mcnn_property.get("rho", {}),
        },
        "severity": {
            "classical": classical_property.get("severity", {}),
            "mcnn": mcnn_property.get("severity", {}),
        },
        "controller_identity": mcnn_property.get("controller_identity", {}),
        "window_terminal": {
            "classical": classical_property.get("window", {}).get("terminal", {}),
            "mcnn": mcnn_property.get("window", {}).get("terminal", {}),
        },
        "metrics": {
            "classical": compact_controller_metrics(docs_dir / f"mcnn_gate3_{args.tag}_classical_metrics.json"),
            "mcnn": compact_controller_metrics(docs_dir / f"mcnn_gate3_{args.tag}_mcnn_metrics.json"),
        },
    }
    write_json(result_path, compact)
    print(json.dumps({"worker_result": str(result_path), "returncode": result.returncode, "error": result.error}))
    return 0 if result.returncode == 0 else result.returncode


def docker_stats_command(names: list[str]) -> list[str]:
    quoted_names = " ".join(shlex.quote(name) for name in names)
    fmt = "{{.Name}}\\t{{.CPUPerc}}\\t{{.MemUsage}}"
    return ["sg", "docker", "-c", f"docker stats --no-stream --format {shlex.quote(fmt)} {quoted_names}"]


def parse_size_mib(value: str) -> float | None:
    number_unit = value.strip().split()[0]
    units = [
        ("tib", 1024.0 * 1024.0),
        ("gib", 1024.0),
        ("mib", 1.0),
        ("kib", 1.0 / 1024.0),
        ("gb", 1000.0 * 1000.0 * 1000.0 / (1024.0 * 1024.0)),
        ("mb", 1000.0 * 1000.0 / (1024.0 * 1024.0)),
        ("kb", 1000.0 / (1024.0 * 1024.0)),
        ("b", 1.0 / (1024.0 * 1024.0)),
    ]
    for unit, scale in units:
        if number_unit.lower().endswith(unit):
            number = number_unit[: -len(unit)]
            try:
                return float(number) * scale
            except ValueError:
                return None
    return None


def sample_docker_stats(names: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            docker_stats_command(names),
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=12,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "containers": {}}
    containers: dict[str, Any] = {}
    for line in completed.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        name, cpu_text, mem_text = parts
        try:
            cpu_pct = float(cpu_text.strip().rstrip("%"))
        except ValueError:
            cpu_pct = None
        mem_mib = parse_size_mib(mem_text.split("/")[0])
        containers[name] = {"cpu_pct": cpu_pct, "mem_mib": mem_mib, "raw": mem_text}
    return {
        "ok": completed.returncode == 0,
        "error": completed.stderr.strip() if completed.returncode else None,
        "containers": containers,
    }


def worker_command(
    *,
    container_name: str,
    tag: str,
    worker_dir: Path,
    theta_seed: int,
    run_timeout: int,
    sim_speed_factor: float,
    ros_domain_id: int,
    agent_port: int,
    target_properties: str,
    mission_end_s: float,
    cpuset_cpus: str | None,
) -> list[str]:
    docs_dir = worker_dir / "docs"
    theta_path = worker_dir / f"{tag}.json"
    result_json = worker_dir / "worker_result.json"
    tmp_dir = worker_dir / "tmp"
    px4_roots = worker_dir / "px4_roots"
    worker_dir.mkdir(parents=True, exist_ok=True)

    def container_path(path: Path) -> str:
        return str(Path("/workspace") / path.resolve().relative_to(REPO_ROOT))

    inner_parts = [
        "set -euo pipefail",
        f"mkdir -p {shlex.quote(container_path(tmp_dir))} {shlex.quote(container_path(px4_roots))}",
        f"export ROS_DOMAIN_ID={ros_domain_id}",
        f"export AGENT_PORT={agent_port}",
        f"export PX4_UXRCE_DDS_PORT={agent_port}",
        "export PX4_UXRCE_DDS_NS=",
        f"export TMPDIR={shlex.quote(container_path(tmp_dir))}",
        f"export PX4_RUN_ROOT_BASE={shlex.quote(container_path(px4_roots))}",
        f"export PROFILE_CPUSET_CPUS={shlex.quote(cpuset_cpus or '')}",
        " ".join(
            [
                "python3",
                "scripts/parallel_profile.py",
                "--worker",
                "--tag",
                shlex.quote(tag),
                "--worker-label",
                shlex.quote(worker_dir.name),
                "--docs-dir",
                shlex.quote(container_path(docs_dir)),
                "--theta-path",
                shlex.quote(container_path(theta_path)),
                "--result-json",
                shlex.quote(container_path(result_json)),
                "--theta-seed",
                str(theta_seed),
                "--run-timeout",
                str(run_timeout),
                "--sim-speed-factor",
                str(sim_speed_factor),
                "--target-properties",
                shlex.quote(target_properties),
                "--mission-end-s",
                str(mission_end_s),
            ]
        ),
    ]
    inner = "; ".join(inner_parts)
    outer = (
        f"cd {shlex.quote(str(REPO_ROOT))} && "
        f"CONTAINER_NAME={shlex.quote(container_name)} "
        f"ROS_DOMAIN_ID={ros_domain_id} "
        f"DOCKER_CPUSET_CPUS={shlex.quote(cpuset_cpus or '')} "
        f"./docker/run.sh bash -lc {shlex.quote(inner)}"
    )
    return ["sg", "docker", "-c", outer]


def run_batch(
    *,
    run_dir: Path,
    run_id: str,
    label: str,
    n: int,
    sim_speed_factor: float,
    args: argparse.Namespace,
    domain_base: int,
    port_base: int,
) -> dict[str, Any]:
    batch_dir = run_dir / "evals" / label
    batch_dir.mkdir(parents=True, exist_ok=True)
    processes: list[dict[str, Any]] = []
    container_names: list[str] = []
    cpuset_groups = parse_cpuset_groups(getattr(args, "cpuset_groups", ""))
    if cpuset_groups and len(cpuset_groups) < n:
        raise ValueError(f"need at least {n} cpuset groups, got {len(cpuset_groups)}")
    start = time.monotonic()
    for slot in range(n):
        tag = f"{run_id}_{label}_w{slot:02d}"
        worker_dir = batch_dir / tag
        container_name = f"uavsf_{run_id}_{label}_w{slot:02d}".replace("-", "_")
        container_names.append(container_name)
        log_path = worker_dir / "container.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        command = worker_command(
            container_name=container_name,
            tag=tag,
            worker_dir=worker_dir,
            theta_seed=args.theta_seed,
            run_timeout=args.run_timeout,
            sim_speed_factor=sim_speed_factor,
            ros_domain_id=domain_base + slot,
            agent_port=port_base + slot,
            target_properties=args.target_properties,
            mission_end_s=args.mission_end_s,
            cpuset_cpus=cpuset_groups[slot] if cpuset_groups else None,
        )
        log_handle = log_path.open("w", encoding="utf-8")
        process = subprocess.Popen(command, cwd=str(REPO_ROOT), stdout=log_handle, stderr=subprocess.STDOUT)
        processes.append(
            {
                "slot": slot,
                "tag": tag,
                "worker_dir": worker_dir,
                "container_name": container_name,
                "cpuset_cpus": cpuset_groups[slot] if cpuset_groups else None,
                "log_path": log_path,
                "process": process,
                "log_handle": log_handle,
            }
        )

    stats_samples: list[dict[str, Any]] = []
    while True:
        running = [entry for entry in processes if entry["process"].poll() is None]
        if not running:
            break
        stats = sample_docker_stats(container_names)
        stats["t_wall_s"] = time.monotonic() - start
        stats_samples.append(stats)
        print(
            json.dumps(
                {
                    "batch": label,
                    "running": len(running),
                    "n": n,
                    "speed": sim_speed_factor,
                    "t_wall_s": round(stats["t_wall_s"], 1),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        time.sleep(args.stats_interval_s)

    elapsed = time.monotonic() - start
    results: list[dict[str, Any]] = []
    for entry in processes:
        rc = entry["process"].wait()
        entry["log_handle"].close()
        result_json = entry["worker_dir"] / "worker_result.json"
        result = load_json(result_json) if result_json.exists() else {}
        result.update(
            {
                "container_returncode": rc,
                "container_name": entry["container_name"],
                "cpuset_cpus": entry["cpuset_cpus"],
                "container_log": str(entry["log_path"]),
            }
        )
        if not result_json.exists():
            result["error"] = f"missing worker_result.json; container rc={rc}"
            result["returncode"] = rc if rc != 0 else 1
        results.append(result)

    success_count = sum(1 for result in results if int(result.get("returncode", 1)) == 0 and result.get("container_returncode") == 0)
    max_cpu_pct = None
    max_mem_mib = None
    for sample in stats_samples:
        total_cpu = 0.0
        total_mem = 0.0
        saw_cpu = False
        saw_mem = False
        for item in sample.get("containers", {}).values():
            if isinstance(item.get("cpu_pct"), (int, float)):
                total_cpu += float(item["cpu_pct"])
                saw_cpu = True
            if isinstance(item.get("mem_mib"), (int, float)):
                total_mem += float(item["mem_mib"])
                saw_mem = True
        if saw_cpu:
            max_cpu_pct = total_cpu if max_cpu_pct is None else max(max_cpu_pct, total_cpu)
        if saw_mem:
            max_mem_mib = total_mem if max_mem_mib is None else max(max_mem_mib, total_mem)

    record = {
        "label": label,
        "n": n,
        "sim_speed_factor": sim_speed_factor,
        "cpuset_groups": cpuset_groups[:n],
        "elapsed_wall_s": elapsed,
        "success_count": success_count,
        "failure_count": n - success_count,
        "evals_per_hour_success": (success_count / elapsed * 3600.0) if elapsed > 0 else 0.0,
        "evals_per_hour_attempted": (n / elapsed * 3600.0) if elapsed > 0 else 0.0,
        "max_docker_cpu_pct_sum": max_cpu_pct,
        "max_docker_mem_mib_sum": max_mem_mib,
        "results": results,
    }
    write_json(batch_dir / "batch_summary.json", record)
    append_jsonl(run_dir / "batches.jsonl", {key: value for key, value in record.items() if key != "results"})
    print(
        json.dumps(
            {
                "batch_done": label,
                "n": n,
                "speed": sim_speed_factor,
                "elapsed_wall_s": round(elapsed, 2),
                "success": success_count,
                "failures": n - success_count,
                "evals_per_hour": round(record["evals_per_hour_success"], 3),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return record


def result_vector(result: dict[str, Any]) -> dict[str, float]:
    vector: dict[str, float] = {}
    for controller in ["classical", "mcnn"]:
        rho = result.get("rho", {}).get(controller, {})
        if isinstance(rho, dict):
            for prop in RHO_PROPERTIES:
                value = rho.get(prop)
                if isinstance(value, (int, float)) and math.isfinite(float(value)):
                    vector[f"{controller}.rho.{prop}"] = float(value)
        metrics = result.get("metrics", {}).get(controller, {})
        if isinstance(metrics, dict):
            for key in METRIC_KEYS:
                value = metrics.get(key)
                if isinstance(value, (int, float)) and math.isfinite(float(value)):
                    vector[f"{controller}.metric.{key}"] = float(value)
    return vector


def median_vector(results: list[dict[str, Any]]) -> dict[str, float]:
    vectors = [result_vector(result) for result in results if int(result.get("returncode", 1)) == 0]
    keys = sorted(set().union(*(vector.keys() for vector in vectors))) if vectors else []
    center: dict[str, float] = {}
    for key in keys:
        values = [vector[key] for vector in vectors if key in vector]
        if values:
            center[key] = float(median(values))
    return center


def max_pairwise_delta(results: list[dict[str, Any]]) -> dict[str, float]:
    vectors = [result_vector(result) for result in results if int(result.get("returncode", 1)) == 0]
    keys = sorted(set().union(*(vector.keys() for vector in vectors))) if vectors else []
    deltas: dict[str, float] = {}
    for key in keys:
        values = [vector[key] for vector in vectors if key in vector]
        if values:
            deltas[key] = max(values) - min(values)
    return deltas


def max_delta_from_center(results: list[dict[str, Any]], center: dict[str, float]) -> dict[str, float]:
    deltas: dict[str, float] = {}
    for result in results:
        if int(result.get("returncode", 1)) != 0:
            continue
        vector = result_vector(result)
        for key, expected in center.items():
            if key in vector:
                deltas[key] = max(deltas.get(key, 0.0), abs(vector[key] - expected))
    return deltas


def crosstalk_summary(serial_results: list[dict[str, Any]], parallel_results: list[dict[str, Any]]) -> dict[str, Any]:
    center = median_vector(serial_results)
    serial_delta = max_pairwise_delta(serial_results)
    parallel_delta = max_delta_from_center(parallel_results, center)
    keys = sorted(set(serial_delta) | set(parallel_delta))
    rows = []
    suspicious = []
    for key in keys:
        baseline = float(serial_delta.get(key, 0.0))
        observed = float(parallel_delta.get(key, 0.0))
        tolerance = max(1e-6, baseline * 3.0, abs(center.get(key, 0.0)) * 0.02)
        row = {
            "metric": key,
            "serial_pairwise_range": baseline,
            "parallel_delta_from_serial_median": observed,
            "tolerance": tolerance,
            "ratio_to_serial_range": None if baseline <= 0.0 else observed / baseline,
        }
        if observed > tolerance:
            suspicious.append(row)
        rows.append(row)
    failures = [result for result in parallel_results if int(result.get("returncode", 1)) != 0]
    status = "clean" if not failures and not suspicious else "crosstalk_or_resource_failure"
    return {
        "status": status,
        "serial_successes": sum(1 for result in serial_results if int(result.get("returncode", 1)) == 0),
        "parallel_successes": sum(1 for result in parallel_results if int(result.get("returncode", 1)) == 0),
        "parallel_failures": len(failures),
        "rows": rows,
        "suspicious_rows": suspicious,
    }


def orchestrator_main(args: argparse.Namespace) -> int:
    run_id = args.run_id or f"parallel_profile_{DEFAULT_DATE}_{datetime.now().strftime('%H%M%S')}"
    run_dir = (args.out_dir or (REPO_ROOT / "docs" / f"{run_id}_runs")).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "theta_seed": args.theta_seed,
        "run_timeout_s": args.run_timeout,
        "mission_end_s": args.mission_end_s,
        "levels": parse_csv_ints(args.levels),
        "speed_factors": parse_csv_floats(args.speed_factors),
        "cpuset_groups": parse_cpuset_groups(args.cpuset_groups),
        "container_entry": "sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=<name> ./docker/run.sh bash -lc ...'",
        "isolation": {
            "container_name": "unique per worker",
            "ros_domain_id": "unique per worker",
            "agent_port": "unique per worker and also exported as PX4_UXRCE_DDS_PORT",
            "tmpdir": "unique per worker",
            "px4_run_root": "unique per controller under worker px4_roots",
        },
    }
    write_json(run_dir / "metadata.json", metadata)

    all_batches: list[dict[str, Any]] = []
    serial_results: list[dict[str, Any]] = []
    for repeat in range(args.serial_repeats):
        batch = run_batch(
            run_dir=run_dir,
            run_id=run_id,
            label=f"serial_r{repeat:02d}",
            n=1,
            sim_speed_factor=1.0,
            args=args,
            domain_base=args.ros_domain_base,
            port_base=args.agent_port_base,
        )
        all_batches.append(batch)
        serial_results.extend(batch["results"])
        if batch["failure_count"]:
            write_json(run_dir / "summary.json", {"metadata": metadata, "batches": all_batches, "error": "serial baseline failed"})
            return 2

    crosstalk_batch = run_batch(
        run_dir=run_dir,
        run_id=run_id,
        label=f"crosstalk_n{args.crosstalk_n}",
        n=args.crosstalk_n,
        sim_speed_factor=1.0,
        args=args,
        domain_base=args.ros_domain_base,
        port_base=args.agent_port_base,
    )
    all_batches.append(crosstalk_batch)
    crosstalk = crosstalk_summary(serial_results, crosstalk_batch["results"])
    write_json(run_dir / "crosstalk_summary.json", crosstalk)
    if crosstalk["status"] != "clean":
        write_json(run_dir / "summary.json", {"metadata": metadata, "batches": all_batches, "crosstalk": crosstalk})
        return 3

    throughput_batches: list[dict[str, Any]] = []
    for offset, n in enumerate(parse_csv_ints(args.levels)):
        batch = run_batch(
            run_dir=run_dir,
            run_id=run_id,
            label=f"throughput_n{n}",
            n=n,
            sim_speed_factor=1.0,
            args=args,
            domain_base=args.ros_domain_base,
            port_base=args.agent_port_base,
        )
        all_batches.append(batch)
        throughput_batches.append(batch)
        if batch["failure_count"]:
            break

    speed_batches: list[dict[str, Any]] = []
    for offset, speed in enumerate(parse_csv_floats(args.speed_factors)):
        if abs(speed - 1.0) < 1e-9:
            continue
        batch = run_batch(
            run_dir=run_dir,
            run_id=run_id,
            label=f"speed_{str(speed).replace('.', 'p')}",
            n=1,
            sim_speed_factor=speed,
            args=args,
            domain_base=args.ros_domain_base,
            port_base=args.agent_port_base,
        )
        all_batches.append(batch)
        speed_batches.append(batch)
        if batch["failure_count"]:
            break

    clean_throughput = [batch for batch in throughput_batches if batch["failure_count"] == 0]
    recommended = max(clean_throughput, key=lambda batch: batch["evals_per_hour_success"]) if clean_throughput else None
    stable_speed_factors = [1.0] + [
        batch["sim_speed_factor"] for batch in speed_batches if batch["failure_count"] == 0
    ]
    summary = {
        "metadata": metadata,
        "crosstalk": crosstalk,
        "throughput": [
            {key: value for key, value in batch.items() if key != "results"} for batch in throughput_batches
        ],
        "speed_probe": [
            {key: value for key, value in batch.items() if key != "results"} for batch in speed_batches
        ],
        "recommended_parallelism": recommended["n"] if recommended else None,
        "recommended_evals_per_hour": recommended["evals_per_hour_success"] if recommended else None,
        "stable_speed_factor_upper_observed": max(stable_speed_factors),
        "batches": [{key: value for key, value in batch.items() if key != "results"} for batch in all_batches],
    }
    write_json(run_dir / "summary.json", summary)
    print(json.dumps({"run_dir": str(run_dir), "summary": str(run_dir / "summary.json")}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--run-id")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--levels", default="1,2,4,8,12")
    parser.add_argument("--speed-factors", default="1,2,3")
    parser.add_argument("--serial-repeats", type=int, default=3)
    parser.add_argument("--crosstalk-n", type=int, default=4)
    parser.add_argument("--theta-seed", type=int, default=20260628)
    parser.add_argument("--run-timeout", type=int, default=130)
    parser.add_argument("--mission-end-s", type=float, default=54.0)
    parser.add_argument("--target-properties", default="behavior")
    parser.add_argument("--stats-interval-s", type=float, default=8.0)
    parser.add_argument("--ros-domain-base", type=int, default=30)
    parser.add_argument("--agent-port-base", type=int, default=18888)
    parser.add_argument(
        "--cpuset-groups",
        default="",
        help="Optional semicolon-separated Docker cpuset-cpus groups, one per worker slot.",
    )

    parser.add_argument("--tag", help=argparse.SUPPRESS)
    parser.add_argument("--worker-label", default="worker", help=argparse.SUPPRESS)
    parser.add_argument("--docs-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--theta-path", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--result-json", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--sim-speed-factor", type=float, default=1.0, help=argparse.SUPPRESS)
    parser.add_argument("--thresholds-json", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.worker:
        missing = [
            name
            for name in ["tag", "docs_dir", "theta_path", "result_json"]
            if getattr(args, name) is None
        ]
        if missing:
            raise SystemExit(f"worker mode missing required args: {', '.join(missing)}")
        return worker_main(args)
    return orchestrator_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
