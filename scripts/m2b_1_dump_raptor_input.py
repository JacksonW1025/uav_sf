#!/usr/bin/env python3
"""Dump one logged raptor_input sample and its 22-D policy vector."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from pyulog import ULog


REPO_ROOT = Path(__file__).resolve().parents[1]


def finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def first_dataset(ulog: ULog, name: str):
    for dataset in ulog.data_list:
        if dataset.name == name:
            return dataset
    raise KeyError(f"missing ULOG dataset {name}")


def vector(data: dict[str, np.ndarray], stem: str, size: int) -> list[np.ndarray]:
    out: list[np.ndarray] = []
    for index in range(size):
        key = f"{stem}[{index}]"
        if key not in data:
            raise KeyError(f"missing field {key}")
        out.append(data[key])
    return out


def quat_to_rotmat(q: list[float]) -> list[float]:
    qw, qx, qy, qz = q
    return [
        1 - 2 * qy * qy - 2 * qz * qz,
        2 * qx * qy - 2 * qw * qz,
        2 * qx * qz + 2 * qw * qy,
        2 * qx * qy + 2 * qw * qz,
        1 - 2 * qx * qx - 2 * qz * qz,
        2 * qy * qz - 2 * qw * qx,
        2 * qx * qz - 2 * qw * qy,
        2 * qy * qz + 2 * qw * qx,
        1 - 2 * qx * qx - 2 * qy * qy,
    ]


def label_vector(position: list[float], orientation: list[float], linear_velocity: list[float], angular_velocity: list[float], previous_action: list[float]) -> list[dict[str, Any]]:
    values = position + quat_to_rotmat(orientation) + linear_velocity + angular_velocity + previous_action
    labels = [
        "position_target_frame_flu_x",
        "position_target_frame_flu_y",
        "position_target_frame_flu_z",
        "orientation_rotmat_r00",
        "orientation_rotmat_r01",
        "orientation_rotmat_r02",
        "orientation_rotmat_r10",
        "orientation_rotmat_r11",
        "orientation_rotmat_r12",
        "orientation_rotmat_r20",
        "orientation_rotmat_r21",
        "orientation_rotmat_r22",
        "linear_velocity_target_frame_flu_x",
        "linear_velocity_target_frame_flu_y",
        "linear_velocity_target_frame_flu_z",
        "angular_velocity_body_flu_x",
        "angular_velocity_body_flu_y",
        "angular_velocity_body_flu_z",
        "action_history_0_motor0",
        "action_history_0_motor1",
        "action_history_0_motor2",
        "action_history_0_motor3",
    ]
    return [{"index": i, "label": label, "value": values[i]} for i, label in enumerate(labels)]


def dump(ulog_path: Path, output: Path) -> dict[str, Any]:
    ulog = ULog(str(ulog_path), ["raptor_input"])
    data = first_dataset(ulog, "raptor_input").data
    timestamps = data["timestamp"]
    active = data.get("active")
    if active is not None and np.any(active.astype(bool)):
        sample_index = int(np.flatnonzero(active.astype(bool))[0])
    else:
        sample_index = 0

    position = [float(column[sample_index]) for column in vector(data, "position", 3)]
    orientation = [float(column[sample_index]) for column in vector(data, "orientation", 4)]
    linear_velocity = [float(column[sample_index]) for column in vector(data, "linear_velocity", 3)]
    angular_velocity = [float(column[sample_index]) for column in vector(data, "angular_velocity", 3)]
    previous_action = [float(column[sample_index]) for column in vector(data, "previous_action", 4)]

    sample = {
        "ulog": str(ulog_path),
        "ulog_start_timestamp_us": int(ulog.start_timestamp),
        "topic": "raptor_input",
        "sample_index": sample_index,
        "timestamp_us": int(timestamps[sample_index]),
        "elapsed_from_ulog_start_s": (int(timestamps[sample_index]) - int(ulog.start_timestamp)) / 1e6,
        "active": bool(active[sample_index]) if active is not None else None,
        "logged_fields": {
            "position": position,
            "orientation_quaternion_wxyz": orientation,
            "linear_velocity": linear_velocity,
            "angular_velocity": angular_velocity,
            "previous_action": previous_action,
        },
        "policy_vector_22": label_vector(position, orientation, linear_velocity, angular_velocity, previous_action),
        "finite": all(
            finite_float(value["value"]) is not None
            for value in label_vector(position, orientation, linear_velocity, angular_velocity, previous_action)
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(sample, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    return sample


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ulog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = dump(args.ulog.resolve(), args.output.resolve())
    print(json.dumps({"output": str(args.output), "sample_index": result["sample_index"], "active": result["active"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
