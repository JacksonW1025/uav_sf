#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

from img_style import COL_DOUBLE, OKABE_ITO, save
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from m1_metrics import first_dataset, quaternion, task_event_elapsed_us, vector3  # noqa: E402


FIG_NAME = "fig_anchor_trace_three_way"
MCNN_PAIR2_DIR = (
    REPO_ROOT
    / "runs/route_a_anchor_regression/route_a_anchor_regression_20260629/evals/"
    / "route_a_anchor_regression_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_confirm1_s20261901"
)
RAPTOR_PAIR2_DIR = (
    REPO_ROOT
    / "runs/campaigns/raptor_gate0_anchor_recheck_20260705/evals/"
    / "raptor_gate0_anchor_recheck_20260705_pair2_rp48_62_rate2p45_2p90_w6_r6_f045_confirm1_s20261901"
)
ATTITUDE_THRESHOLD_DEG = 90.0
RATE_THRESHOLD_RAD_S = 8.0
CONTROLLERS = ["classical", "mcnn", "raptor"]
CONTROLLER_SPECS = {
    "classical": {
        "dir": MCNN_PAIR2_DIR,
        "file_token": "classical",
        "record_kind": "record",
        "provenance_name": "classical",
    },
    "mcnn": {
        "dir": MCNN_PAIR2_DIR,
        "file_token": "mcnn",
        "record_kind": "record",
        "provenance_name": "mc_nn",
    },
    "raptor": {
        "dir": RAPTOR_PAIR2_DIR,
        "file_token": "raptor",
        "record_kind": "property",
        "provenance_name": "RAPTOR",
    },
}


def one_file(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern))
    return matches[0] if matches else None


def quat_tilt_deg(q: np.ndarray) -> np.ndarray:
    q1 = q[:, 1]
    q2 = q[:, 2]
    r33 = 1.0 - 2.0 * (q1 * q1 + q2 * q2)
    return np.rad2deg(np.arccos(np.clip(r33, -1.0, 1.0)))


def downsample(x: np.ndarray, y: np.ndarray, max_points: int = 1800) -> tuple[np.ndarray, np.ndarray]:
    if len(x) <= max_points:
        return x, y
    step = int(math.ceil(len(x) / max_points))
    return x[::step], y[::step]


def seed_from(*values: object) -> int | None:
    for value in values:
        if value is None:
            continue
        match = re.search(r"_s(\d+)", str(value))
        if match:
            return int(match.group(1))
    return None


def load_record(controller: str) -> dict[str, object]:
    spec = CONTROLLER_SPECS[controller]
    directory = Path(spec["dir"])
    token = str(spec["file_token"])
    if spec["record_kind"] == "record":
        path = directory / f"{token}_record.json"
    else:
        path = one_file(directory, f"*_{token}_property.json")
        if path is None:
            raise FileNotFoundError(f"missing {controller} property json in {directory.relative_to(REPO_ROOT)}")
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    severity = data.get("severity", {})
    if not isinstance(severity, dict):
        severity = {}
    return {
        "path": Path(path),
        "seed": data.get("seed") or seed_from(data.get("tag"), path),
        "severity": severity.get("severity"),
        "severity_label": severity.get("severity_label") or severity.get("label"),
        "reasons": severity.get("reasons", []),
    }


def load_trace(controller: str) -> dict[str, object]:
    from pyulog import ULog

    spec = CONTROLLER_SPECS[controller]
    directory = Path(spec["dir"])
    token = str(spec["file_token"])
    ulog_path = one_file(directory, f"*_{token}.ulg")
    task_path = one_file(directory, f"*_{token}_task.json")
    metrics_path = one_file(directory, f"*_{token}_metrics.json")
    if ulog_path is None or task_path is None or metrics_path is None:
        missing = [
            name
            for name, path in [("ulog", ulog_path), ("task", task_path), ("metrics", metrics_path)]
            if path is None
        ]
        raise FileNotFoundError(f"missing {controller} files in {directory.relative_to(REPO_ROOT)}: {missing}")

    with task_path.open("r", encoding="utf-8") as handle:
        task = json.load(handle)
    with metrics_path.open("r", encoding="utf-8") as handle:
        metrics = json.load(handle)

    origin_us = int(metrics["task_to_ulog_origin_us"])
    switch_elapsed_us = task_event_elapsed_us(task, "state_trigger")
    if switch_elapsed_us is None:
        switch_elapsed_us = task_event_elapsed_us(task, "controller_active")
    if switch_elapsed_us is None:
        raise ValueError(f"cannot find switch event in {task_path.relative_to(REPO_ROOT)}")
    switch_us = origin_us + int(switch_elapsed_us)

    ulog = ULog(str(ulog_path))
    att = first_dataset(ulog, "vehicle_attitude_groundtruth") or first_dataset(ulog, "vehicle_attitude")
    rates = first_dataset(ulog, "vehicle_angular_velocity_groundtruth") or first_dataset(
        ulog, "vehicle_angular_velocity"
    )
    if att is None or rates is None:
        raise ValueError(f"missing attitude/rate datasets in {ulog_path.relative_to(REPO_ROOT)}")

    att_t = (att.data["timestamp"].astype(np.int64) - switch_us) / 1e6
    attitude = quat_tilt_deg(quaternion(att.data))
    rate_t = (rates.data["timestamp"].astype(np.int64) - switch_us) / 1e6
    rate = np.linalg.norm(vector3(rates.data, "xyz"), axis=1)
    att_t, attitude = downsample(att_t, attitude)
    rate_t, rate = downsample(rate_t, rate)

    record = load_record(controller)
    return {
        "controller": controller,
        "provenance_name": spec["provenance_name"],
        "ulog_path": ulog_path,
        "task_path": task_path,
        "metrics_path": metrics_path,
        "record_path": record["path"],
        "seed": record["seed"] or seed_from(task_path, metrics_path, ulog_path),
        "switch_elapsed_s": float(switch_elapsed_us) / 1e6,
        "att_t": att_t,
        "attitude_deg": attitude,
        "rate_t": rate_t,
        "rate_rad_s": rate,
        "severity": record["severity"],
        "severity_label": record["severity_label"],
        "reasons": record["reasons"],
    }


