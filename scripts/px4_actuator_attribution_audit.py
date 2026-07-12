#!/usr/bin/env python3
"""Read-only actuator writer attribution parser for Round 3 audit."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

import numpy as np
from pyulog import ULog


@dataclass(frozen=True)
class LogCase:
    label: str
    path: str
    kind: str


LOGS = [
    LogCase(
        "mcnn_s3_pair1",
        "runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/evals/"
        "route_a_addendum3_diag_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_s20262001/"
        "mcnn_gate3_route_a_addendum3_diag_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_s20262001_mcnn.ulg",
        "mcnn",
    ),
    LogCase(
        "mcnn_s3_pair2",
        "runs/route_a_anchor_regression/route_a_anchor_regression_20260629/evals/"
        "route_a_anchor_regression_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_confirm1_s20261901/"
        "mcnn_gate3_route_a_anchor_regression_20260629_rp48_62_rate2p45_2p90_w6_r6_f045_confirm1_s20261901_mcnn.ulg",
        "mcnn",
    ),
    LogCase(
        "mcnn_s3_pair4",
        "runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/evals/"
        "route_a_addendum3_diag_20260629_rp36_44_rate1p55_2p15_w3_r4_f038_s20261902/"
        "mcnn_gate3_route_a_addendum3_diag_20260629_rp36_44_rate1p55_2p15_w3_r4_f038_s20261902_mcnn.ulg",
        "mcnn",
    ),
    LogCase(
        "mcnn_s3_pair5",
        "runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/evals/"
        "route_a_addendum3_diag_20260629_rp32_40_rate1p30_1p95_w0_r4_f038_s20261903/"
        "mcnn_gate3_route_a_addendum3_diag_20260629_rp32_40_rate1p30_1p95_w0_r4_f038_s20261903_mcnn.ulg",
        "mcnn",
    ),
    LogCase(
        "mcnn_safe_validity_e0000",
        "docs/validity_automation_real_20260627/evals/validity_automation_real_20260627_e0000/"
        "mcnn_gate3_validity_automation_real_20260627_e0000_mcnn.ulg",
        "mcnn",
    ),
    LogCase(
        "mcnn_safe_validity_e0001",
        "docs/validity_automation_real_20260627/evals/validity_automation_real_20260627_e0001/"
        "mcnn_gate3_validity_automation_real_20260627_e0001_mcnn.ulg",
        "mcnn",
    ),
    LogCase(
        "mcnn_safe_baseline_s20261302",
        "docs/mcnn_gonogo_gate3_20260625/evals/mcnn_gonogo_gate3_20260625_baseline_s20261302/"
        "mcnn_gate3_mcnn_gonogo_gate3_20260625_baseline_s20261302_mcnn.ulg",
        "mcnn",
    ),
    LogCase(
        "raptor_pair4_s20262302",
        "runs/campaigns/raptor_gate0_anchor_boundary_20260705/evals/"
        "raptor_gate0_anchor_boundary_20260705_pair4_rp36_44_rate1p55_2p15_w3_r4_f038_s20262302/"
        "m1_raptor_gate0_anchor_boundary_20260705_pair4_rp36_44_rate1p55_2p15_w3_r4_f038_s20262302_raptor.ulg",
        "raptor",
    ),
    LogCase(
        "raptor_pair5_s20262003",
        "runs/campaigns/raptor_gate0_anchor_boundary_20260705/evals/"
        "raptor_gate0_anchor_boundary_20260705_pair5_rp32_40_rate1p30_1p95_w0_r4_f038_s20262003/"
        "m1_raptor_gate0_anchor_boundary_20260705_pair5_rp32_40_rate1p30_1p95_w0_r4_f038_s20262003_raptor.ulg",
        "raptor",
    ),
]


def qstats(values: np.ndarray) -> str:
    if len(values) == 0:
        return "n/a"

    return (
        f"min={int(np.min(values))} "
        f"p50={int(np.percentile(values, 50))} "
        f"p95={int(np.percentile(values, 95))} "
        f"p99={int(np.percentile(values, 99))} "
        f"max={int(np.max(values))}"
    )


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

    if ("vehicle_angular_velocity", 0) in data:
        angular_velocity = data[("vehicle_angular_velocity", 0)]
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

    if ("vehicle_attitude", 0) in data:
        attitude = data[("vehicle_attitude", 0)]
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


def classify_mcnn_actuators(
    data: dict[tuple[str, int], dict[str, np.ndarray]], start: int, end: int
) -> tuple[np.ndarray, np.ndarray]:
    actuator = data[("actuator_motors", 0)]
    mask = (actuator["timestamp"] >= start) & (actuator["timestamp"] <= end)
    timestamps = actuator["timestamp"][mask].astype(np.int64)
    timestamp_sample = actuator["timestamp_sample"][mask].astype(np.int64)
    classes = np.full(len(timestamps), "other", dtype=object)
    classes[timestamp_sample > 10**12] = "neural_tag"
    valid_sample = (
        (timestamp_sample >= 0)
        & (timestamp_sample <= end + 1_000_000)
        & (np.abs(timestamps - timestamp_sample) <= 100_000)
    )
    classes[valid_sample] = "allocator_tag"
    return timestamps, classes


def classify_raptor_actuators(
    data: dict[tuple[str, int], dict[str, np.ndarray]], start: int, end: int
) -> tuple[np.ndarray, np.ndarray]:
    actuator = data[("actuator_motors", 0)]
    mask = (actuator["timestamp"] >= start) & (actuator["timestamp"] <= end)
    timestamps = actuator["timestamp"][mask].astype(np.int64)

    raptor_timestamps: set[int] = set()

    if ("raptor_input", 0) in data:
        raptor_input = data[("raptor_input", 0)]
        input_mask = (raptor_input["timestamp"] >= start) & (raptor_input["timestamp"] <= end)

        if "active" in raptor_input:
            input_mask = input_mask & raptor_input["active"].astype(bool)

        raptor_timestamps.update(map(int, raptor_input["timestamp"][input_mask].astype(np.int64)))

    if ("raptor_status", 0) in data:
        raptor_status = data[("raptor_status", 0)]
        status_mask = (raptor_status["timestamp"] >= start) & (raptor_status["timestamp"] <= end)

        if "active" in raptor_status:
            status_mask = status_mask & raptor_status["active"].astype(bool)

        raptor_timestamps.update(map(int, raptor_status["timestamp"][status_mask].astype(np.int64)))

    classes = np.array(
        ["raptor_tag" if int(timestamp) in raptor_timestamps else "allocator_or_other_tag" for timestamp in timestamps],
        dtype=object,
    )
    return timestamps, classes


def counts(classes: np.ndarray, mask: np.ndarray | None = None) -> dict[str, int]:
    selected = classes if mask is None else classes[mask]
    return {key: int(np.sum(selected == key)) for key in sorted(set(selected))}


def fraction_string(counts_by_class: dict[str, int]) -> str:
    total = sum(counts_by_class.values())

    if total == 0:
        return "n/a"

    return ",".join(f"{key}:{value}/{total}={value / total:.3f}" for key, value in counts_by_class.items())


def topic_rate(
    data: dict[tuple[str, int], dict[str, np.ndarray]], topic: str, start: int, end: int, duration_s: float
) -> str | None:
    topic_data = data.get((topic, 0))

    if not topic_data:
        return None

    timestamps = topic_data["timestamp"].astype(np.int64)
    count = int(np.sum((timestamps >= start) & (timestamps <= end)))
    return f"{topic}:{count / duration_s:.1f}"


def main() -> int:
    print(
        "label,kind,dur_s,loss,loss_dt_s,act_n,act_rate_hz,act_dt_us,"
        "act_dup_extra,act_20ms_dt_count,act_sources,outputs_n,outputs_rate_hz,"
        "output_sources,critical_output_sources,logger_rates_hz"
    )

    for log_case in LOGS:
        if not os.path.exists(log_case.path):
            print(f"{log_case.label},MISSING,{log_case.path}")
            continue

        ulog = ULog(log_case.path)
        data = {(dataset.name, dataset.multi_id): dataset.data for dataset in ulog.data_list}
        interval = first_nav23(data[("vehicle_status", 0)])

        if interval is None:
            print(f"{log_case.label},NO_NAV23")
            continue

        start, end = interval
        duration_s = (end - start) / 1e6

        if log_case.kind == "mcnn":
            actuator_timestamps, actuator_classes = classify_mcnn_actuators(data, start, end)
        else:
            actuator_timestamps, actuator_classes = classify_raptor_actuators(data, start, end)

        actuator_dt = np.diff(actuator_timestamps)
        _, duplicate_counts = np.unique(actuator_timestamps, return_counts=True)
        duplicate_extra = int(np.sum(duplicate_counts - 1))
        dt_20ms_count = int(np.sum((actuator_dt >= 18_000) & (actuator_dt <= 22_000)))

        actuator_outputs = data.get(("actuator_outputs", 0))
        if actuator_outputs:
            output_mask = (actuator_outputs["timestamp"] >= start) & (actuator_outputs["timestamp"] <= end)
            output_timestamps = actuator_outputs["timestamp"][output_mask].astype(np.int64)
            actuator_index = np.searchsorted(actuator_timestamps, output_timestamps, side="right") - 1
            aligned = (actuator_index >= 0) & ((output_timestamps - actuator_timestamps[actuator_index]) <= 20_000)
            output_classes = actuator_classes[actuator_index[aligned]]
        else:
            output_timestamps = np.array([], dtype=np.int64)
            aligned = np.array([], dtype=bool)
            output_classes = np.array([], dtype=object)

        loss_reason, first_loss = loss_time(data, start, end)
        critical_mask = (
            (output_timestamps[aligned] >= start) & (output_timestamps[aligned] <= first_loss)
            if len(output_timestamps)
            else np.array([], dtype=bool)
        )

        rate_parts = [
            rate
            for rate in (
                topic_rate(data, "actuator_motors", start, end, duration_s),
                topic_rate(data, "actuator_outputs", start, end, duration_s),
                topic_rate(data, "neural_control", start, end, duration_s),
                topic_rate(data, "raptor_input", start, end, duration_s),
                topic_rate(data, "vehicle_angular_velocity", start, end, duration_s),
                topic_rate(data, "vehicle_torque_setpoint", start, end, duration_s),
            )
            if rate
        ]

        print(
            f"{log_case.label},{log_case.kind},{duration_s:.3f},{loss_reason},{(first_loss - start) / 1e6:.3f},"
            f"{len(actuator_timestamps)},{len(actuator_timestamps) / duration_s:.2f},{qstats(actuator_dt)},"
            f"{duplicate_extra},{dt_20ms_count},{fraction_string(counts(actuator_classes))},"
            f"{len(output_timestamps)},{len(output_timestamps) / duration_s if duration_s > 0 else 0:.2f},"
            f"{fraction_string(counts(output_classes))},"
            f"{fraction_string(counts(output_classes, critical_mask))},"
            f"{'|'.join(rate_parts)}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
