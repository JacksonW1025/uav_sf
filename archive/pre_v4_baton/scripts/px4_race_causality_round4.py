#!/usr/bin/env python3
"""Round 4 actuator-race attribution and comparable-window statistics.

This script is intentionally read-only with respect to ULOGs and PX4 source.
It writes a JSON summary artifact so the report numbers can be reproduced.
"""

from __future__ import annotations

import itertools
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from pyulog import ULog


OUT_JSON = Path("docs/px4_race_causality_round4_analysis_20260709.json")
TOL = 1e-6


@dataclass(frozen=True)
class LogCase:
    label: str
    path: str
    kind: str
    outcome: str


LOGS = [
    LogCase(
        "mcnn_s3_pair1",
        "runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/evals/"
        "route_a_addendum3_diag_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_s20262001/"
        "mcnn_gate3_route_a_addendum3_diag_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_s20262001_mcnn.ulg",
        "mcnn",
        "flip",
    ),
    LogCase(
        "mcnn_s3_pair2",
        "runs/route_a_anchor_regression/route_a_anchor_regression_20260629/evals/"
        "route_a_anchor_regression_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_confirm1_s20261901/"
        "mcnn_gate3_route_a_anchor_regression_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_confirm1_s20261901_mcnn.ulg",
        "mcnn",
        "flip",
    ),
    LogCase(
        "mcnn_s3_pair4",
        "runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/evals/"
        "route_a_addendum3_diag_20260629_rp36_44_rate1p55_2p15_w3_r4_f038_s20261902/"
        "mcnn_gate3_route_a_addendum3_diag_20260629_rp36_44_rate1p55_2p15_w3_r4_f038_s20261902_mcnn.ulg",
        "mcnn",
        "flip",
    ),
    LogCase(
        "mcnn_s3_pair5",
        "runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/evals/"
        "route_a_addendum3_diag_20260629_rp32_40_rate1p30_1p95_w0_r4_f038_s20261903/"
        "mcnn_gate3_route_a_addendum3_diag_20260629_rp32_40_rate1p30_1p95_w0_r4_f038_s20261903_mcnn.ulg",
        "mcnn",
        "flip",
    ),
    LogCase(
        "mcnn_safe_validity_e0000",
        "docs/validity_automation_real_20260627/evals/validity_automation_real_20260627_e0000/"
        "mcnn_gate3_validity_automation_real_20260627_e0000_mcnn.ulg",
        "mcnn",
        "safe",
    ),
    LogCase(
        "mcnn_safe_validity_e0001",
        "docs/validity_automation_real_20260627/evals/validity_automation_real_20260627_e0001/"
        "mcnn_gate3_validity_automation_real_20260627_e0001_mcnn.ulg",
        "mcnn",
        "safe",
    ),
    LogCase(
        "mcnn_safe_baseline_s20261302",
        "docs/mcnn_gonogo_gate3_20260625/evals/mcnn_gonogo_gate3_20260625_baseline_s20261302/"
        "mcnn_gate3_mcnn_gonogo_gate3_20260625_baseline_s20261302_mcnn.ulg",
        "mcnn",
        "safe",
    ),
    LogCase(
        "raptor_pair4_s20262302",
        "runs/campaigns/raptor_gate0_anchor_boundary_20260705/evals/"
        "raptor_gate0_anchor_boundary_20260705_pair4_rp36_44_rate1p55_2p15_w3_r4_f038_s20262302/"
        "m1_raptor_gate0_anchor_boundary_20260705_pair4_rp36_44_rate1p55_2p15_w3_r4_f038_s20262302_raptor.ulg",
        "raptor",
        "safe",
    ),
    LogCase(
        "raptor_pair5_s20262003",
        "runs/campaigns/raptor_gate0_anchor_boundary_20260705/evals/"
        "raptor_gate0_anchor_boundary_20260705_pair5_rp32_40_rate1p30_1p95_w0_r4_f038_s20262003/"
        "m1_raptor_gate0_anchor_boundary_20260705_pair5_rp32_40_rate1p30_1p95_w0_r4_f038_s20262003_raptor.ulg",
        "raptor",
        "safe",
    ),
]


