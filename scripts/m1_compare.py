#!/usr/bin/env python3
"""Compare one classical and one RAPTOR M1 metrics result."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


NOISE_FLOOR_DEFAULT = {
    "tracking_error_max_m": 0.05,
    "tracking_error_rms_m": 0.04,
    "final_error_m": 0.05,
    "roll_pitch_max_deg": 1.0,
    "roll_pitch_std_deg": 0.5,
    "angular_rate_max_rad_s": 0.02,
    "angular_rate_std_rad_s": 0.02,
    "motor_saturation_ratio": 0.01,
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def metric_delta(raptor: dict[str, Any], classical: dict[str, Any], key: str) -> float | None:
    rv = raptor.get(key)
    cv = classical.get(key)
    if rv is None or cv is None:
        return None
    return float(rv) - float(cv)


def trace_array(metrics: dict[str, Any], key: str) -> np.ndarray:
    trace = metrics.get(key) or []
    if not trace:
        return np.empty((0, 4), dtype=float)
    return np.asarray(trace, dtype=float)


def time_to_divergence(classical: dict[str, Any], raptor: dict[str, Any], threshold_m: float) -> float | None:
    a = trace_array(classical, "position_trace")
    b = trace_array(raptor, "position_trace")
    if len(a) < 2 or len(b) < 2:
        return None
    start = max(float(a[0, 0]), float(b[0, 0]))
    end = min(float(a[-1, 0]), float(b[-1, 0]))
    if end <= start:
        return None
    times = np.linspace(start, end, max(2, int((end - start) * 20)))
    apos = np.column_stack([np.interp(times, a[:, 0], a[:, i]) for i in range(1, 4)])
    bpos = np.column_stack([np.interp(times, b[:, 0], b[:, i]) for i in range(1, 4)])
    dist = np.linalg.norm(apos - bpos, axis=1)
    idx = np.where(dist > threshold_m)[0]
    if len(idx) == 0:
        return None
    return float(times[int(idx[0])] - start)


def quadrant(classical_safe: bool, raptor_safe: bool) -> str:
    if classical_safe and raptor_safe:
        return "boring_both_safe"
    if not classical_safe and raptor_safe:
        return "interesting_not_bug"
    if classical_safe and not raptor_safe:
        return "primary_bug"
    return "too_hard_not_bug"


def noise_floor(theta: dict[str, Any], classical: dict[str, Any], raptor: dict[str, Any]) -> dict[str, float]:
    floor = dict(NOISE_FLOOR_DEFAULT)
    for source in [theta.get("noise_floor", {}), classical.get("noise_floor", {}), raptor.get("noise_floor", {})]:
        if isinstance(source, dict):
            for key, value in source.items():
                if isinstance(value, (int, float)):
                    floor[key] = float(value)
    return floor


def effective_deltas(deltas: dict[str, float | None], floor: dict[str, float]) -> dict[str, float | None]:
    effective: dict[str, float | None] = {}
    for key, value in deltas.items():
        if value is None:
            effective[key] = None
            continue
        effective[key] = max(0.0, float(value) - float(floor.get(key, 0.0)))
    return effective


def divergence_quality(
    effective: dict[str, float | None],
    time_to_divergence_s: float | None,
    classical: dict[str, Any],
    raptor: dict[str, Any],
) -> float:
    weights = {
        "tracking_error_max_m": 1.0,
        "tracking_error_rms_m": 3.0,
        "final_error_m": 1.5,
        "roll_pitch_max_deg": 0.08,
        "roll_pitch_std_deg": 0.12,
        "angular_rate_max_rad_s": 0.6,
        "angular_rate_std_rad_s": 0.8,
        "motor_saturation_ratio": 6.0,
    }
    score = 0.0
    for key, weight in weights.items():
        value = effective.get(key)
        if value is not None:
            score += weight * max(0.0, float(value))
    if time_to_divergence_s is not None:
        score += 2.0 / (1.0 + max(0.0, float(time_to_divergence_s)))
    thresholds = raptor.get("safe_thresholds", {}) or classical.get("safe_thresholds", {})
    for key in ["tracking_error_max_m", "roll_pitch_max_deg", "angular_rate_max_rad_s", "motor_saturation_ratio"]:
        rvalue = raptor.get(key)
        limit_key = "motor_saturation_ratio_max" if key == "motor_saturation_ratio" else key
        limit = thresholds.get(limit_key)
        if rvalue is not None and limit:
            score += 0.5 * max(0.0, float(rvalue) / float(limit) - 0.75)
    if not bool(raptor.get("safe")):
        score += 20.0
    return float(score)


def compare(theta: dict[str, Any], classical: dict[str, Any], raptor: dict[str, Any]) -> dict[str, Any]:
    div_threshold = float(theta.get("divergence_thresholds", {}).get("position_divergence_m", 2.0))
    ttd = time_to_divergence(classical, raptor, div_threshold)
    deltas = {
        "tracking_error_max_m": metric_delta(raptor, classical, "tracking_error_max_m"),
        "tracking_error_rms_m": metric_delta(raptor, classical, "tracking_error_rms_m"),
        "final_error_m": metric_delta(raptor, classical, "final_error_m"),
        "roll_pitch_max_deg": metric_delta(raptor, classical, "roll_pitch_max_deg"),
        "roll_pitch_std_deg": metric_delta(raptor, classical, "roll_pitch_std_deg"),
        "angular_rate_max_rad_s": metric_delta(raptor, classical, "angular_rate_max_rad_s"),
        "angular_rate_std_rad_s": metric_delta(raptor, classical, "angular_rate_std_rad_s"),
        "motor_saturation_ratio": metric_delta(raptor, classical, "motor_saturation_ratio"),
    }
    floor = noise_floor(theta, classical, raptor)
    effective = effective_deltas(deltas, floor)
    classical_usable = bool(classical.get("safe")) and not bool(classical.get("infrastructure_limited"))
    raptor_safe = bool(raptor.get("safe"))
    return {
        "tag": theta.get("tag"),
        "theta": theta,
        "classical": classical,
        "raptor": raptor,
        "quadrant": quadrant(classical_usable, raptor_safe),
        "classical_usable_for_primary": classical_usable,
        "primary_bug": classical_usable and not raptor_safe and divergence_quality(effective, ttd, classical, raptor) > 0.0,
        "divergence": {
            "deltas_raptor_minus_classical": deltas,
            "effective_deltas_above_noise_floor": effective,
            "noise_floor": floor,
            "quality": divergence_quality(effective, ttd, classical, raptor) if classical_usable else 0.0,
            "position_divergence_threshold_m": div_threshold,
            "time_to_divergence_s": ttd,
            "stability_margin_proxy": {
                "classical_angular_rate_peak_rad_s": classical.get("angular_rate_max_rad_s"),
                "raptor_angular_rate_peak_rad_s": raptor.get("angular_rate_max_rad_s"),
                "classical_roll_pitch_max_deg": classical.get("roll_pitch_max_deg"),
                "raptor_roll_pitch_max_deg": raptor.get("roll_pitch_max_deg"),
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theta", type=Path, required=True)
    parser.add_argument("--classical", type=Path, required=True)
    parser.add_argument("--raptor", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = compare(load_json(args.theta), load_json(args.classical), load_json(args.raptor))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "quadrant": result["quadrant"],
                "primary_bug": result["primary_bug"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