def first_crossing(x: np.ndarray, y: np.ndarray, threshold: float) -> float | None:
    idx = np.where((x >= 0.0) & (y >= threshold))[0]
    return float(x[idx[0]]) if len(idx) else None


def fmt_optional(value: float | None) -> str:
    return "None" if value is None else f"{value:.3f}"


def print_provenance(traces: dict[str, dict[str, object]]) -> None:
    print(f"SOURCE: {MCNN_PAIR2_DIR.relative_to(REPO_ROOT)}")
    print(f"SOURCE: {RAPTOR_PAIR2_DIR.relative_to(REPO_ROOT)}")
    print("ANCHOR: rp48_62_rate2p45_2p90_w6_r6_f045_confirm1")
    for controller in CONTROLLERS:
        trace = traces[controller]
        att = np.asarray(trace["attitude_deg"], dtype=float)
        att_t = np.asarray(trace["att_t"], dtype=float)
        rate = np.asarray(trace["rate_rad_s"], dtype=float)
        rate_t = np.asarray(trace["rate_t"], dtype=float)
        post_att = att[(att_t >= 0.0) & (att_t <= 50.0)]
        post_rate = rate[(rate_t >= 0.0) & (rate_t <= 50.0)]
        first_90 = first_crossing(att_t, att, ATTITUDE_THRESHOLD_DEG)
        first_8 = first_crossing(rate_t, rate, RATE_THRESHOLD_RAD_S)
        print(f"SOURCE: {Path(trace['ulog_path']).relative_to(REPO_ROOT)}")
        print(f"SOURCE: {Path(trace['task_path']).relative_to(REPO_ROOT)}")
        print(f"SOURCE: {Path(trace['metrics_path']).relative_to(REPO_ROOT)}")
        print(f"SOURCE: {Path(trace['record_path']).relative_to(REPO_ROOT)}")
        print(
            "VALUE: "
            f"{trace['provenance_name']} seed={trace['seed']} "
            f"severity={trace['severity']} label={trace['severity_label']} "
            f"switch_elapsed_s={trace['switch_elapsed_s']:.6f} "
            f"max_attitude_deg={float(np.nanmax(post_att)):.3f} "
            f"max_rate_rad_s={float(np.nanmax(post_rate)):.3f} "
            f"first_90deg_s={fmt_optional(first_90)} "
            f"first_8rad_s={fmt_optional(first_8)}"
        )


def main() -> int:
    for controller in CONTROLLERS:
        directory = Path(CONTROLLER_SPECS[controller]["dir"])
        if not directory.exists():
            print(f"BLOCKED: local ULOG directory not found: {directory.relative_to(REPO_ROOT)}")
            return 0
    try:
        traces = {controller: load_trace(controller) for controller in CONTROLLERS}
    except Exception as exc:
        print(f"BLOCKED: cannot build three-way trace figure from local ULOGs: {exc}")
        return 0

    print_provenance(traces)

    mcnn = traces["mcnn"]
    crossings = [
        first_crossing(np.asarray(mcnn["att_t"]), np.asarray(mcnn["attitude_deg"]), ATTITUDE_THRESHOLD_DEG),
        first_crossing(np.asarray(mcnn["rate_t"]), np.asarray(mcnn["rate_rad_s"]), RATE_THRESHOLD_RAD_S),
    ]
    finite_crossings = [value for value in crossings if value is not None]
    x_end = max(28.0, max(finite_crossings) + 5.0) if finite_crossings else 30.0
    x_start = -1.0

    fig, axes = plt.subplots(2, 1, figsize=(COL_DOUBLE, 3.55), sharex=True)
    styles = {
        "classical": {"color": OKABE_ITO[5], "linestyle": "-", "label": "classical (S0)"},
        "mcnn": {"color": OKABE_ITO[6], "linestyle": "--", "label": "mc_nn (S3)"},
        "raptor": {"color": OKABE_ITO[3], "linestyle": "-", "label": "RAPTOR (S0)"},
    }
    for controller in CONTROLLERS:
        trace = traces[controller]
        style = styles[controller]
        axes[0].plot(trace["att_t"], trace["attitude_deg"], **style)
        axes[1].plot(trace["rate_t"], trace["rate_rad_s"], **style)

    axes[0].axhline(ATTITUDE_THRESHOLD_DEG, color="0.2", linestyle=":", linewidth=0.8)
    axes[1].axhline(RATE_THRESHOLD_RAD_S, color="0.2", linestyle=":", linewidth=0.8)
    for ax in axes:
        ax.axvline(0.0, color="0.35", linestyle="-", linewidth=0.6)
        ax.set_xlim(x_start, x_end)
        ax.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.4)
    axes[0].set_ylabel("attitude tilt (deg)")
    axes[1].set_ylabel("angular-rate norm (rad/s)")
    axes[1].set_xlabel("time from switch (s)")
    axes[0].legend(loc="upper left", ncol=3)
    axes[0].text(x_end - 0.3, ATTITUDE_THRESHOLD_DEG + 3.0, "90 deg", ha="right", va="bottom", fontsize=8)
    axes[1].text(x_end - 0.3, RATE_THRESHOLD_RAD_S + 0.4, "8 rad/s", ha="right", va="bottom", fontsize=8)
    fig.subplots_adjust(hspace=0.16)
    save(fig, FIG_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