def as_py(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(k): as_py(v) for k, v in value.items()}
    if isinstance(value, list):
        return [as_py(v) for v in value]
    return value


def counts(classes: np.ndarray, mask: np.ndarray | None = None) -> dict[str, int]:
    selected = classes if mask is None else classes[mask]
    return {str(key): int(np.sum(selected == key)) for key in sorted(set(selected))}


def frac(count: int, total: int) -> float:
    return float(count / total) if total else float("nan")


def count_frac(classes: np.ndarray, target: str, mask: np.ndarray | None = None) -> dict[str, Any]:
    selected = classes if mask is None else classes[mask]
    n = int(len(selected))
    c = int(np.sum(selected == target))
    return {"count": c, "total": n, "fraction": frac(c, n)}


def first_nav23(vehicle_status: dict[str, np.ndarray]) -> tuple[int, int] | None:
    timestamps = vehicle_status["timestamp"].astype(np.int64)
    nav_state = vehicle_status["nav_state"]
    indexes = np.where(nav_state == 23)[0]

    if len(indexes) == 0:
        return None

    start_index = indexes[0]
    end_index = start_index

    while end_index + 1 < len(nav_state) and nav_state[end_index + 1] == 23:
        end_index += 1

    return int(timestamps[start_index]), int(timestamps[end_index])


def quat_tilt_deg(q: np.ndarray) -> float:
    w, x, y, z = q
    r22 = 1.0 - 2.0 * (x * x + y * y)
    r20 = 2.0 * (x * z - w * y)
    r21 = 2.0 * (y * z + w * x)
    return math.degrees(math.atan2(math.sqrt(r20 * r20 + r21 * r21), r22))


def loss_time(data: dict[tuple[str, int], dict[str, np.ndarray]], start: int, end: int) -> tuple[str, int]:
    candidates: list[tuple[str, int]] = []

    angular_velocity = data.get(("vehicle_angular_velocity", 0))
    if angular_velocity is not None:
        timestamps = angular_velocity["timestamp"].astype(np.int64)
        mask = (timestamps >= start) & (timestamps <= end)

        if np.any(mask):
            rate_norm = np.sqrt(
                angular_velocity["xyz[0]"][mask] ** 2
                + angular_velocity["xyz[1]"][mask] ** 2
                + angular_velocity["xyz[2]"][mask] ** 2
            )
            hits = np.where(rate_norm > 8.0)[0]

            if len(hits):
                candidates.append(("rate>8", int(timestamps[mask][hits[0]])))

    attitude = data.get(("vehicle_attitude", 0))
    if attitude is not None:
        timestamps = attitude["timestamp"].astype(np.int64)
        mask = (timestamps >= start) & (timestamps <= end)

        if np.any(mask):
            quaternions = np.vstack([attitude[f"q[{i}]"][mask] for i in range(4)]).T
            tilt = np.array([quat_tilt_deg(q) for q in quaternions])
            hits = np.where(tilt > 90.0)[0]

            if len(hits):
                candidates.append(("tilt>90", int(timestamps[mask][hits[0]])))

    if not candidates:
        return "none", end

    return min(candidates, key=lambda item: item[1])


def actuator_matrix(actuator: dict[str, np.ndarray], mask: np.ndarray) -> np.ndarray:
    return np.vstack([actuator[f"control[{i}]"][mask] for i in range(4)]).T.astype(np.float32)


