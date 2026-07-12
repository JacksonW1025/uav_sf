#!/usr/bin/env python3
"""Round 5 setpoint-fingerprint writer attribution.

The script is intentionally read-only. It fits the classical allocator mapping
on pure classical ULOGs, validates the fixed mapping on held-out classical
logs, and then checks whether residual thresholding reproduces the mcnn
value-match labels before any RAPTOR use.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from pyulog import ULog


REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "docs" / "round5_delivered_state_20260709"
MCNN_SWEEP = REPO / "runs/campaigns/switch_severity_dense_sweep_20260630/sweep_results.jsonl"
RAPTOR_SWEEP = REPO / "runs/campaigns/raptor_switch_severity_dense_sweep_20260705/sweep_results.jsonl"
TOPICS = [
    "vehicle_status",
    "actuator_motors",
    "vehicle_torque_setpoint",
    "vehicle_thrust_setpoint",
    "neural_control",
    "raptor_input",
    "raptor_status",
    "actuator_outputs",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def qstats(values: np.ndarray) -> dict[str, float | int | None]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return {"n": 0, "min": None, "p05": None, "p25": None, "median": None, "p75": None, "p95": None, "max": None}
    return {
        "n": int(len(values)),
        "min": float(np.min(values)),
        "p05": float(np.percentile(values, 5)),
        "p25": float(np.percentile(values, 25)),
        "median": float(np.percentile(values, 50)),
        "p75": float(np.percentile(values, 75)),
        "p95": float(np.percentile(values, 95)),
        "max": float(np.max(values)),
    }


def load_ulog(path: str | Path) -> dict[str, dict[str, np.ndarray]]:
    ulog = ULog(str(path), TOPICS)
    return {dataset.name: dataset.data for dataset in ulog.data_list}


def status_mask(data: dict[str, dict[str, np.ndarray]], timestamps: np.ndarray, nav_states: set[int]) -> np.ndarray:
    status = data["vehicle_status"]
    status_ts = status["timestamp"].astype(np.int64)
    indexes = np.searchsorted(status_ts, timestamps, side="right") - 1
    mask = indexes >= 0
    out = np.zeros(len(timestamps), dtype=bool)
    out[mask] = np.isin(status["nav_state"][indexes[mask]], list(nav_states))
    return out


def aligned_allocator_rows(
    data: dict[str, dict[str, np.ndarray]],
    nav_states: set[int],
    max_age_us: int = 30_000,
    row_limit: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return actuator indexes, X=[tau, thrust, intercept], Y=motor controls."""

    actuator = data["actuator_motors"]
    actuator_ts = actuator["timestamp"].astype(np.int64)
    actuator_sample = actuator["timestamp_sample"].astype(np.int64)
    key_ts = actuator_sample.copy()
    invalid_sample = (key_ts < 0) | (key_ts > 1_000_000_000_000)
    key_ts[invalid_sample] = actuator_ts[invalid_sample]

    torque = data["vehicle_torque_setpoint"]
    thrust = data["vehicle_thrust_setpoint"]
    torque_ts = torque["timestamp_sample"].astype(np.int64)
    thrust_ts = thrust["timestamp_sample"].astype(np.int64)
    if np.any(np.diff(torque_ts) < 0):
        torque_ts = torque["timestamp"].astype(np.int64)
    if np.any(np.diff(thrust_ts) < 0):
        thrust_ts = thrust["timestamp"].astype(np.int64)

    torque_idx = np.searchsorted(torque_ts, key_ts, side="right") - 1
    thrust_idx = np.searchsorted(thrust_ts, key_ts, side="right") - 1
    valid = (torque_idx >= 0) & (thrust_idx >= 0)
    torque_age = np.full(len(key_ts), 10**15, dtype=np.int64)
    thrust_age = np.full(len(key_ts), 10**15, dtype=np.int64)
    torque_age[valid] = key_ts[valid] - torque_ts[torque_idx[valid]]
    thrust_age[valid] = key_ts[valid] - thrust_ts[thrust_idx[valid]]

    mask = (
        status_mask(data, actuator_ts, nav_states)
        & valid
        & (torque_age >= 0)
        & (thrust_age >= 0)
        & (torque_age <= max_age_us)
        & (thrust_age <= max_age_us)
    )
    indexes = np.where(mask)[0]
    if row_limit is not None and len(indexes) > row_limit:
        stride = max(1, len(indexes) // row_limit)
        indexes = indexes[::stride][:row_limit]

    x_rows: list[list[float]] = []
    y_rows: list[list[float]] = []
    for index in indexes:
        torque_row = torque_idx[index]
        thrust_row = thrust_idx[index]
        x_rows.append(
            [
                float(torque["xyz[0]"][torque_row]),
                float(torque["xyz[1]"][torque_row]),
                float(torque["xyz[2]"][torque_row]),
                float(thrust["xyz[0]"][thrust_row]),
                float(thrust["xyz[1]"][thrust_row]),
                float(thrust["xyz[2]"][thrust_row]),
                1.0,
            ]
        )
        y_rows.append([float(actuator[f"control[{i}]"][index]) for i in range(4)])

    return indexes, np.asarray(x_rows, dtype=float), np.asarray(y_rows, dtype=float)


def frame_rmse(x: np.ndarray, y: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    if len(x) == 0:
        return np.array([], dtype=float)
    residual = y - x @ matrix
    return np.sqrt(np.mean(residual * residual, axis=1))


def mcnn_value_labels(data: dict[str, dict[str, np.ndarray]], actuator_indexes: np.ndarray) -> np.ndarray:
    actuator = data["actuator_motors"]
    actuator_ts = actuator["timestamp"].astype(np.int64)[actuator_indexes]
    actuator_controls = np.vstack([actuator[f"control[{i}]"][actuator_indexes] for i in range(4)]).T
    neural = data.get("neural_control")
    labels = np.full(len(actuator_indexes), "allocator_or_other", dtype=object)
    if neural is None:
        return labels

    neural_ts = neural["timestamp"].astype(np.int64)
    neural_out = np.vstack([neural[f"network_output[{i}]"] for i in range(4)]).T
    positions = np.searchsorted(neural_ts, actuator_ts)
    for row, position in enumerate(positions):
        best: tuple[int, int] | None = None
        for candidate in (position - 1, position, position + 1):
            if 0 <= candidate < len(neural_ts):
                dt = abs(int(actuator_ts[row]) - int(neural_ts[candidate]))
                if dt <= 5_000 and (best is None or dt < best[0]):
                    best = (dt, candidate)
        if best is not None and float(np.max(np.abs(actuator_controls[row] - neural_out[best[1]]))) < 1e-6:
            labels[row] = "neural_value_match"
    return labels


def confusion(labels: np.ndarray, residuals: np.ndarray, threshold: float) -> dict[str, int]:
    pred = np.where(residuals <= threshold, "allocator_or_other", "neural_value_match")
    return {
        "allocator_as_allocator": int(np.sum((labels == "allocator_or_other") & (pred == "allocator_or_other"))),
        "allocator_as_neural": int(np.sum((labels == "allocator_or_other") & (pred == "neural_value_match"))),
        "neural_as_allocator": int(np.sum((labels == "neural_value_match") & (pred == "allocator_or_other"))),
        "neural_as_neural": int(np.sum((labels == "neural_value_match") & (pred == "neural_value_match"))),
    }


def best_threshold(labels: np.ndarray, residuals: np.ndarray) -> tuple[float, float, dict[str, int]]:
    best_acc = -1.0
    best_thr = 0.0
    best_conf: dict[str, int] = {}
    for threshold in np.linspace(0.02, 1.0, 491):
        conf = confusion(labels, residuals, float(threshold))
        correct = conf["allocator_as_allocator"] + conf["neural_as_neural"]
        total = sum(conf.values())
        acc = correct / total if total else 0.0
        if acc > best_acc:
            best_acc = acc
            best_thr = float(threshold)
            best_conf = conf
    return best_thr, best_acc, best_conf


def source_rates(data: dict[str, dict[str, np.ndarray]], nav_states: set[int]) -> dict[str, float | int]:
    actuator = data["actuator_motors"]
    ts = actuator["timestamp"].astype(np.int64)
    mask = status_mask(data, ts, nav_states)
    selected_ts = ts[mask]
    sample = actuator["timestamp_sample"].astype(np.int64)[mask]
    if len(selected_ts) == 0:
        return {"duration_s": 0.0, "actuator_count": 0, "actuator_rate_hz": 0.0}
    duration_s = max((int(selected_ts[-1]) - int(selected_ts[0])) / 1e6, 1e-9)
    neural_tag = sample > 1_000_000_000_000
    allocator_tag = (sample >= 0) & (sample < 1_000_000_000)
    return {
        "duration_s": float(duration_s),
        "actuator_count": int(len(selected_ts)),
        "actuator_rate_hz": float(len(selected_ts) / duration_s),
        "timestamp_sample_allocator_count": int(np.sum(allocator_tag)),
        "timestamp_sample_allocator_rate_hz": float(np.sum(allocator_tag) / duration_s),
        "timestamp_sample_neural_count": int(np.sum(neural_tag)),
        "timestamp_sample_neural_rate_hz": float(np.sum(neural_tag) / duration_s),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mcnn_rows = load_jsonl(MCNN_SWEEP)
    raptor_rows = load_jsonl(RAPTOR_SWEEP)

    train_rows = mcnn_rows[:30]
    holdout_rows = mcnn_rows[30:45]
    mcnn_check_rows = mcnn_rows[45:60]
    raptor_probe_rows = raptor_rows[45:60]

    train_x: list[np.ndarray] = []
    train_y: list[np.ndarray] = []
    train_counts: list[int] = []
    for row in train_rows:
        data = load_ulog(row["evidence"]["ulog_paths"]["classical"])
        _, x_rows, y_rows = aligned_allocator_rows(data, {14}, row_limit=2_000)
        train_x.append(x_rows)
        train_y.append(y_rows)
        train_counts.append(int(len(x_rows)))

    matrix, *_ = np.linalg.lstsq(np.vstack(train_x), np.vstack(train_y), rcond=None)
    train_residuals = frame_rmse(np.vstack(train_x), np.vstack(train_y), matrix)

    holdout_residuals: list[np.ndarray] = []
    for row in holdout_rows:
        data = load_ulog(row["evidence"]["ulog_paths"]["classical"])
        _, x_rows, y_rows = aligned_allocator_rows(data, {14}, row_limit=2_000)
        holdout_residuals.append(frame_rmse(x_rows, y_rows, matrix))
    holdout_all = np.concatenate(holdout_residuals) if holdout_residuals else np.array([], dtype=float)

    mcnn_detail_rows: list[dict[str, Any]] = []
    all_mcnn_residuals: list[np.ndarray] = []
    all_mcnn_labels: list[np.ndarray] = []
    mcnn_rate_rows: list[dict[str, Any]] = []
    for row in mcnn_check_rows:
        data = load_ulog(row["evidence"]["ulog_paths"]["mcnn"])
        actuator_indexes, x_rows, y_rows = aligned_allocator_rows(data, {23})
        residuals = frame_rmse(x_rows, y_rows, matrix)
        labels = mcnn_value_labels(data, actuator_indexes)
        all_mcnn_residuals.append(residuals)
        all_mcnn_labels.append(labels)
        for label in ("allocator_or_other", "neural_value_match"):
            mask = labels == label
            mcnn_detail_rows.append(
                {
                    "tag": row.get("tag"),
                    "label": label,
                    "count": int(np.sum(mask)),
                    "rmse_median": float(np.median(residuals[mask])) if np.any(mask) else math.nan,
                    "rmse_p95": float(np.percentile(residuals[mask], 95)) if np.any(mask) else math.nan,
                }
            )
        rate = source_rates(data, {23})
        rate["tag"] = row.get("tag")
        mcnn_rate_rows.append(rate)

    mcnn_residuals = np.concatenate(all_mcnn_residuals) if all_mcnn_residuals else np.array([], dtype=float)
    mcnn_labels = np.concatenate(all_mcnn_labels) if all_mcnn_labels else np.array([], dtype=object)
    threshold, agreement, conf = best_threshold(mcnn_labels, mcnn_residuals)
    method_valid = bool(agreement >= 0.95)

    raptor_rate_rows: list[dict[str, Any]] = []
    raptor_residuals: list[np.ndarray] = []
    if method_valid:
        for row in raptor_probe_rows:
            data = load_ulog(row["evidence"]["ulog_paths"]["raptor"])
            _, x_rows, y_rows = aligned_allocator_rows(data, {23})
            raptor_residuals.append(frame_rmse(x_rows, y_rows, matrix))
            rate = source_rates(data, {23})
            rate["tag"] = row.get("tag")
            raptor_rate_rows.append(rate)

    with (OUT_DIR / "mixer_fingerprint_mcnn_detail.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["tag", "label", "count", "rmse_median", "rmse_p95"])
        writer.writeheader()
        writer.writerows(mcnn_detail_rows)

    with (OUT_DIR / "mixer_fingerprint_queue_rates.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "controller",
            "tag",
            "duration_s",
            "actuator_count",
            "actuator_rate_hz",
            "timestamp_sample_allocator_count",
            "timestamp_sample_allocator_rate_hz",
            "timestamp_sample_neural_count",
            "timestamp_sample_neural_rate_hz",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in mcnn_rate_rows:
            writer.writerow({"controller": "mcnn", **row})
        for row in raptor_rate_rows:
            writer.writerow({"controller": "raptor", **row})

    summary = {
        "command": "python3 scripts/px4_mixer_fingerprint_round5.py",
        "fit": {
            "train_log_count": len(train_rows),
            "train_rows_per_log_limit": 2000,
            "train_frame_count": int(sum(train_counts)),
            "matrix_shape": list(matrix.shape),
            "matrix": matrix.tolist(),
            "train_residual_rmse": qstats(train_residuals),
            "holdout_log_count": len(holdout_rows),
            "holdout_residual_rmse": qstats(holdout_all),
        },
        "mcnn_self_check": {
            "log_count": len(mcnn_check_rows),
            "value_match_label_counts": {str(key): int(np.sum(mcnn_labels == key)) for key in sorted(set(mcnn_labels))},
            "residual_by_value_label": {
                str(label): qstats(mcnn_residuals[mcnn_labels == label]) for label in sorted(set(mcnn_labels))
            },
            "best_threshold": threshold,
            "agreement": agreement,
            "confusion": conf,
            "method_valid_for_raptor": method_valid,
        },
        "raptor_application": {
            "status": "not_run_self_check_agreement_below_95pct" if not method_valid else "run",
            "log_count": len(raptor_probe_rows) if method_valid else 0,
            "residual_rmse": qstats(np.concatenate(raptor_residuals)) if raptor_residuals else qstats(np.array([])),
        },
        "queue_rate_probe": {
            "mcnn_logs": len(mcnn_rate_rows),
            "mcnn_timestamp_sample_allocator_rate_hz": qstats(
                np.asarray([row["timestamp_sample_allocator_rate_hz"] for row in mcnn_rate_rows], dtype=float)
            ),
            "mcnn_timestamp_sample_neural_rate_hz": qstats(
                np.asarray([row["timestamp_sample_neural_rate_hz"] for row in mcnn_rate_rows], dtype=float)
            ),
            "raptor_logs": len(raptor_rate_rows),
        },
    }
    (OUT_DIR / "mixer_fingerprint_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary["mcnn_self_check"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
