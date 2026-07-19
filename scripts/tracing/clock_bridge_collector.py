#!/usr/bin/env python3
"""Build a segmented, uncertainty-bounded ROS↔PX4 clock bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "data" / "schemas" / "clock_bridge.schema.json").read_text(encoding="utf-8")
)
PREREGISTERED_THRESHOLDS = {
    "minimum_sample_count": 20,
    "residual_max_ns": 100_000_000,
    "degraded_residual_max_ns": 250_000_000,
    "maximum_round_trip_time_ns": 20_000_000,
    "maximum_timesync_offset_span_ns": 5_000_000,
    "segment_jump_ns": 50_000_000,
}


def _median_int(values: Iterable[int]) -> int:
    return int(round(statistics.median(values)))


def _px4_boot_us(sample: dict[str, Any]) -> int:
    if sample.get("px4_boot_timestamp_us") is not None:
        return int(sample["px4_boot_timestamp_us"])
    timestamp = int(sample["px4_timestamp_us"])
    if sample.get("timesync_estimated_offset_us") is not None:
        return timestamp + int(sample["timesync_estimated_offset_us"])
    return timestamp


def _segments(samples: list[dict[str, Any]], jump_ns: int) -> list[list[dict[str, Any]]]:
    segments: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    previous_px4: int | None = None
    previous_ros: int | None = None
    previous_monotonic: int | None = None
    previous_source_protocol: int | None = None
    previous_converged: bool | None = None
    for sample in samples:
        px4 = _px4_boot_us(sample)
        ros = int(sample["ros_receive_ns"])
        monotonic = int(sample["monotonic_receive_ns"])
        source_protocol = int(sample.get("timesync_source_protocol", 0))
        converged = bool(sample.get("timesync_converged", True))
        reset = (
            previous_px4 is not None
            and (
                px4 < previous_px4
                or ros <= int(previous_ros)
                or monotonic <= int(previous_monotonic)
                or abs((ros - int(previous_ros)) - (monotonic - int(previous_monotonic)))
                > jump_ns
                or source_protocol != previous_source_protocol
                or converged != previous_converged
            )
        )
        if reset and current:
            segments.append(current)
            current = []
        current.append(sample)
        previous_px4 = px4
        previous_ros = ros
        previous_monotonic = monotonic
        previous_source_protocol = source_protocol
        previous_converged = converged
    if current:
        segments.append(current)
    return segments


def _drop_initial_delivery_backlog(
    samples: list[dict[str, Any]], jump_ns: int
) -> tuple[list[dict[str, Any]], int]:
    """Exclude DDS discovery backlog before fitting a receive-time bridge.

    A newly-created subscription can receive multiple already-in-flight samples in
    one callback burst. Their PX4 timestamp spacing then cannot correspond to their
    receive-time spacing. Once the first causal interval is observed, later jumps
    remain available to the normal segment detector.
    """
    backlog_observed = False
    for index in range(1, len(samples)):
        previous = samples[index - 1]
        current = samples[index]
        px4_delta_ns = (_px4_boot_us(current) - _px4_boot_us(previous)) * 1000
        ros_delta_ns = int(current["ros_receive_ns"]) - int(previous["ros_receive_ns"])
        if px4_delta_ns <= 0 or ros_delta_ns <= 0:
            backlog_observed = True
            continue
        if abs(ros_delta_ns - px4_delta_ns) <= jump_ns:
            return (samples[index:], index) if backlog_observed else (samples, 0)
        backlog_observed = True
    return samples, 0


def _evaluate_segment(
    segment: list[dict[str, Any]], thresholds: dict[str, int], segment_index: int
) -> dict[str, Any]:
    # PX4 SITL time can run at a repeatable rate slightly different from wall time.
    # Fit an affine bridge around a local reference so that this rate difference is
    # bounded by the measured residual instead of being mistaken for a reset.
    pairs = [(_px4_boot_us(sample), int(sample["ros_receive_ns"])) for sample in segment]
    unique_pairs: list[tuple[int, int]] = []
    for pair in pairs:
        if unique_pairs and pair[0] == unique_pairs[-1][0]:
            continue
        unique_pairs.append(pair)
    if len(unique_pairs) >= 2:
        reference_px4_us = _median_int(pair[0] for pair in unique_pairs)
        reference_ros_ns = _median_int(pair[1] for pair in unique_pairs)
        centered_px4_ns = [(pair[0] - reference_px4_us) * 1000 for pair in unique_pairs]
        centered_ros_ns = [pair[1] - reference_ros_ns for pair in unique_pairs]
        denominator = sum(value * value for value in centered_px4_ns)
        rate_ratio = (
            sum(x_value * y_value for x_value, y_value in zip(centered_px4_ns, centered_ros_ns))
            / denominator
            if denominator
            else 1.0
        )
        intercept_adjustment = _median_int(
            y_value - rate_ratio * x_value
            for x_value, y_value in zip(centered_px4_ns, centered_ros_ns)
        )
        reference_ros_ns += intercept_adjustment
        residuals = [
            abs(
                pair[1]
                - int(
                    round(
                        reference_ros_ns
                        + rate_ratio * (pair[0] - reference_px4_us) * 1000
                    )
                )
            )
            for pair in unique_pairs
        ]
        offset_ns = reference_ros_ns - reference_px4_us * 1000
    else:
        reference_px4_us = unique_pairs[0][0] if unique_pairs else None
        reference_ros_ns = unique_pairs[0][1] if unique_pairs else None
        rate_ratio = 1.0 if unique_pairs else None
        offset_ns = (
            reference_ros_ns - reference_px4_us * 1000 if unique_pairs else None
        )
        residuals = [0] if unique_pairs else []
    residual_median = _median_int(residuals) if residuals else None
    residual_max = max(residuals, default=None)
    rtts = [
        int(sample.get("timesync_round_trip_time_us", 0)) * 1000
        for sample in segment
        if sample.get("timesync_round_trip_time_us") is not None
    ]
    source_protocols = {
        int(sample.get("timesync_source_protocol", 0)) for sample in segment
    }
    maximum_rtt = max(rtts, default=0)
    uncertainty = (
        int(residual_max) + maximum_rtt // 2 if residual_max is not None else None
    )
    reasons: list[str] = []
    if len(unique_pairs) < thresholds["minimum_sample_count"]:
        reasons.append("sample_count_below_preregistered_minimum")
    if source_protocols != {2}:
        reasons.append("DDS_timesync_not_observed_for_every_sample")
    if not all(sample.get("timesync_converged", True) for sample in segment):
        reasons.append("timesync_convergence_evidence_missing")
    if maximum_rtt > thresholds["maximum_round_trip_time_ns"]:
        reasons.append("timesync_round_trip_time_exceeds_threshold")
    hard_invalid = any(
        reason
        in {
            "sample_count_below_preregistered_minimum",
            "DDS_timesync_not_observed_for_every_sample",
            "timesync_convergence_evidence_missing",
            "timesync_estimated_offset_not_converged",
            "timesync_round_trip_time_exceeds_threshold",
        }
        for reason in reasons
    )
    if hard_invalid or residual_max is None:
        status = "INVALID"
    elif residual_max <= thresholds["residual_max_ns"]:
        status = "VALID"
    elif residual_max <= thresholds["degraded_residual_max_ns"]:
        status = "DEGRADED"
        reasons.append("residual_exceeds_valid_threshold")
    else:
        status = "INVALID"
        reasons.append("residual_exceeds_degraded_threshold")

    identity_material = json.dumps(
        {
            "first": segment[0] if segment else None,
            "last": segment[-1] if segment else None,
            "index": segment_index,
            "offset": offset_ns,
        },
        sort_keys=True,
    ).encode()
    return {
        "schema_version": "1.0",
        "clock_bridge_id": "clock-" + hashlib.sha256(identity_material).hexdigest()[:16],
        "status": status,
        "offset_ns": offset_ns,
        "rate_ratio": rate_ratio,
        "reference_px4_us": reference_px4_us,
        "reference_ros_ns": reference_ros_ns,
        "uncertainty_ns": uncertainty,
        "residual_median_ns": residual_median,
        "residual_max_ns": residual_max,
        "sample_count": len(unique_pairs),
        "valid_from": _px4_boot_us(segment[0]) if segment else None,
        "valid_until": _px4_boot_us(segment[-1]) if segment else None,
        "timestamp_domains": {"source": "px4_boot_us", "target": "ros_node_ns"},
        "thresholds": thresholds,
        "segment_count": 1,
        "reset_count": 0,
        "reasons": reasons,
    }


def collect(
    samples: list[dict[str, Any]], thresholds: dict[str, int] | None = None
) -> dict[str, Any]:
    selected_thresholds = dict(PREREGISTERED_THRESHOLDS if thresholds is None else thresholds)
    ordered = sorted(samples, key=lambda sample: int(sample["monotonic_receive_ns"]))
    ordered, discarded_backlog = _drop_initial_delivery_backlog(
        ordered, selected_thresholds["segment_jump_ns"]
    )
    segments = _segments(ordered, selected_thresholds["segment_jump_ns"])
    evaluated = [
        _evaluate_segment(segment, selected_thresholds, index)
        for index, segment in enumerate(segments)
    ]
    if evaluated:
        rank = {"VALID": 2, "DEGRADED": 1, "INVALID": 0}
        result = max(
            evaluated,
            key=lambda item: (rank[item["status"]], item["sample_count"], item["valid_until"] or 0),
        )
    else:
        result = _evaluate_segment([], selected_thresholds, 0)
    result["segment_count"] = len(segments)
    result["reset_count"] = max(0, len(segments) - 1)
    result["discarded_initial_backlog_samples"] = discarded_backlog
    if len(segments) > 1:
        result["reasons"].append("clock_reset_or_jump_segmented")
    Draft202012Validator(SCHEMA).validate(result)
    return result


def load_samples(path: Path) -> list[dict[str, Any]]:
    samples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("event_type") == "clock_bridge_sample":
            samples.append(record)
    def source(sample: dict[str, Any]) -> Any:
        return sample.get("sample_source") or sample.get("details", {}).get(
            "sample_source"
        )

    vehicle_status_samples = [sample for sample in samples if source(sample) == "vehicle_status"]
    timesync_samples = [
        sample for sample in samples if source(sample) == "timesync_status"
    ]
    return vehicle_status_samples or timesync_samples or samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--thresholds", type=Path)
    args = parser.parse_args()
    thresholds = (
        json.loads(args.thresholds.read_text(encoding="utf-8"))
        if args.thresholds is not None
        else None
    )
    result = collect(load_samples(args.samples), thresholds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "clock_bridge_id": result["clock_bridge_id"]}))
    return 0 if result["status"] in {"VALID", "DEGRADED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