def classify_mcnn_by_value(
    data: dict[tuple[str, int], dict[str, np.ndarray]], start: int, end: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, int]]:
    actuator = data[("actuator_motors", 0)]
    mask = (actuator["timestamp"] >= start) & (actuator["timestamp"] <= end)
    timestamps = actuator["timestamp"][mask].astype(np.int64)
    timestamp_sample = actuator["timestamp_sample"][mask].astype(np.int64)
    controls = actuator_matrix(actuator, mask)

    classes = np.full(len(timestamps), "unknown", dtype=object)

    neural = data[("neural_control", 0)]
    neural_index = {int(t): i for i, t in enumerate(neural["timestamp"].astype(np.int64))}
    neural_output = np.vstack([neural[f"network_output[{i}]"] for i in range(4)]).T.astype(np.float32)

    has_neural_timestamp = np.zeros(len(timestamps), dtype=bool)

    for i, timestamp in enumerate(timestamps):
        neural_i = neural_index.get(int(timestamp))

        if neural_i is not None:
            has_neural_timestamp[i] = True

            if np.all(np.abs(controls[i] - neural_output[neural_i]) <= TOL):
                classes[i] = "neural_value"

    valid_allocator_sample = (
        (timestamp_sample >= 0)
        & (timestamp_sample <= end + 1_000_000)
        & (np.abs(timestamps - timestamp_sample) <= 100_000)
    )
    finite_clipped = np.all(np.isfinite(controls) & (controls >= -TOL) & (controls <= 1.0 + TOL), axis=1)
    classes[(classes != "neural_value") & valid_allocator_sample & finite_clipped] = "allocator_value_residual"

    selfcheck = {
        "actuator_samples": int(len(timestamps)),
        "with_simultaneous_neural_control_timestamp": int(np.sum(has_neural_timestamp)),
        "exact_neural_value_matches": int(np.sum(classes == "neural_value")),
        "simultaneous_neural_timestamp_nonmatches_with_allocator_signature": int(
            np.sum(has_neural_timestamp & (classes == "allocator_value_residual"))
        ),
        "all_allocator_signature_residuals": int(np.sum(classes == "allocator_value_residual")),
        "no_simultaneous_neural_timestamp_allocator_signature_residuals": int(
            np.sum((~has_neural_timestamp) & (classes == "allocator_value_residual"))
        ),
    }

    return timestamps, classes, controls, selfcheck


def shifted_raptor_controls_from_next_input(
    data: dict[tuple[str, int], dict[str, np.ndarray]], start: int, end: int, actuator_timestamps: np.ndarray
) -> np.ndarray:
    raptor_input = data[("raptor_input", 0)]
    mask = (raptor_input["timestamp"] >= start) & (raptor_input["timestamp"] <= end)

    if "active" in raptor_input:
        mask = mask & raptor_input["active"].astype(bool)

    input_timestamps = raptor_input["timestamp"][mask].astype(np.int64)
    previous_action = np.vstack([raptor_input[f"previous_action[{i}]"][mask] for i in range(4)]).T.astype(np.float32)
    scaled = (previous_action + np.float32(1.0)) / np.float32(2.0)
    # Raptor::REMAP_FROM_CRAZYFLIE is true in this PX4 tree:
    # [0, 1, 2, 3] -> [0, 2, 3, 1].
    remapped = scaled[:, [0, 2, 3, 1]]

    matched = np.full((len(actuator_timestamps), 4), np.nan, dtype=np.float32)
    next_indexes = np.searchsorted(input_timestamps, actuator_timestamps, side="right")

    for i, next_i in enumerate(next_indexes):
        if next_i < len(input_timestamps) and input_timestamps[next_i] - actuator_timestamps[i] <= 20_000:
            matched[i] = remapped[next_i]

    return matched


