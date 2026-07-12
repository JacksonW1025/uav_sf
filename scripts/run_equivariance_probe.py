#!/usr/bin/env python3
"""Yaw-equivariance metamorphic probe driver.

Phase P uses `--stage0-preflight` only. The default execution path is the
Phase 1 floor-gated probe and should be run only after an explicit GO.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
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
from equivariance_transform import (  # noqa: E402
    apply_yaw_rotation,
    body_frame_maneuver_signature,
    circle_bearing_rad,
    wind_bearing_rad,
    wind_speed_m_s,
    yaw_rad,
    zero_wind,
)
from property_oracle import evaluate_ulog, load_thresholds  # noqa: E402
from validity_automation import decontamination_gate, reproduction_margins  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[1]
ANCHOR_RUN = REPO_ROOT / "runs/campaigns/raptor_gate0_anchor_recheck_20260705"
DENSE_RUN = REPO_ROOT / "runs/campaigns/raptor_switch_severity_dense_sweep_20260705"
PSI_VALUES_RAD = (0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0)
STAGE0_SEED = 2026070800
FLOOR_SEEDS = (2026070801,)
MCNN_SEEDS = (2026070801, 2026070802)
ATTITUDE_VALUES = (42.0, 45.0, 48.0)
HARD_ATTITUDE_VALUE = 50.0
CONTROLLED = {0, 1, 2}
UNCONTROLLED = {3, 4}


@dataclass(frozen=True)
class ThetaPoint:
    theta_id: str
    kind: str
    base_theta: dict[str, Any]
    source_artifact: str
    source_theta_path: str | None
    plan_metadata: dict[str, Any]


@dataclass(frozen=True)
class PlannedEval:
    index: int
    stage: str
    point: ThetaPoint
    psi_rad: float
    seed: int
    controller: str
    sut: str
    tag: str
    wind_zero: bool = False

    @property
    def theta_id(self) -> str:
        return self.point.theta_id

    @property
    def psi_deg(self) -> int:
        return int(round(math.degrees(self.psi_rad))) % 360


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
        handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")


def format_value(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".").replace("-", "m").replace(".", "p")


def psi_id(psi_rad: float) -> str:
    return f"yaw{int(round(math.degrees(psi_rad))) % 360:03d}"


def angle_delta_deg(a: float, b: float) -> float:
    return math.degrees(math.atan2(math.sin(a - b), math.cos(a - b)))


def theta_summary(theta: dict[str, Any]) -> dict[str, Any]:
    setpoint = theta.get("setpoint", {})
    circle = setpoint.get("circle", {}) if isinstance(setpoint, dict) else {}
    trigger = setpoint.get("activation_trigger", {}) if isinstance(setpoint, dict) else {}
    genome = theta.get("theta_genome", {}).get("genome", {}) if isinstance(theta.get("theta_genome"), dict) else {}
    env = theta.get("environment", {})
    case = env.get("case", {}) if isinstance(env, dict) else {}
    return {
        "yaw_rad": yaw_rad(theta),
        "yaw_deg": math.degrees(yaw_rad(theta)),
        "circle_phase_rad": float(circle.get("phase_rad", genome.get("approach_phase_rad", case.get("phase_rad", 0.0)))),
        "circle_bearing_rad": circle_bearing_rad(theta),
        "circle_bearing_deg": math.degrees(circle_bearing_rad(theta)),
        "circle_radius_m": circle.get("radius_m", genome.get("approach_radius_m", case.get("radius_m"))),
        "circle_frequency_hz": circle.get("frequency_hz", genome.get("approach_frequency_hz", case.get("frequency_hz"))),
        "wind_speed_m_s": wind_speed_m_s(theta),
        "wind_bearing_rad": wind_bearing_rad(theta),
        "wind_bearing_deg": math.degrees(wind_bearing_rad(theta)),
        "attitude_min_deg": trigger.get("roll_pitch_abs_min_deg", case.get("roll_pitch_min_deg")),
        "attitude_max_deg": trigger.get("roll_pitch_abs_max_deg", case.get("roll_pitch_max_deg")),
        "rate_min_rad_s": trigger.get("angular_rate_norm_min_rad_s", case.get("rate_min_rad_s")),
        "rate_max_rad_s": trigger.get("angular_rate_norm_max_rad_s", case.get("rate_max_rad_s")),
        "switch_delay_s": trigger.get("switch_delay_s", genome.get("switch_delay_s", case.get("switch_delay_s"))),
        "expected_tilt_deg": env.get("expected_tilt_deg", env.get("switching", {}).get("expected_tilt_deg"))
        if isinstance(env, dict)
        else None,
    }


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


def anchor_point(anchor: str, *, anchor_run: Path = ANCHOR_RUN) -> ThetaPoint:
    plan = read_json(anchor_run / "anchor_plan.json")
    for item in plan.get("anchors", []):
        if str(item.get("anchor")) != anchor:
            continue
        theta_path = find_anchor_theta(anchor_run, anchor, str(item["case"]), int(item["seed"]))
        return ThetaPoint(
            theta_id=anchor,
            kind="route_a_anchor",
            base_theta=read_json(theta_path),
            source_artifact=str((anchor_run / "anchor_plan.json").relative_to(REPO_ROOT)),
            source_theta_path=str(theta_path.relative_to(REPO_ROOT)),
            plan_metadata={"anchor": anchor, "case": item["case"], "source_seed": int(item["seed"])},
        )
    raise RuntimeError(f"anchor_plan missing {anchor}")


def genome_for_attitude(value: float, base: dict[str, Any]) -> dict[str, Any]:
    genome = theta_genome.default_genome("switching")
    genome.update(
        {
            **m2.route_a_profile_for(float(value), float(base["requested_rate_rad_s"])),
            "approach_phase_rad": float(base.get("approach_phase_rad", 0.0)),
            "wind_direction_rad": 0.0,
            "wind_speed_m_s": float(base.get("wind_speed_m_s", 0.0)),
            "setpoint_rate_hz": 80.0,
            "switch_delay_s": float(base.get("switch_delay_s", 0.09)),
        }
    )
    return m2.project_genome_to_subspace(genome, "route-a-switching", random0())


def random0():
    import random

    return random.Random(0)


def attitude_point(value: float, *, dense_run: Path = DENSE_RUN, hard: bool = False) -> ThetaPoint:
    config = read_json(dense_run / "sweep_config.json")
    genome = genome_for_attitude(value, config["base"])
    point_id = f"{'hard_' if hard else ''}attitude_deg_{format_value(value)}"
    theta = theta_genome.theta_from_genome(genome, f"template_{point_id}", FLOOR_SEEDS[0])
    return ThetaPoint(
        theta_id=point_id,
        kind="hard_attitude_cell" if hard else "attitude_band",
        base_theta=theta,
        source_artifact=str((dense_run / "sweep_config.json").relative_to(REPO_ROOT)),
        source_theta_path=None,
        plan_metadata={"axis": "attitude_deg", "value": value, "base": config["base"]},
    )


def planned_theta_points() -> list[ThetaPoint]:
    return [
        *(attitude_point(value) for value in ATTITUDE_VALUES),
        anchor_point("pair2"),
        anchor_point("pair5"),
        attitude_point(HARD_ATTITUDE_VALUE, hard=True),
    ]


def stage0_plan(run_id: str = "equivariance_probe_stage0", *, sut: str = "mcnn") -> list[PlannedEval]:
    point = anchor_point("pair2")
    plan: list[PlannedEval] = []
    for psi in PSI_VALUES_RAD:
        plan.append(
            PlannedEval(
                index=len(plan),
                stage="stage0_preflight",
                point=point,
                psi_rad=psi,
                seed=STAGE0_SEED,
                controller="classical",
                sut=sut,
                tag=f"{run_id}_stage0_{point.theta_id}_{psi_id(psi)}_s{STAGE0_SEED}_classical",
            )
        )
    return plan


def phase1_plan(
    run_id: str = "equivariance_probe",
    *,
    points: list[ThetaPoint] | None = None,
    sut: str = "mcnn",
    wind_zero: bool = False,
) -> tuple[list[PlannedEval], list[PlannedEval]]:
    points = list(points or planned_theta_points())
    floor: list[PlannedEval] = []
    neural: list[PlannedEval] = []
    for point in points:
        for psi in PSI_VALUES_RAD:
            for seed in FLOOR_SEEDS:
                floor.append(
                    PlannedEval(
                        index=len(floor),
                        stage="phase1_floor_gate",
                        point=point,
                        psi_rad=psi,
                        seed=seed,
                        controller="classical",
                        sut=sut,
                        wind_zero=wind_zero,
                        tag=f"{run_id}_floor_{point.theta_id}_{psi_id(psi)}_s{seed}_classical",
                    )
                )
            for seed in MCNN_SEEDS:
                neural.append(
                    PlannedEval(
                        index=len(neural),
                        stage="phase1_mcnn_probe",
                        point=point,
                        psi_rad=psi,
                        seed=seed,
                        controller=m2.sut_config(sut).controller,
                        sut=sut,
                        wind_zero=wind_zero,
                        tag=f"{run_id}_mcnn_{point.theta_id}_{psi_id(psi)}_s{seed}_{m2.sut_config(sut).controller}",
                    )
                )
    return floor, neural


def theta_for_eval(item: PlannedEval) -> dict[str, Any]:
    theta = copy.deepcopy(item.point.base_theta)
    theta["tag"] = item.tag
    theta["seed"] = int(item.seed)
    if item.stage == "stage0_preflight":
        theta.setdefault("setpoint", {}).setdefault("diagnostic_probe", {})["relative_times_s"] = [
            0.0,
            0.25,
            0.5,
            1.0,
        ]
    if item.wind_zero:
        theta = zero_wind(theta)
    theta = apply_yaw_rotation(theta, item.psi_rad)
    theta.setdefault("yaw_equivariance_probe", {}).update(
        {
            "stage": item.stage,
            "theta_id": item.theta_id,
            "kind": item.point.kind,
            "psi_rad": item.psi_rad,
            "psi_deg": item.psi_deg,
            "controller": item.controller,
            "sut": item.sut,
            "wind_zero": item.wind_zero,
            "source_artifact": item.point.source_artifact,
            "source_theta_path": item.point.source_theta_path,
            "plan_metadata": item.point.plan_metadata,
        }
    )
    return theta


def eval_plan_record(item: PlannedEval) -> dict[str, Any]:
    theta = theta_for_eval(item)
    return {
        "index": item.index,
        "stage": item.stage,
        "theta_id": item.theta_id,
        "kind": item.point.kind,
        "psi_deg": item.psi_deg,
        "psi_rad": item.psi_rad,
        "seed": item.seed,
        "controller": item.controller,
        "sut": item.sut,
        "tag": item.tag,
        "wind_zero": item.wind_zero,
        "theta": theta_summary(theta),
        "body_frame_maneuver_signature": body_frame_maneuver_signature(theta),
        "source_artifact": item.point.source_artifact,
        "source_theta_path": item.point.source_theta_path,
    }


def list_plan(run_id: str, *, sut: str = "mcnn", wind_zero: bool = False) -> dict[str, Any]:
    points = planned_theta_points()
    floor, neural = phase1_plan(run_id, points=points, sut=sut, wind_zero=wind_zero)
    stage0 = stage0_plan(run_id, sut=sut)
    return {
        "run_id": run_id,
        "sut": sut,
        "stage0": {
            "eval_count": len(stage0),
            "theta_count": 1,
            "psi_deg": [int(round(math.degrees(psi))) for psi in PSI_VALUES_RAD],
            "evals": [eval_plan_record(item) for item in stage0],
        },
        "phase1": {
            "wind_zero": wind_zero,
            "theta_count": len(points),
            "theta_ids": [point.theta_id for point in points],
            "psi_deg": [int(round(math.degrees(psi))) for psi in PSI_VALUES_RAD],
            "floor_gate_eval_count": len(floor),
            "mcnn_eval_count": len(neural),
            "total_eval_count": len(floor) + len(neural),
            "floor_seeds": list(FLOOR_SEEDS),
            "mcnn_seeds": list(MCNN_SEEDS),
            "floor_evals": [eval_plan_record(item) for item in floor],
            "mcnn_evals": [eval_plan_record(item) for item in neural],
        },
    }


def validate_genome_if_present(theta: dict[str, Any]) -> list[str]:
    genome = theta.get("theta_genome", {}).get("genome") if isinstance(theta.get("theta_genome"), dict) else None
    if not isinstance(genome, dict):
        return []
    return theta_genome.validate_genome(genome)


def controller_validity(property_result: dict[str, Any], controller: str) -> dict[str, Any]:
    decontam = decontamination_gate(property_result.get("window", {}).get("decontamination", {}))
    identity = property_result.get("controller_identity", {}).get("identity_gate")
    if controller == "classical":
        identity = {"passed": True, "reasons": [], "classical_identity_gate": "not_required"}
    if not isinstance(identity, dict):
        identity = {"passed": False, "reasons": ["missing_identity_gate"]}
    return {
        "decontamination": {controller: decontam},
        "identity": {controller: identity},
        "rho_jitter_reproduction_margins": reproduction_margins(),
        "passed": bool(decontam.get("passed")) and bool(identity.get("passed")),
    }


def evaluate_single_controller(
    *,
    item: PlannedEval,
    theta: dict[str, Any],
    theta_path: Path,
    eval_dir: Path,
    env: dict[str, str],
    thresholds: dict[str, float],
    run_timeout_s: int,
    read_property: bool,
) -> dict[str, Any]:
    selected_sut = m2.sut_config(item.sut)
    write_json(theta_path, theta)
    eval_dir.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    output = m2.run_one_for_sut(
        selected_sut,
        theta_path,
        theta,
        item.controller,
        eval_dir,
        env,
        run_timeout_s,
        m2.SAFETY_CONFIG,
    )
    elapsed = time.monotonic() - start
    property_path = None
    validity_path = None
    severity = None
    severity_label = None
    property_result: dict[str, Any] | None = None
    validity: dict[str, Any] = {
        "passed": True,
        "stage0_property_oracle_skipped": not read_property,
    }
    if read_property:
        property_result = evaluate_ulog(
            output["ulog"],
            controller=item.controller,
            theta=theta,
            task=read_json(output["task"]),
            thresholds=thresholds,
        )
        if item.controller == "raptor":
            identity = property_result.setdefault("controller_identity", {})
            policy_path = output.get("policy_tar")
            identity["policy_tar_staged"] = bool(policy_path is not None and policy_path.exists())
            identity_gate = m2.raptor_identity_gate(identity)
            identity["identity_gate"] = identity_gate
            identity["raptor_confirmed"] = bool(identity_gate.get("passed"))
        validity = controller_validity(property_result, item.controller)
        property_path = eval_dir / f"{theta['tag']}_{item.controller}_property.json"
        validity_path = eval_dir / f"{theta['tag']}_validity.json"
        write_json(property_path, property_result)
        write_json(validity_path, validity)
        severity_payload = property_result.get("severity", {})
        severity = int(severity_payload["severity"])
        severity_label = severity_payload.get("label")

    return {
        "index": item.index,
        "stage": item.stage,
        "theta_id": item.theta_id,
        "kind": item.point.kind,
        "psi_deg": item.psi_deg,
        "psi_rad": item.psi_rad,
        "seed": item.seed,
        "controller": item.controller,
        "sut": item.sut,
        "tag": item.tag,
        "wind_zero": item.wind_zero,
        "returncode": 0 if validity.get("passed") else 2,
        "valid": bool(validity.get("passed")),
        "error": None if validity.get("passed") else "validity_gate_failed",
        "elapsed_wall_s": elapsed,
        "severity": severity,
        "severity_label": severity_label,
        "theta": theta_summary(theta),
        "body_frame_maneuver_signature": body_frame_maneuver_signature(theta),
        "genome_validation_errors": validate_genome_if_present(theta),
        "theta_path": str(theta_path),
        "evidence": {
            "ulog_path": str(output["ulog"]),
            "task_path": str(output["task"]),
            "metrics_path": str(output.get("metrics")) if output.get("metrics") is not None else None,
            "property_path": str(property_path) if property_path else None,
            "validity_path": str(validity_path) if validity_path else None,
            "validity": validity,
        },
    }


def _field(data: dict[str, Any], *names: str):
    for name in names:
        if name in data:
            return data[name]
    raise KeyError(names[0])


def logged_body_frame_signature(
    ulog_path: Path,
    task_path: Path,
    theta: dict[str, Any],
    *,
    sample_times_s: tuple[float, ...] = (0.0, 0.25, 0.5, 1.0),
) -> dict[str, Any]:
    task = read_json(task_path)
    probe_events = [
        event
        for event in task.get("events", [])
        if event.get("name") == "setpoint_probe" and isinstance(event.get("detail"), dict)
    ]
    if probe_events:
        hover = theta.get("setpoint", {}).get("hover_ned", [0.0, 0.0, 0.0])
        samples: list[dict[str, Any]] = []
        headings: list[float] = []
        for event in sorted(probe_events, key=lambda item: float(item["detail"].get("offset_s", 0.0))):
            detail = event["detail"]
            y = float(detail.get("yaw_rad", yaw_rad(theta)))
            headings.append(y)
            position = detail["position_ned"]
            velocity = detail["velocity_ned"]
            acceleration = detail["acceleration_ned"]
            vectors = []
            for vector, subtract_hover in [
                (position, True),
                (velocity, False),
                (acceleration, False),
            ]:
                north = float(vector[0]) - (float(hover[0]) if subtract_hover else 0.0)
                east = float(vector[1]) - (float(hover[1]) if subtract_hover else 0.0)
                vectors.append(
                    [
                        round(math.cos(y) * north + math.sin(y) * east, 9),
                        round(-math.sin(y) * north + math.cos(y) * east, 9),
                    ]
                )
            samples.append(
                {
                    "t_s": round(float(detail.get("offset_s", 0.0)), 6),
                    "pos_body_ne_m": vectors[0],
                    "vel_body_ne_m_s": vectors[1],
                    "acc_body_ne_m_s2": vectors[2],
                }
            )
        return {
            "logged_heading_rad": round(headings[0], 9),
            "logged_heading_deg": round(math.degrees(headings[0]) % 360.0, 6),
            "logged_body_circle_samples": samples,
            "body_wind_speed_m_s": round(wind_speed_m_s(theta), 9),
            "body_wind_bearing_rad": round((wind_bearing_rad(theta) - yaw_rad(theta)) % (2.0 * math.pi), 9)
            if wind_speed_m_s(theta) > 1e-12
            else None,
            "source": "m1_offboard_task.setpoint_probe",
        }

    import numpy as np
    from pyulog import ULog

    from m1_metrics import first_dataset

    origin_us = task.get("origin_us")
    trajectory_start_us = task.get("trajectory_start_us")
    if origin_us is None or trajectory_start_us is None:
        raise ValueError(f"task missing origin_us/trajectory_start_us: {task_path}")
    setpoint = first_dataset(ULog(str(ulog_path)), "trajectory_setpoint")
    if setpoint is None:
        raise ValueError(f"missing trajectory_setpoint in {ulog_path}")
    ts = setpoint.data["timestamp"].astype(np.int64)
    pos_n = _field(setpoint.data, "position[0]", "position_0", "position.0").astype(float)
    pos_e = _field(setpoint.data, "position[1]", "position_1", "position.1").astype(float)
    yaw_values = setpoint.data["yaw"].astype(float) if "yaw" in setpoint.data else np.full_like(pos_n, yaw_rad(theta))
    hover = theta.get("setpoint", {}).get("hover_ned", [0.0, 0.0, 0.0])
    samples: list[dict[str, Any]] = []
    headings: list[float] = []
    for t in sample_times_s:
        target = int((int(trajectory_start_us) - int(origin_us)) + round(float(t) * 1e6))
        idx = int(np.argmin(np.abs(ts - target)))
        y = float(yaw_values[idx])
        headings.append(y)
        north = float(pos_n[idx]) - float(hover[0])
        east = float(pos_e[idx]) - float(hover[1])
        body_n = math.cos(y) * north + math.sin(y) * east
        body_e = -math.sin(y) * north + math.cos(y) * east
        samples.append(
            {
                "t_s": round(float(t), 6),
                "pos_body_ne_m": [round(body_n, 4), round(body_e, 4)],
            }
        )
    return {
        "logged_heading_rad": round(headings[0], 9),
        "logged_heading_deg": round(math.degrees(headings[0]) % 360.0, 6),
        "logged_body_circle_samples": samples,
        "body_wind_speed_m_s": round(wind_speed_m_s(theta), 9),
        "body_wind_bearing_rad": round((wind_bearing_rad(theta) - yaw_rad(theta)) % (2.0 * math.pi), 9)
        if wind_speed_m_s(theta) > 1e-12
        else None,
    }


def signatures_match(signatures: list[dict[str, Any]], key: str) -> bool:
    if not signatures:
        return False
    first = signatures[0].get(key)
    return all(item.get(key) == first for item in signatures)


def summarize_stage0(records: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [record for record in records if record.get("valid")]
    headings = [record.get("logged_signature", {}).get("logged_heading_deg") for record in valid]
    expected = sorted([record["psi_deg"] for record in valid])
    observed_delta = []
    if valid:
        base_heading = float(valid[0].get("logged_signature", {}).get("logged_heading_rad", valid[0]["theta"]["yaw_rad"]))
        for record in valid:
            heading = float(record.get("logged_signature", {}).get("logged_heading_rad", record["theta"]["yaw_rad"]))
            observed_delta.append(round(angle_delta_deg(heading, base_heading) % 360.0, 6))
    logged = [record.get("logged_signature", {}) for record in valid]
    commanded = [record.get("body_frame_maneuver_signature", {}) for record in valid]
    heading_ok = sorted(int(round(delta)) % 360 for delta in observed_delta) == expected
    return {
        "stage": "stage0_preflight",
        "total_evals": len(records),
        "valid_evals": len(valid),
        "invalid_evals": len(records) - len(valid),
        "severity_read": False,
        "observed_heading_deg": headings,
        "observed_heading_delta_deg": observed_delta,
        "expected_heading_delta_deg": expected,
        "heading_ok": heading_ok,
        "commanded_body_maneuver_identical": signatures_match(commanded, "body_circle_samples")
        and signatures_match(commanded, "body_wind_bearing_rad")
        and signatures_match(commanded, "body_wind_speed_m_s"),
        "logged_body_maneuver_identical": signatures_match(logged, "logged_body_circle_samples")
        and signatures_match(logged, "body_wind_bearing_rad")
        and signatures_match(logged, "body_wind_speed_m_s"),
        "passed": bool(valid)
        and len(valid) == len(records)
        and heading_ok
        and signatures_match(commanded, "body_circle_samples")
        and signatures_match(commanded, "body_wind_bearing_rad")
        and signatures_match(commanded, "body_wind_speed_m_s")
        and signatures_match(logged, "logged_body_circle_samples")
        and signatures_match(logged, "body_wind_bearing_rad")
        and signatures_match(logged, "body_wind_speed_m_s"),
        "records": records,
    }


def run_stage0(args: argparse.Namespace) -> int:
    run_dir = REPO_ROOT / "runs/campaigns" / args.run_id
    theta_dir = run_dir / "theta"
    evals_dir = run_dir / "evals"
    results_path = run_dir / "stage0_results.jsonl"
    plan = stage0_plan(args.run_id, sut=args.sut)
    records = [] if args.no_resume else read_jsonl(results_path)
    if args.no_resume and results_path.exists():
        results_path.unlink()
    seen = {record.get("tag") for record in records}
    env = m2.os_environ_with_speed(args.sim_speed_factor)
    thresholds = load_thresholds(args.thresholds_json)
    write_json(
        run_dir / "equivariance_probe_config.json",
        {
            "run_id": args.run_id,
            "mode": "stage0_preflight",
            "sut": args.sut,
            "sim_speed_factor": args.sim_speed_factor,
            "run_timeout_s": args.run_timeout,
            "severity_read": False,
            "phase1_not_run": True,
        },
    )
    completed = 0
    for item in plan:
        if item.tag in seen:
            continue
        if args.max_evals is not None and completed >= args.max_evals:
            break
        theta = theta_for_eval(item)
        theta_path = theta_dir / f"{item.tag}.json"
        eval_dir = evals_dir / item.tag
        try:
            record = evaluate_single_controller(
                item=item,
                theta=theta,
                theta_path=theta_path,
                eval_dir=eval_dir,
                env=env,
                thresholds=thresholds,
                run_timeout_s=args.run_timeout,
                read_property=False,
            )
            record["logged_signature"] = logged_body_frame_signature(
                Path(record["evidence"]["ulog_path"]),
                Path(record["evidence"]["task_path"]),
                theta,
            )
        except Exception as exc:
            write_json(theta_path, theta)
            record = {
                "index": item.index,
                "stage": item.stage,
                "theta_id": item.theta_id,
                "psi_deg": item.psi_deg,
                "psi_rad": item.psi_rad,
                "seed": item.seed,
                "controller": item.controller,
                "sut": item.sut,
                "tag": item.tag,
                "returncode": 1,
                "valid": False,
                "error": f"{type(exc).__name__}: {exc}",
                "severity": None,
                "theta": theta_summary(theta),
                "body_frame_maneuver_signature": body_frame_maneuver_signature(theta),
                "theta_path": str(theta_path),
                "evidence": {},
            }
        append_jsonl(results_path, record)
        records.append(record)
        seen.add(item.tag)
        completed += 1
        summary = summarize_stage0(records)
        write_json(run_dir / "stage0_summary.json", summary)
        print(
            json.dumps(
                {
                    "stage": item.stage,
                    "theta_id": item.theta_id,
                    "psi_deg": item.psi_deg,
                    "valid": record.get("valid"),
                    "error": record.get("error"),
                    "severity_read": False,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    summary = summarize_stage0(records)
    write_json(run_dir / "stage0_summary.json", summary)
    print("STAGE0_COMPLETE", json.dumps({"passed": summary["passed"], "severity_read": False}, sort_keys=True))
    return 0 if summary["passed"] else 2


def floor_status(records: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [record for record in records if record.get("valid") and record.get("severity") is not None]
    severities = [int(record["severity"]) for record in valid]
    counts = dict(Counter(str(value) for value in severities))
    clean = len(valid) == len(PSI_VALUES_RAD) * len(FLOOR_SEEDS) and len(set(severities)) == 1
    return {
        "valid_evals": len(valid),
        "planned_evals": len(PSI_VALUES_RAD) * len(FLOOR_SEEDS),
        "severity_counts": counts,
        "clean_floor": clean,
        "stable_severity": severities[0] if clean and severities else None,
    }


def classify_theta(classical_status: dict[str, Any], neural_records: list[dict[str, Any]]) -> str:
    if not classical_status.get("clean_floor"):
        return "C"
    valid = [record for record in neural_records if record.get("valid") and record.get("severity") is not None]
    severities = [int(record["severity"]) for record in valid]
    if not severities:
        return "invalid"
    has_controlled = any(value in CONTROLLED for value in severities)
    has_uncontrolled = any(value in UNCONTROLLED for value in severities)
    if has_controlled and has_uncontrolled:
        return "A"
    if max(severities) - min(severities) >= 1:
        return "A-minus"
    return "B"


def summarize_phase1(run_id: str, records: list[dict[str, Any]], points: list[ThetaPoint]) -> dict[str, Any]:
    by_theta_stage: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_theta_stage[(record["theta_id"], record["stage"])].append(record)
    point_summaries: list[dict[str, Any]] = []
    for point in points:
        floor = by_theta_stage[(point.theta_id, "phase1_floor_gate")]
        neural = by_theta_stage[(point.theta_id, "phase1_mcnn_probe")]
        cstatus = floor_status(floor)
        point_summaries.append(
            {
                "theta_id": point.theta_id,
                "kind": point.kind,
                "classical_floor": cstatus,
                "neural_valid_evals": sum(1 for record in neural if record.get("valid")),
                "neural_severity_counts": dict(
                    Counter(str(record.get("severity")) for record in neural if record.get("severity") is not None)
                ),
                "outcome": classify_theta(cstatus, neural),
                "source_artifact": point.source_artifact,
                "source_theta_path": point.source_theta_path,
            }
        )
    return {
        "run_id": run_id,
        "stage": "phase1",
        "total_records": len(records),
        "valid_records": sum(1 for record in records if record.get("valid")),
        "points": point_summaries,
        "outcome_counts": dict(Counter(item["outcome"] for item in point_summaries)),
    }


def run_phase1(args: argparse.Namespace) -> int:
    selected_sut = m2.sut_config(args.sut)
    if selected_sut.controller != "mcnn":
        raise SystemExit("Phase 1 first-round probe is locked to mc_nn; use --sut mcnn")
    run_dir = REPO_ROOT / "runs/campaigns" / args.run_id
    theta_dir = run_dir / "theta"
    evals_dir = run_dir / "evals"
    results_path = run_dir / "equivariance_results.jsonl"
    points = planned_theta_points()
    floor_plan, neural_plan = phase1_plan(args.run_id, points=points, sut=args.sut, wind_zero=args.wind_zero)
    records = [] if args.no_resume else read_jsonl(results_path)
    if args.no_resume and results_path.exists():
        results_path.unlink()
    seen = {record.get("tag") for record in records}
    env = m2.os_environ_with_speed(args.sim_speed_factor)
    thresholds = load_thresholds(args.thresholds_json)
    write_json(
        run_dir / "equivariance_probe_config.json",
        {
            "run_id": args.run_id,
            "mode": "phase1",
            "sut": args.sut,
            "wind_zero": args.wind_zero,
            "sim_speed_factor": args.sim_speed_factor,
            "run_timeout_s": args.run_timeout,
            "stage0_required_before_interpretation": True,
            "floor_gate_policy": "read mc_nn only for theta with classical severity invariant across psi",
        },
    )
    completed = 0

    def run_item(item: PlannedEval) -> dict[str, Any]:
        theta = theta_for_eval(item)
        theta_path = theta_dir / f"{item.tag}.json"
        eval_dir = evals_dir / item.tag
        try:
            return evaluate_single_controller(
                item=item,
                theta=theta,
                theta_path=theta_path,
                eval_dir=eval_dir,
                env=env,
                thresholds=thresholds,
                run_timeout_s=args.run_timeout,
                read_property=True,
            )
        except Exception as exc:
            write_json(theta_path, theta)
            return {
                "index": item.index,
                "stage": item.stage,
                "theta_id": item.theta_id,
                "kind": item.point.kind,
                "psi_deg": item.psi_deg,
                "psi_rad": item.psi_rad,
                "seed": item.seed,
                "controller": item.controller,
                "sut": item.sut,
                "tag": item.tag,
                "wind_zero": item.wind_zero,
                "returncode": 1,
                "valid": False,
                "error": f"{type(exc).__name__}: {exc}",
                "severity": None,
                "theta": theta_summary(theta),
                "body_frame_maneuver_signature": body_frame_maneuver_signature(theta),
                "theta_path": str(theta_path),
                "evidence": {},
            }

    for item in floor_plan:
        if item.tag in seen:
            continue
        if args.max_evals is not None and completed >= args.max_evals:
            break
        record = run_item(item)
        append_jsonl(results_path, record)
        records.append(record)
        seen.add(item.tag)
        completed += 1
        write_json(run_dir / "summary.json", summarize_phase1(args.run_id, records, points))
        print(
            json.dumps(
                {
                    "stage": item.stage,
                    "theta_id": item.theta_id,
                    "psi_deg": item.psi_deg,
                    "valid": record.get("valid"),
                    "severity": record.get("severity"),
                    "error": record.get("error"),
                },
                sort_keys=True,
            ),
            flush=True,
        )

    floor_by_theta: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("stage") == "phase1_floor_gate":
            floor_by_theta[str(record["theta_id"])].append(record)
    clean_theta_ids = {
        theta_id for theta_id, items in floor_by_theta.items() if floor_status(items).get("clean_floor")
    }
    for item in neural_plan:
        if item.theta_id not in clean_theta_ids:
            continue
        if item.tag in seen:
            continue
        if args.max_evals is not None and completed >= args.max_evals:
            break
        record = run_item(item)
        append_jsonl(results_path, record)
        records.append(record)
        seen.add(item.tag)
        completed += 1
        write_json(run_dir / "summary.json", summarize_phase1(args.run_id, records, points))
        print(
            json.dumps(
                {
                    "stage": item.stage,
                    "theta_id": item.theta_id,
                    "psi_deg": item.psi_deg,
                    "seed": item.seed,
                    "valid": record.get("valid"),
                    "severity": record.get("severity"),
                    "error": record.get("error"),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    summary = summarize_phase1(args.run_id, records, points)
    write_json(run_dir / "summary.json", summary)
    print("PHASE1_COMPLETE", json.dumps({"outcome_counts": summary["outcome_counts"]}, sort_keys=True))
    return 0


def main() -> int:
    default_run_id = f"equivariance_probe_{datetime.now().strftime('%Y%m%d')}"
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=default_run_id)
    parser.add_argument("--sut", choices=m2.SUTS, default="mcnn")
    parser.add_argument("--sim-speed-factor", type=float, default=1.25)
    parser.add_argument("--run-timeout", type=int, default=230)
    parser.add_argument("--thresholds-json", type=Path)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--stage0-preflight", action="store_true")
    parser.add_argument("--wind-zero", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--max-evals", type=int, default=None)
    args = parser.parse_args()

    if args.list_only:
        print(json.dumps(list_plan(args.run_id, sut=args.sut, wind_zero=args.wind_zero), indent=2, sort_keys=True))
        return 0
    if args.stage0_preflight:
        return run_stage0(args)
    return run_phase1(args)


if __name__ == "__main__":
    raise SystemExit(main())