def classify_raptor_shift_proxy(
    data: dict[tuple[str, int], dict[str, np.ndarray]], start: int, end: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    actuator = data[("actuator_motors", 0)]
    mask = (actuator["timestamp"] >= start) & (actuator["timestamp"] <= end)
    timestamps = actuator["timestamp"][mask].astype(np.int64)
    controls = actuator_matrix(actuator, mask)
    shifted_controls = shifted_raptor_controls_from_next_input(data, start, end, timestamps)

    classes = np.full(len(timestamps), "unclassified_value", dtype=object)
    finite_shift = np.all(np.isfinite(shifted_controls), axis=1)
    matched = finite_shift & np.all(np.abs(controls - shifted_controls) <= TOL, axis=1)
    classes[matched] = "raptor_shifted_previous_action_value"
    return timestamps, classes, controls


def align_outputs(
    data: dict[tuple[str, int], dict[str, np.ndarray]],
    actuator_timestamps: np.ndarray,
    actuator_classes: np.ndarray,
    start: int,
    end: int,
) -> tuple[np.ndarray, np.ndarray]:
    actuator_outputs = data.get(("actuator_outputs", 0))

    if actuator_outputs is None:
        return np.array([], dtype=np.int64), np.array([], dtype=object)

    output_mask = (actuator_outputs["timestamp"] >= start) & (actuator_outputs["timestamp"] <= end)
    output_timestamps = actuator_outputs["timestamp"][output_mask].astype(np.int64)
    actuator_index = np.searchsorted(actuator_timestamps, output_timestamps, side="right") - 1
    aligned = (actuator_index >= 0) & ((output_timestamps - actuator_timestamps[actuator_index]) <= 20_000)
    return output_timestamps[aligned], actuator_classes[actuator_index[aligned]]


def setpoint_features_for_actuator_timestamps(
    data: dict[tuple[str, int], dict[str, np.ndarray]], actuator_timestamps: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    torque = data.get(("vehicle_torque_setpoint", 0))
    thrust = data.get(("vehicle_thrust_setpoint", 0))
    if torque is None or thrust is None or len(actuator_timestamps) == 0:
        return np.empty((0, 7), dtype=float), np.zeros(len(actuator_timestamps), dtype=bool)

    torque_ts = torque["timestamp"].astype(np.int64)
    thrust_ts = thrust["timestamp"].astype(np.int64)
    torque_values = np.vstack([torque[f"xyz[{i}]"] for i in range(3)]).T.astype(float)
    thrust_values = np.vstack([thrust[f"xyz[{i}]"] for i in range(3)]).T.astype(float)

    torque_i = np.searchsorted(torque_ts, actuator_timestamps, side="right") - 1
    thrust_i = np.searchsorted(thrust_ts, actuator_timestamps, side="right") - 1
    valid = (
        (torque_i >= 0)
        & (thrust_i >= 0)
        & ((actuator_timestamps - torque_ts[np.clip(torque_i, 0, len(torque_ts) - 1)]) <= 40_000)
        & ((actuator_timestamps - thrust_ts[np.clip(thrust_i, 0, len(thrust_ts) - 1)]) <= 40_000)
    )
    features = np.full((len(actuator_timestamps), 7), np.nan, dtype=float)
    if np.any(valid):
        features[valid, :3] = torque_values[torque_i[valid]]
        features[valid, 3:6] = thrust_values[thrust_i[valid]]
        features[valid, 6] = 1.0
    return features, valid


def allocator_setpoint_fingerprint(
    data: dict[tuple[str, int], dict[str, np.ndarray]],
    actuator_timestamps: np.ndarray,
    actuator_classes: np.ndarray,
    controls: np.ndarray,
) -> dict[str, Any]:
    features, valid_features = setpoint_features_for_actuator_timestamps(data, actuator_timestamps)
    if len(features) == 0:
        return {"available": False, "reason": "missing_setpoint_topics"}

    allocator_mask = (actuator_classes == "allocator_value_residual") & valid_features
    neural_mask = (actuator_classes == "neural_value") & valid_features
    allocator_indexes = np.where(allocator_mask)[0]
    if len(allocator_indexes) < 20:
        return {"available": False, "reason": "too_few_allocator_frames_with_setpoints", "allocator_count": int(len(allocator_indexes))}

    train = allocator_indexes[::2]
    test = allocator_indexes[1::2]
    coefficients, *_ = np.linalg.lstsq(features[train], controls[train].astype(float), rcond=None)
    predicted = features @ coefficients
    residual = np.sqrt(np.mean((predicted - controls.astype(float)) ** 2, axis=1))

    def residual_summary(mask: np.ndarray) -> dict[str, Any]:
        values = residual[mask]
        values = values[np.isfinite(values)]
        if len(values) == 0:
            return {"count": 0}
        return {
            "count": int(len(values)),
            "rmse_median": float(np.median(values)),
            "rmse_p90": float(np.percentile(values, 90)),
            "rmse_p99": float(np.percentile(values, 99)),
        }

    return {
        "available": True,
        "feature": "least-squares motor mix from [torque xyz, thrust xyz, intercept], trained on alternating allocator-tagged frames",
        "train_allocator_count": int(len(train)),
        "test_allocator_count": int(len(test)),
        "valid_neural_count": int(np.sum(neural_mask)),
        "allocator_test_residual": residual_summary(np.isin(np.arange(len(actuator_timestamps)), test)),
        "neural_residual": residual_summary(neural_mask),
    }


def ranks_average(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0

    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1

        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[order[k]] = avg_rank

        i = j

    return ranks


def mann_whitney_exact(x: list[float], y: list[float]) -> dict[str, float]:
    n1 = len(x)
    n2 = len(y)
    pooled = list(x) + list(y)
    ranks = ranks_average(pooled)
    rank_sum_x = sum(ranks[:n1])
    u_obs = rank_sum_x - n1 * (n1 + 1) / 2.0
    mean_u = n1 * n2 / 2.0
    obs_dist = abs(u_obs - mean_u)

    total = 0
    extreme = 0

    for combo in itertools.combinations(range(n1 + n2), n1):
        rank_sum = sum(ranks[i] for i in combo)
        u = rank_sum - n1 * (n1 + 1) / 2.0
        total += 1

        if abs(u - mean_u) >= obs_dist - 1e-12:
            extreme += 1

    return {"u": float(u_obs), "p_two_sided_exact": float(extreme / total)}


def analyze_case(log_case: LogCase) -> dict[str, Any]:
    if not os.path.exists(log_case.path):
        return {"label": log_case.label, "missing": True, "path": log_case.path}

    ulog = ULog(log_case.path)
    data = {(dataset.name, dataset.multi_id): dataset.data for dataset in ulog.data_list}
    interval = first_nav23(data[("vehicle_status", 0)])

    if interval is None:
        return {"label": log_case.label, "no_nav23": True, "path": log_case.path}

    start, end = interval
    loss_reason, first_loss = loss_time(data, start, end)

    mcnn_selfcheck = None

    if log_case.kind == "mcnn":
        actuator_timestamps, actuator_classes, controls_for_fingerprint, mcnn_selfcheck = classify_mcnn_by_value(data, start, end)
        setpoint_fingerprint = allocator_setpoint_fingerprint(
            data, actuator_timestamps, actuator_classes, controls_for_fingerprint
        )
        primary_class = "allocator_value_residual"
    else:
        actuator_timestamps, actuator_classes, _ = classify_raptor_shift_proxy(data, start, end)
        setpoint_fingerprint = None
        primary_class = "raptor_shifted_previous_action_value"

    output_timestamps, output_classes = align_outputs(data, actuator_timestamps, actuator_classes, start, end)

    windows: dict[str, dict[str, Any]] = {}
    for name, window_end in (
        ("critical_or_full", first_loss),
        ("fixed_0p5s", min(end, start + 500_000)),
        ("fixed_0p6s", min(end, start + 600_000)),
        ("full_nav23", end),
    ):
        output_mask = (output_timestamps >= start) & (output_timestamps <= window_end)
        actuator_mask = (actuator_timestamps >= start) & (actuator_timestamps <= window_end)
        windows[name] = {
            "duration_s": (window_end - start) / 1e6,
            "actuator_counts": counts(actuator_classes, actuator_mask),
            "output_counts": counts(output_classes, output_mask),
            "output_primary": count_frac(output_classes, primary_class, output_mask),
            "actuator_primary": count_frac(actuator_classes, primary_class, actuator_mask),
        }

    duplicate_counts = np.unique(actuator_timestamps, return_counts=True)[1]
    actuator_dt = np.diff(actuator_timestamps)

    return {
        "label": log_case.label,
        "path": log_case.path,
        "kind": log_case.kind,
        "outcome": log_case.outcome,
        "nav23_start_us": start,
        "nav23_end_us": end,
        "nav23_duration_s": (end - start) / 1e6,
        "loss_reason": loss_reason,
        "loss_dt_s": (first_loss - start) / 1e6,
        "actuator_total_counts": counts(actuator_classes),
        "output_total_counts": counts(output_classes),
        "mcnn_value_selfcheck": mcnn_selfcheck,
        "setpoint_fingerprint": setpoint_fingerprint,
        "actuator_rate_hz": len(actuator_timestamps) / ((end - start) / 1e6),
        "output_rate_hz": len(output_timestamps) / ((end - start) / 1e6),
        "duplicate_timestamp_extra": int(np.sum(duplicate_counts - 1)),
        "actuator_dt_us": {
            "min": int(np.min(actuator_dt)) if len(actuator_dt) else None,
            "p50": int(np.percentile(actuator_dt, 50)) if len(actuator_dt) else None,
            "p95": int(np.percentile(actuator_dt, 95)) if len(actuator_dt) else None,
            "p99": int(np.percentile(actuator_dt, 99)) if len(actuator_dt) else None,
            "max": int(np.max(actuator_dt)) if len(actuator_dt) else None,
        },
        "windows": windows,
    }


def p5_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    stats: dict[str, Any] = {}

    for window_name in ("fixed_0p5s", "fixed_0p6s", "critical_or_full", "full_nav23"):
        flips = [
            result["windows"][window_name]["output_primary"]["fraction"]
            for result in results
            if result.get("kind") == "mcnn" and result.get("outcome") == "flip"
        ]
        safes = [
            result["windows"][window_name]["output_primary"]["fraction"]
            for result in results
            if result.get("kind") == "mcnn" and result.get("outcome") == "safe"
        ]

        stats[window_name] = {
            "flip_fractions": flips,
            "safe_fractions": safes,
            "flip_median": float(np.median(flips)) if flips else None,
            "safe_median": float(np.median(safes)) if safes else None,
            "mann_whitney": mann_whitney_exact(flips, safes) if flips and safes else None,
        }

    return stats


def pct(value: float) -> str:
    if math.isnan(value):
        return "nan"
    return f"{100.0 * value:.2f}%"


def print_summary(summary: dict[str, Any]) -> None:
    print("P1/P5 Round 4 analysis")
    print(f"json_out={OUT_JSON}")
    print()
    print(
        "label,kind,outcome,loss_dt_s,actuator_counts,output_counts,"
        "critical_or_full_output_primary,fixed_0p5_output_primary,fixed_0p6_output_primary,full_output_primary"
    )

    for result in summary["logs"]:
        if result.get("missing") or result.get("no_nav23"):
            print(f"{result['label']},MISSING_OR_NO_NAV23")
            continue

        primary_fields = []
        for window_name in ("critical_or_full", "fixed_0p5s", "fixed_0p6s", "full_nav23"):
            primary = result["windows"][window_name]["output_primary"]
            primary_fields.append(f"{primary['count']}/{primary['total']}={pct(primary['fraction'])}")

        print(
            f"{result['label']},{result['kind']},{result['outcome']},{result['loss_dt_s']:.3f},"
            f"{result['actuator_total_counts']},{result['output_total_counts']},"
            f"{','.join(primary_fields)}"
        )

    print()
    print("P5 Mann-Whitney exact two-sided tests on mcnn downstream allocator fraction")
    print("window,flip_fractions,safe_fractions,U,p")

    for window_name, stats in summary["p5"].items():
        mw = stats["mann_whitney"]
        print(
            f"{window_name},"
            f"{[round(x, 6) for x in stats['flip_fractions']]},"
            f"{[round(x, 6) for x in stats['safe_fractions']]},"
            f"{mw['u'] if mw else None},"
            f"{mw['p_two_sided_exact'] if mw else None}"
        )


def main() -> int:
    results = [analyze_case(log_case) for log_case in LOGS]
    summary = {
        "method": {
            "mcnn": "exact actuator_motors.control[0..3] == same-timestamp neural_control.network_output[0..3]; residual valid timestamp_sample clipped frames are allocator_value_residual",
            "raptor": "current action is not logged; shifted proxy compares actuator_motors.control[0..3] to next active raptor_input.previous_action scaled from [-1,1] and Crazyflie-remapped",
            "downstream": "actuator_outputs samples inherit the class of the preceding actuator_motors sample within 20 ms",
            "mann_whitney": "exact enumeration over average ranks; two-sided by distance from U mean",
        },
        "logs": results,
        "p5": p5_stats(results),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(as_py(summary), indent=2, sort_keys=True) + "\n")
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
